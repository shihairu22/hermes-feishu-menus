#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PT 签到结果记录器（飞书「PT 签到」卡的数据源）+ 流式进度卡（2026-10-04）。

用途：每轮「签到pt」时逐站记录结果，供卡片显示「已签到 N/M」与最近一轮明细。

用法：
  record_checkin.py --begin [--total N]                # 开新一轮（N 缺省时从 sites.json 推导）
  record_checkin.py --site HDSky --status ok --note "分享率 1.569" --time 05:45
  record_checkin.py --site UBits --status fail --note "Turnstile"
  record_checkin.py --finish                           # 结束本轮（写 ended）
  record_checkin.py --show                             # 打印最近一轮摘要（给助手看）
  record_checkin.py --demo-card                        # 流式卡效果演示（只动卡，不写记录）

流式进度卡：--begin 时在飞书开一张卡并开始「直播」；每 --site 追加一行（打字机式写入）；
--finish 收口成完成态。任何卡操作失败都静默放行（绝不拖累签到记录本身）；--no-card 可关闭。

status: ok / fail / skip（skip = 本轮跳过，如站点无需签到）
文件：$PT_SESSIONS_DIR/state/checkin_runs.json（默认 ~/.pt-sessions；保留最近 5 轮）
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid as _uuid
from pathlib import Path

# 路径可用环境变量覆盖（默认 = 本机原值：root 下 expanduser("~") == /root，行为零变化）
_PT_DIR = os.environ.get("PT_SESSIONS_DIR") or os.path.expanduser("~/.pt-sessions")
PATH = Path(_PT_DIR) / "state" / "checkin_runs.json"
KEEP = 5

# ── 飞书流式卡（薄层；失败安全）───────────────────────────────
_HERMES_DIR = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
_TOOLS = os.path.join(_HERMES_DIR, "tools")
_CARD_TITLE = "⏳ 签到进行中"


def _api(url, payload=None, token=None, method="POST"):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8", "ignore") or "{}")
        except Exception:
            return {"code": -1}
    except Exception:
        return {"code": -1}


def _feishu_ctx():
    """复用波形生产线的 token/会话（同一应用）；导入失败返回 None。"""
    try:
        if _TOOLS not in sys.path:
            sys.path.insert(0, _TOOLS)
        import usage_wave as uw  # 延迟导入：未用签到时不必加载 usage_wave 的重依赖
        return uw.get_runtime_state()
    except Exception as exc:
        print("record_checkin: feishu ctx 不可用: %r" % (exc,), file=sys.stderr)
        return None, None


def _card_json(total: int, ok: int, done: int, lines: list, finished: bool = False,
               started: str = "", ended: str = "") -> dict:
    """进度卡本体（2.0 + streaming_mode；两个可流式元素：prog / list）。

    标题保持中性（不随状态变）——状态放进可流式的 prog，收口无需全量更新接口。
    """
    if finished:
        span = f" · {started}-{ended}" if started and ended else ""
        # 2026-10-07：只有整轮全成功才配 ✅；中途叫停/有失败用 🏁，避免「看着像全过」
        mark = "✅ 完成" if (total > 0 and ok >= total) else "🏁 结束"
        body_prog = f"{mark} {ok}/{total} · 成功 {ok}{span}"
    else:
        body_prog = "⏳ **进行中** " + (f"· {done}/{total}" + (f" · 成功 {ok}" if done else "") if done else "· 等待第一站")
    body_list = "\n".join(lines) if lines else "_等待第一站…_"
    return {
        "schema": "2.0",
        # 2026-10-05 修（X6-D29）：schema 2.0 的宽度字段是 width_mode（"default"/"fill"），
        # wide_screen_mode 是 1.0 的老字段名，2.0 卡上会被忽略（宽度不生效）。
        "config": {"width_mode": "fill", "streaming_mode": True,
                   "summary": {"content": "PT 签到进度"}},
        "header": {"title": {"tag": "plain_text", "content": "📋 PT 签到进度"}, "template": "turquoise"},
        "body": {"direction": "vertical", "padding": "12px 12px 12px 12px", "elements": [
            {"tag": "markdown", "element_id": "prog", "content": body_prog, "text_size": "normal"},
            {"tag": "markdown", "element_id": "cur", "content": "🔄 **当前**：等待开始…", "text_size": "normal"},
            {"tag": "markdown", "element_id": "list", "content": body_list, "text_size": "notation"},
        ]},
    }


_PT_LIVE = str(Path(_PT_DIR) / "state" / "checkin_live.json")


def _infer_total() -> int:
    """站点总数推导：优先 state/sites.json 清单长度；推不出来返回 0（调用方必须显式报错，绝不猜数）。"""
    for p in (Path(_PT_DIR) / "state" / "sites.json", Path(_PT_DIR) / "sites.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, list) and d:
                return len(d)
        except Exception:
            continue
    return 0


def _pt_read() -> dict:
    try:
        data = json.loads(Path(_PT_LIVE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _pt_write(obj: dict) -> None:
    """原子写标记（唯一 tmp 名 + os.replace）：插件侧永远读不到半截 JSON。"""
    p = Path(_PT_LIVE)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def _pt_mark_live(on: bool) -> None:
    """签到静音窗标记（v2 心跳制 2026-10-05）：开卡成功→写标记，收口→删标记。

    插件读到「心跳新鲜」的标记时，在签到期间静音「工具进度」与「后台任务完成」两类提示；
    其他时段/其他卡片一律不变。v2 新增 hb（心跳）字段，取代原先的 4 小时固定 TTL，
    使 5.5 小时级长轮全程静音、中断后 ≤45 分钟自灭。失败安全：写不了绝不影响主流程。
    """
    try:
        if on:
            now = time.time()
            old = _pt_read()
            started = float(old.get("started") or 0.0)
            _pt_write({"v": 2, "started": started if started > 0 else now, "hb": now,
                       "round": time.strftime("%Y-%m-%d %H:%M"), "pid": os.getpid()})
        else:
            Path(_PT_LIVE).unlink(missing_ok=True)
    except Exception:
        pass


def _pt_beat(run: dict | None = None) -> None:
    """刷新心跳（A4）：每次 --site/--stage 调一次，让静音窗跟着真实进度续期。

    标记缺失但本轮已有 card_id（崩溃后恢复续跑）→ 补建，静音窗自动恢复；
    无卡轮（--no-card / 建卡失败）不写标记 —— 语义正确：没有卡就不静音。
    """
    try:
        now = time.time()
        st = _pt_read()
        hb = float(st.get("hb") or 0.0)
        started = float(st.get("started") or 0.0)
        if hb <= 0.0 and not (run and run.get("card_id")):
            return
        st.update({"v": 2, "started": started if started > 0 else now, "hb": now,
                   "round": st.get("round") or (run or {}).get("date", ""),
                   "pid": os.getpid()})
        _pt_write(st)
    except Exception:
        pass


def card_stage(run: dict, text: str) -> None:
    """直播「当前动作」（如：HDSky 读取验证码…）——每次 --stage 调一次，覆盖同一行。"""
    try:
        cid = run.get("card_id")
        if not cid:
            return
        tok, _ = _feishu_ctx()
        _TOK_CACHE["tok"] = tok
        _bind_run(run)
        _stream(cid, "cur", "🔄 **当前**：%s" % text, _next_seq())
    except Exception as e:
        print("[card] stage 异常（忽略）:", e)


# 2026-10-09：飞书流式模式「距上次开启约 10 分钟后自动关闭」（官方文档），关闭后所有
# content PUT 返回 200850/300309；旧实现只认 code==0 且静默失败 → 卡面定格在关闭前状态
# （实测 2026-10-09 定格第 16 站：03:45 记完 BYR 后跑批量巡检，13 分钟空窗）。
_STREAM_TIMEOUT_CODES = (200850, 300309, 200510)

_SEQ = {"n": 0, "run": None}


def _bind_run(run: dict) -> None:
    """绑定本轮记录，让 sequence 跨元素统一自增（重试也占号，不会撞号）。"""
    _SEQ["run"] = run
    _SEQ["n"] = int(run.get("card_seq") or 1)


def _next_seq() -> int:
    """序号 = max(上次+1, 当前秒级时间戳)。

    飞书要求同一卡片的 sequence 严格递增（否则 300317），又不提供「已用到几号」的查询接口；
    用秒级时间戳做基数，可让「进程崩溃后磁盘 card_seq 落后于服务端」的卡片自动追平
    （实测 2026-10-09：探针未回写 card_seq，服务端已见 95 而磁盘仍是 91，后续全部 300317）。
    实测飞书接受秒级时间戳与 int32 上限；毫秒级（1.79e12）会被 9499 拒掉。
    """
    n = max(_SEQ["n"] + 1, int(time.time()))
    _SEQ["n"] = n
    r = _SEQ["run"]
    if isinstance(r, dict):
        r["card_seq"] = n
    return n


def _reopen_streaming(card_id: str) -> bool:
    """重新开启被飞书超时关闭的流式模式（官方恢复办法）。序号走统一分配器，避免撞号。"""
    r = _api("https://open.feishu.cn/open-apis/cardkit/v1/cards/%s/settings" % card_id,
             {"settings": json.dumps({"config": {"streaming_mode": True}}),
              "sequence": _next_seq(), "uuid": _uuid.uuid4().hex},
             token=_stream_tok(), method="PATCH")
    if r.get("code") == 0:
        print("[card] 流式模式已被飞书超时关闭 → 已重新开启", file=sys.stderr)
        return True
    print("[card] 重开流式模式失败:", r.get("code"), r.get("msg"), file=sys.stderr)
    return False


def _stream(card_id: str, element_id: str, content: str, seq: int) -> bool:
    if seq > _SEQ["n"]:
        _SEQ["n"] = seq      # 保证后续 _next_seq() 始终大于已用过的序号
    url = "https://open.feishu.cn/open-apis/cardkit/v1/cards/%s/elements/%s/content" % (card_id, element_id)
    r = _api(url, {"content": content, "sequence": seq, "uuid": _uuid.uuid4().hex},
             token=_stream_tok(), method="PUT")
    if r.get("code") == 0:
        return True
    if r.get("code") in _STREAM_TIMEOUT_CODES:
        if _reopen_streaming(card_id):
            r2 = _api(url, {"content": content, "sequence": _next_seq(), "uuid": _uuid.uuid4().hex},
                      token=_stream_tok(), method="PUT")
            if r2.get("code") == 0:
                return True
            print("[card] 重开后重试仍失败:", r2.get("code"), r2.get("msg"), file=sys.stderr)
        return False
    print("[card] 流式更新失败:", r.get("code"), r.get("msg"), file=sys.stderr)
    return False


_TOK_CACHE = {"tok": None}


def _stream_tok():
    if _TOK_CACHE["tok"] is None:
        t, _ = _feishu_ctx()
        _TOK_CACHE["tok"] = t or ""
    return _TOK_CACHE["tok"] or None


def card_begin(run: dict) -> None:
    """开卡并发送；card_id 写进本轮记录（供后续追加）。"""
    try:
        tok, chat = _feishu_ctx()
        if not tok or not chat:
            return
        card = _card_json(int(run.get("total") or 0), 0, 0, [])
        r = _api("https://open.feishu.cn/open-apis/cardkit/v1/cards",
                 {"type": "card_json", "data": json.dumps(card, ensure_ascii=False)}, token=tok)
        cid = (r.get("data") or {}).get("card_id")
        if r.get("code") != 0 or not cid:
            print("[card] 创建失败:", r.get("code"), r.get("msg"))
            return
        r2 = _api("https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
                  {"receive_id": chat, "msg_type": "interactive",
                   "content": json.dumps({"type": "card", "data": {"card_id": cid}}, ensure_ascii=False),
                   "uuid": _uuid.uuid4().hex}, token=tok)
        if r2.get("code") != 0:
            print("[card] 发送失败:", r2.get("code"), r2.get("msg"))
            return
        run["card_id"] = cid
        run["card_seq"] = 1
        _pt_mark_live(True)   # A1：静音窗只在「建卡+推送」均成功后开启（早退/异常不再误开）
        print("[card] 流式进度卡已开:", cid)
    except Exception as e:  # 永不拖累记录
        print("[card] 开卡异常（忽略）:", e)


def _site_lines(run: dict) -> list:
    """卡面站点行 = 由 run['sites'] 全量重建（B4：与 main 的同站覆盖语义一致）。"""
    icons = {"ok": "✅", "fail": "❌", "skip": "⏭"}
    return [
        f"{icons.get(it.get('status'), '•')} {it.get('site')}"
        + (f" · {it.get('note')}" if it.get("note") else "")
        for it in (run.get("sites") or [])
    ]


def card_site(run: dict, site: str, status: str, note: str, total: int) -> None:
    try:
        cid = run.get("card_id")
        if not cid:
            return
        run["card_lines"] = _site_lines(run)   # B4：全量重建，同站只一行、行数与计数一致
        ok = sum(1 for x in (run.get("sites") or []) if x.get("status") == "ok")
        done = len(run.get("sites") or [])
        tok, _ = _feishu_ctx()
        _TOK_CACHE["tok"] = tok
        _bind_run(run)
        _stream(cid, "list", "\n".join(run["card_lines"]), _next_seq())
        _stream(cid, "prog", f"**进度 {done}/{total}** · 成功 {ok}", _next_seq())
        # 2026-10-07：按状态出图标与措辞（失败站不再显示 ✅）
        _icon = {"ok": "✅ 最近成功", "fail": "❌ 最近失败", "skip": "⏭ 最近跳过"}.get(
            status, "• 最近完成")
        _stream(cid, "cur", f"{_icon}：{site} · {time.strftime('%H:%M')}", _next_seq())
    except Exception as e:
        print("[card] 追加异常（忽略）:", e)


def card_finish(run: dict) -> None:
    _pt_mark_live(False)   # 静音窗关闭（失败安全：先关再收口，任何异常都不影响）
    try:
        cid = run.get("card_id")
        if not cid:
            return
        total = int(run.get("total") or 0)
        ok = sum(1 for x in (run.get("sites") or []) if x.get("status") == "ok")
        done = len(run.get("sites") or [])
        # 只走流式（不碰全量更新接口）：prog 出完成态 + list 补一行收口时间。
        card = _card_json(total, ok, done, [], finished=True,
                          started=run.get("started", ""), ended=run.get("ended", ""))
        tok, _ = _feishu_ctx()
        _TOK_CACHE["tok"] = tok
        _bind_run(run)
        ok1 = _stream(cid, "prog", card["body"]["elements"][0]["content"], _next_seq())
        lines = run.get("card_lines") or []
        lines.append(f"_{run.get('started','')}-{run.get('ended','')} 结束 · 成功 {ok}/{total}_")
        run["card_lines"] = lines
        ok2 = _stream(cid, "list", "\n".join(lines), _next_seq())
        _stream(cid, "cur", "🏁 **本轮已结束**", _next_seq())
        print("[card] 收口:", "OK" if (ok1 and ok2) else f"prog={ok1} list={ok2}")
    except Exception as e:
        print("[card] 收口异常（忽略）:", e)


# ── 记录层（原逻辑，保持逐字兼容）─────────────────────────────

# ── 状态文件安全读写（B1+B2+B3 统一方案 2026-10-05）───────────
#  B1 损坏不再静默当空表（先隔离留证再允许覆盖）
#  B2 flock 排他锁覆盖整个 read-modify-write（并发不丢更新）
#  B3 唯一 tmp 名 + fsync 后 os.replace（并发互踩成为不可能）
_LOCK_FD = {"fd": None}


def _acquire_lock() -> None:
    """对状态文件取排他锁（flock，随进程退出自动释放；一次调用只取一次）。"""
    if _LOCK_FD["fd"] is not None:
        return
    lock_path = PATH.with_name(PATH.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)   # 阻塞等待；持有者都是毫秒级短进程
    except BaseException:
        os.close(fd)
        raise
    _LOCK_FD["fd"] = fd


def _release_lock() -> None:
    fd = _LOCK_FD["fd"]
    if fd is not None:
        _LOCK_FD["fd"] = None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _load() -> dict:
    """读状态；持排他锁直至 _save 完成（锁住整个 read-modify-write）。

    损坏绝不静默丢弃：原字节另存为 .corrupt.<ts>.<pid> 并告警，再返回空表。
    仅「文件不存在」按空表处理；其他 I/O 异常如实抛出，避免误当空表覆盖。
    """
    _acquire_lock()
    try:
        raw = PATH.read_bytes()
    except FileNotFoundError:
        return {"runs": []}
    err = None
    data = None
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:            # B1：解析失败不再装作空表
        err = e
    if err is None and not (isinstance(data, dict) and isinstance(data.get("runs"), list)):
        err = ValueError("结构不符：缺少 runs 列表")
    if err is None:
        return data
    ts = time.strftime("%Y%m%d-%H%M%S")
    quar = PATH.with_name(f"{PATH.name}.corrupt.{ts}.{os.getpid()}")
    try:
        quar.write_bytes(raw)          # 留证据（原文件保持不动，随后由 _save 原子替换）
        print(f"[state] 状态文件损坏，已隔离副本到 {quar}（可人工恢复）：{err}", file=sys.stderr)
    except OSError as e2:
        print(f"[state] 状态文件损坏且隔离失败（原文件保持不动）：{err} / {e2}", file=sys.stderr)
    return {"runs": []}


def _save(data: dict) -> None:
    try:
        data["runs"] = data["runs"][-KEEP:]
        PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        # B3：唯一 tmp 名（mkstemp = O_EXCL+随机），并发互踩成为不可能
        fd, tmp = tempfile.mkstemp(dir=str(PATH.parent), prefix=PATH.name + ".tmp.", suffix=".part")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())   # 先落盘再换名
            os.replace(tmp, PATH)      # 单次写原子可见
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        os.chmod(PATH, 0o644)          # mkstemp 默认 0600，恢复原权限
        try:                           # 目录 fsync：让 rename 也持久（失败无妨）
            dfd = os.open(str(PATH.parent), os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
    finally:
        _release_lock()                # 无论成败都解锁（进程退出亦自动释放）


def _cur(data: dict) -> dict | None:
    runs = data["runs"]
    if runs and not runs[-1].get("ended"):
        return runs[-1]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--begin", action="store_true", help="开始新一轮")
    ap.add_argument("--total", type=int, default=0,
                    help="站点总数（缺省时从 state/sites.json 推导；都推不出来则报错退出，不写记录）")
    ap.add_argument("--site", default="", help="站点名")
    ap.add_argument("--status", default="ok", choices=["ok", "fail", "skip"])
    ap.add_argument("--note", default="", help="备注（分享率/原因等）")
    ap.add_argument("--time", default="", help="该站完成时间 HH:MM（默认当前）")
    ap.add_argument("--stage", default="", help="直播「当前动作」（如：HDSky 读取验证码…）")
    ap.add_argument("--finish", action="store_true", help="结束本轮")
    ap.add_argument("--show", action="store_true", help="打印最近一轮摘要")
    ap.add_argument("--no-card", action="store_true", help="本轮不更新流式卡")
    ap.add_argument("--allow-new-run", action="store_true",
                    help="无进行中轮次时允许 --site 自动开新轮（默认拒绝，防幽灵轮次）")
    ap.add_argument("--beat", action="store_true", help="刷新静音窗心跳（长站中途续期用）")
    ap.add_argument("--demo-card", action="store_true", help="流式卡效果演示（只动卡，不写记录）")
    a = ap.parse_args()

    if a.demo_card:
        demo = {"total": 6, "sites": [], "card_lines": [], "started": time.strftime("%H:%M")}
        card_begin(demo)
        time.sleep(1.5)
        card_stage(demo, "HDSky · 读取签到验证码（双路识图）…")
        time.sleep(1.5)
        for w in [("M-Team", "ok", "登录保活 · 已登录"), ("HDSky", "ok", "第 512 次签到 +12"),
                  ("U2", "ok", "圆点题一次过 +55 UCoin"), ("PigGo", "fail", "SafeLine 超时（已跳过）"),
                  ("ZT", "skip", "无签到 · 登录保活达成")]:
            if w[0] == "PigGo":
                card_stage(demo, "PigGo · 等待 SafeLine 挑战…")
                time.sleep(1.2)
            demo["sites"].append({"site": w[0], "status": w[1], "note": w[2]})
            card_site(demo, w[0], w[1], w[2], demo["total"])
            time.sleep(1.0)
        demo["ended"] = time.strftime("%H:%M")
        card_finish(demo)
        print("演示完成（未写记录文件）")
        return 0

    data = _load()
    now_hm = time.strftime("%H:%M")

    if a.show:
        runs = data.get("runs") or []
        if not runs:
            print("（无记录）")
            return 0
        r = runs[-1]
        sites = r.get("sites") or []
        print(f"{r.get('date')} {r.get('started','')}-{r.get('ended','')}  "
              f"ok={r.get('ok',0)}/{r.get('total','?')}  明细 {len(sites)} 站")
        for it in sites:
            print(f"  {it.get('site'):<16} {it.get('status'):<5} {it.get('time','')} {it.get('note','')}")
        if r.get("note"):
            print("  note:", r["note"])
        return 0

    if a.begin:
        cur = _cur(data)
        if cur:  # 上一轮没 --finish：补结束 + 收口旧卡 + 清静音标记（A3）
            cur["ended"] = cur.get("ended") or now_hm
            cur["ok"] = sum(1 for x in (cur.get("sites") or []) if x.get("status") == "ok")
            if cur.get("card_id"):
                card_finish(cur)   # 旧卡收口成完成态（内部失败安全；不永久挂「进行中」）
            _pt_mark_live(False)   # 兜底清标记；新一轮开卡时按需重新开启
        total = a.total or _infer_total()
        if total <= 0:
            print("无法确定站点总数：请显式传 --total N，或先写 state/sites.json 站点清单",
                  file=sys.stderr)
            return 1
        run = {
            "date": time.strftime("%Y-%m-%d"),
            "started": now_hm,
            "ended": "",
            "total": total,
            "ok": 0,
            "note": "",
            "sites": [],
        }
        data["runs"].append(run)
        if not a.no_card:
            card_begin(run)          # card_id/card_seq 会写进 run（随 _save 落盘）
        _save(data)
        print(f"新一轮开始：{run['date']} {run['started']}  共 {run['total']} 站")
        return 0

    if a.stage:
        cur = _cur(data)
        if not cur:
            print("没有进行中的轮次（--stage 只对进行中的轮次生效）")
            return 1
        _pt_beat(cur)                      # A4：长站中途也续期
        if not a.no_card:
            card_stage(cur, a.stage)
        _save(data)
        print(f"[stage] {a.stage}")
        return 0

    if a.finish:
        cur = _cur(data)
        if not cur:
            print("没有进行中的轮次")
            return 1
        cur["ended"] = now_hm
        cur["ok"] = sum(1 for x in (cur.get("sites") or []) if x.get("status") == "ok")
        _pt_mark_live(False)   # A2：不依赖卡片路径——--no-card / 收口异常都保证清标记
        if not a.no_card:
            card_finish(cur)   # 内部第一行会再删一次（幂等）
        _save(data)
        print(f"本轮结束：{cur['date']} {cur['started']}-{cur['ended']}  ok={cur['ok']}/{cur['total']}")
        return 0

    if a.beat:
        cur = _cur(data)
        _pt_beat(cur)
        print("[beat] 静音窗心跳已刷新" if cur else "[beat] 无进行中轮次（仅刷新已有标记）")
        return 0

    if a.site:
        cur = _cur(data)
        if not cur:
            if not a.allow_new_run:
                print("没有进行中的轮次：请先用 --begin 开轮；确需为补录新建一轮，"
                      "请显式加 --allow-new-run（原静默自建行为已移除）", file=sys.stderr)
                return 1
            total = a.total or _infer_total()
            if total <= 0:
                print("无法确定站点总数：请显式传 --total N，或先写 state/sites.json 站点清单",
                      file=sys.stderr)
                return 1
            cur = {"date": time.strftime("%Y-%m-%d"), "started": now_hm, "ended": "",
                   "total": total, "ok": 0, "note": "", "sites": []}
            data["runs"].append(cur)
            print(f"[warn] 无进行中轮次，按 --allow-new-run 新建一轮"
                  f"（{cur['date']} {cur['started']}）", file=sys.stderr)
            if not a.no_card:
                card_begin(cur)
        _pt_beat(cur)                      # A4：每站续期静音窗心跳
        sites = cur.setdefault("sites", [])
        for it in sites:  # 同站重复记录 → 覆盖
            if it.get("site") == a.site:
                it.update(status=a.status, note=a.note, time=a.time or now_hm)
                break
        else:
            sites.append({"site": a.site, "status": a.status, "note": a.note,
                          "time": a.time or now_hm})
        cur["ok"] = sum(1 for x in sites if x.get("status") == "ok")
        if not a.no_card:
            card_site(cur, a.site, a.status, a.note, int(cur.get("total") or 0))
        _save(data)
        print(f"已记录 {a.site} → {a.status} ({len(sites)}/{cur['total']})")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
