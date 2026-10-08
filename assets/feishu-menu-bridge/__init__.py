"""feishu-menu-bridge — 飞书机器人自定义菜单 ↔ Hermes 的桥接层。

背景
----
飞书机器人菜单的「发送文字消息」型菜单项，发出去的就是菜单名本身。菜单名为了好看
（不带斜杠），发出来的文本就成了裸词（如 ``面板``/``新会话``），Hermes 命令层不认识。

本插件在 ``pre_gateway_dispatch`` 钩子上工作——该钩子跑在**鉴权与命令派发之前**，
因此可以：
  * 把文字型菜单名改写为 ``/<同名>``（命中 config.yaml 的 quick_commands，零模型、零 token）；
    菜单名可带 emoji（``📊面板``）——先精确命中，再退回「剥掉开头图标」后的名字；
  * 把 6 个卡片型菜单名（面板/系统/PT/技能/帮助/用量）就地渲染成飞书交互卡片，
    并以 ``{"action": "skip"}`` 丢弃原文本，不进模型；
  * 卡片上的按钮点击回注一条消息（斜杠命令或自然语言）到同一会话。

不修改任何官方文件；卡片点击复用官方 FeishuAdapter 的卡片回调通道。
"""
from __future__ import annotations

import asyncio
import ctypes
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("hermes_plugins.feishu_menu_bridge")

_MARKER = "_hermes_feishu_menu_bridge_installed"
_MARKER_LARK = "_hermes_feishu_menu_bridge_lark_hook"

# ── 跨重载守护宿主（keeper）────────────────────────────────────────
# 热重载会 evict 本模块并 exec 一份新模块对象 → 上一代的守护线程若不退役，就会用
# 旧代码反复重建分发器。历史做法是注入 SystemExit 杀掉它，但那会被网关的
# threading.excepthook 记成 [gateway-crash]，并污染 tui_gateway_crash.log。
# 现改为：线程只有一条、跨代存活、每轮执行最新代代码（详见 keeper.py）。
# keeper 模块名不在 hermes_plugins.<slug> 前缀下 → 不会被 evict。
_KEEPER_NAME = "hermes_plugins._fmb_keeper"
_KEEPER_FILE = Path(__file__).with_name("keeper.py")
_KEEPER_VERSION = 2   # 必须与 keeper.py 里的 KEEPER_VERSION 一致（改 keeper.py 时两边一起加）


#: keeper 对外契约（2026-10-04 审计：把「改 keeper.py 要两边一起改、靠人盯注释」变成机械检查）
_WATCHER_NAME_EXPECTED = "feishu-menu-bridge"
_KEEPER_CONTRACT_FUNCS = ("shared", "watch_loop", "watchdog_loop", "boot", "request_stop", "status")
_KEEPER_CONTRACT_ATTRS = (("KEEPER_VERSION", int), ("WATCHER_NAME", str), ("state", dict), ("token", int))


def _verify_keeper_contract(mod) -> None:
    """只读检查 keeper 契约：缺符号就抛 → 走既有 except → 退化为插件自带线程（不会炸网关）。"""
    for name in _KEEPER_CONTRACT_FUNCS:
        if not callable(getattr(mod, name, None)):
            raise RuntimeError("keeper 契约缺失/非可调用: %s" % name)
    for name, typ in _KEEPER_CONTRACT_ATTRS:
        if not isinstance(getattr(mod, name, None), typ):
            raise RuntimeError("keeper 契约类型错误: %s" % name)
    if getattr(mod, "WATCHER_NAME", "") != _WATCHER_NAME_EXPECTED:
        raise RuntimeError("keeper WATCHER_NAME 漂移: %r" % getattr(mod, "WATCHER_NAME", None))
    # 2026-10-07 审计修复（#15）：原来只校验 KEEPER_VERSION「是 int」。文件里的版本号与
    # 本文件期望值不一致时，模块仍能装上，但下一次 _keeper_module() 又会因为版本不等而
    # 重载 → 每次调用都重载 keeper、重启线程（重载风暴）。这里直接判等，漂移就落到上面
    # 既有的 except（退化为插件自带线程，不炸网关）。
    if getattr(mod, "KEEPER_VERSION", None) != _KEEPER_VERSION:
        raise RuntimeError("keeper KEEPER_VERSION 漂移: %r != %r"
                           % (getattr(mod, "KEEPER_VERSION", None), _KEEPER_VERSION))


def _keeper_module():
    """取/建 keeper 模块；keeper.py 缺失时返回 None（退化路径，插件仍可用）。

    版本戳不一致（keeper.py 被改过）→ 丢掉旧的、加载新的，并把跨代共享容器搬过去。
    旧 keeper 的线程会按「自我让位」自行退出，因此**改 keeper.py 不必重启网关**。
    """
    import importlib.util

    old = sys.modules.get(_KEEPER_NAME)
    if old is not None and getattr(old, "KEEPER_VERSION", None) == _KEEPER_VERSION:
        return old
    try:
        spec = importlib.util.spec_from_file_location(_KEEPER_NAME, _KEEPER_FILE)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[_KEEPER_NAME] = mod
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            sys.modules.pop(_KEEPER_NAME, None)
            raise
        _verify_keeper_contract(mod)      # 契约校验：漂移立刻落到下面既有 except（退化线程）
        if old is not None:
            # 旧 keeper 用**它自己的停止标志**收摊（置标志，不注入异常）：watcher/看门狗都会退出
            try:
                old.stop = True
            except Exception:
                pass
            # 搬走共享容器（_SOURCES / _QUOTA_CACHE …）：同一批字典对象继续被新代别名过去
            try:
                mod.state.update(getattr(old, "state", {}) or {})
            except Exception:
                pass
            logger.warning("[FeishuMenuBridge] keeper 换版 %s → %s（已重载，共享状态已搬移）",
                           getattr(old, "KEEPER_VERSION", "?"), _KEEPER_VERSION)
        return mod
    except Exception:
        logger.warning("[FeishuMenuBridge] keeper 加载失败，退化为插件自带线程", exc_info=True)
        sys.modules.pop(_KEEPER_NAME, None)
        return None


def _shared(key: str, factory):
    """取/建跨代共享容器：热重载后仍指向同一对象（否则卡片按钮回注的会话上下文会丢）。"""
    k = _keeper_module()
    if k is None:
        return factory()
    return k.shared(key, factory)


# ── 菜单结构（与飞书控制台菜单一一对应，改一处即可）────────────────
# 2026-09-30 精简：5 组 23 项（原 5×10=50）。逐项依据 = 使用日志 + 命令注册表核验：
#   · 删「需参数、点了只回用法」的项（后台/侧问/插话/学习/导出/排队/标题/心跳/变更/记忆）
#   · 删零使用且非行业共识的项（洞察/时间/身份/回退/分支/恢复/审批/语音条/对讲/静音/计划/平台）
#   · 删本机模型不支持的「加速」（/fast 对 cn:deepseek-v4.1-flash 为 False）
#   · 新增「命令表」「重启」以对齐 Telegram 菜单（两者 gateway_only，聊天侧可用）
# 2026-09-30 21:05 二轮微调（使用度 2 天数据 + 卡片重复度）：
#   · 删「上下文」（与「状态」信息重叠，卡片里也能看）、「会话列表」（0 次使用）
#   · 新增「语音」（→ /voice 切换语音模式；飞书适配器支持原生语音消息，本机 TTS 全本地）
#   · 改名消歧义：「忙碌」→「忙时」（/busy 是"我忙时你的消息怎么处理"，不是"我很忙"）、
#     「主页」→「设主频道」（/sethome 是把此聊天设为主频道，避免与仪表盘主页混淆）
GROUPS: List[Tuple[str, List[str]]] = [
    ("面板", ["面板", "系统", "用量", "技能", "PT", "帮助"]),
    ("会话", ["新会话", "状态", "重试", "压缩"]),
    ("任务", ["任务", "停止", "目标"]),
    ("设置", ["模型", "推理", "人格", "语音", "忙时", "设主频道"]),
    ("运维", ["命令表", "版本", "更新", "重启"]),
]

#: 卡片型入口（点按出卡片，不发文本）——与 CARD_BUILDERS 逐项一致（2026-10-04 同步：
#: 删「模型」（死代码，走 /model 点选器）、补「洞察」（入口在系统卡/用量卡，也登记在此供审计对齐）。
#: 注：「模型」不在这里 —— 2026-10-04 用户要求「设置里模型要跟面板里那个效果一样」，
#:     所以「模型」改回发 /model（= 飞书点选器插件给的「切换模型 · 选择提供方」交互卡）。
CARD_NAMES = ("面板", "系统", "系统详情", "PT", "技能", "帮助", "用量", "命令表", "人格",
              "状态", "推理", "任务", "洞察", "忙时", "版本")

#: 文字型入口 → 改写目标（**真实内置命令**）。
#: 2026-10-02 修正：原实现假设存在 /停止 /新会话 这类中文斜杠命令，
#: 实测 resolve_command() 全部返回 None —— 点菜单等于发一条没人认识的斜杠文本。
#: 下表每个目标都经 resolve_command() 实测通过（scratch/test_resolve2.py）。
_MENU_CMD: Dict[str, str] = {
    "新会话": "/new", "重试": "/retry", "压缩": "/compact",
    "停止": "/stop", "目标": "/goal",
    "语音": "/voice", "设主频道": "/sethome",
    "更新": "/update", "重启": "/restart",
    "模型": "/model",          # 2026-10-04：回到点选器（和「面板」里那颗按钮同一个效果）
}
# 注：「状态」「推理」「任务」「忙时」「版本」已从本表摘除 → 落到 CARD_BUILDERS 分支，
#     点菜单出卡片而不是发命令。
#     /status、/reasoning 仍可在聊天里直接输入；两张卡片上也有对应按钮。
#     「模型」反过来：不发卡片，发 /model（飞书点选器插件会渲染「切换模型 · 选择提供方」交互卡）。

COMMANDS: Dict[str, str] = {
    name: _MENU_CMD[name]
    for _g, _items in GROUPS
    for name in _items
    if name in _MENU_CMD
}

#: 直输斜杠命令 → 卡片名（2026-10-04 卡片化研究落地：不再「菜单出卡、直输回文字」两套皮）。
#: 只认**裸命令**；带参数的一律原样放行（/reasoning high、/help <词>、/model <id>、/busy queue…）。
_SLASH_CARD_MAP: Dict[str, str] = {
    "/status": "状态", "/reasoning": "推理", "/usage": "用量", "/insights": "洞察",
    "/version": "版本", "/help": "帮助", "/commands": "命令表", "/personality": "人格",
    "/busy": "忙时",
}

#: 菜单名开头的图标/空白（2026-10-02 起悬浮菜单项名称带 emoji，如「📊面板」）
_ICON_LEAD_RE = re.compile(r"^[^\u4e00-\u9fa5A-Za-z0-9/]+")


def _strip_lead_icon(text: str) -> str:
    """剥掉开头的图标/空白，让带 emoji 的菜单名与纯中文名同样命中。"""
    return _ICON_LEAD_RE.sub("", str(text or "")).strip()


def _resolve_menu_key(text: str) -> Optional[str]:
    """菜单文本 → 已登记的键（先精确命中，再退回「剥掉开头图标」后的名字）。

    统一入口：pre_gateway_dispatch / 帧层 / 忙线 / 批处理 四处共用
    （2026-10-04 审计：原来这段解析在本文件里抄了 4 份）。
    """
    key = str(text or "")
    if key in COMMANDS or key in CARD_BUILDERS:
        return key
    alt = _strip_lead_icon(key)
    if alt and alt != key and (alt in COMMANDS or alt in CARD_BUILDERS):
        return alt
    return None

#: 最近一次各会话的来源对象（卡片按钮回注消息时复用）
#: 存进 keeper 的跨代共享容器 → 热重载后仍在（原来每代一份，重载即丢）
_SOURCES: Dict[str, Any] = _shared("sources", dict)
_SOURCES_TS: Dict[str, float] = _shared("sources_ts", dict)
_SOURCE_TTL = 86400.0


# ── 本机数据采集（全部走线程，别堵事件循环）─────────────────────────

def _run(cmd: str, timeout: float = 4.0) -> str:
    """跑一条本机命令，**只取 stdout** —— stderr 是诊断信息，绝不能当作数据渲染进卡片。"""
    try:
        out = subprocess.run(
            ["bash", "-lc", cmd], capture_output=True, text=True, timeout=timeout,
        )
        if out.returncode and out.stderr.strip() and not out.stdout.strip():
            logger.debug("[FeishuMenuBridge] _run 非零退出（%s）：%s",
                         out.returncode, out.stderr.strip()[:200])
        return (out.stdout or "").strip()
    except Exception:
        return ""


def _host_stats() -> Dict[str, str]:
    disk = _run("df -h / | awk 'NR==2{print $3\"|\"$2\"|\"$5}'")
    d_used, d_total, d_pct = (disk.split("|") + ["?", "?", "?"])[:3]
    mem = _run("free -h | awk 'NR==2{print $3\"|\"$2}'")
    m_used, m_total = (mem.split("|") + ["?", "?"])[:2]
    load = _run("cut -d' ' -f1-3 /proc/loadavg")
    up = _run("uptime -p")
    cpu = _run("nproc")
    m_pct = "?"
    try:  # 内存百分比（3.1G / 15.6G → 20%）；单位不一致时换算
        def _g(t: str) -> float:
            return float(re.sub(r"[^0-9.]", "", t or "") or 0)
        _mu, _mt = _g(m_used), _g(m_total)
        if "G" in m_total and "M" in m_used:
            _mu = _mu / 1024.0
        elif "M" in m_total and "G" in m_used:
            _mu = _mu * 1024.0
        if _mt > 0:
            m_pct = f"{_mu / _mt * 100:.0f}%"
    except Exception:
        pass
    return {
        "disk": f"{d_used} / {d_total} · {d_pct}",
        "disk_used": d_used, "disk_total": d_total, "disk_pct": d_pct,
        "mem": f"{m_used} / {m_total}",
        "mem_used": m_used, "mem_total": m_total, "mem_pct": m_pct,
        "load": load or "?",
        "uptime": up or "?",
        "cpu": cpu or "?",
    }


def _model_info() -> Dict[str, str]:
    """从 config.yaml 顶层 ``model:`` 块里取 default / context_length（不依赖 YAML 库）。"""
    import os
    import re
    home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
    info = {"default": "?", "context_length": "?"}
    try:
        text = (home / "config.yaml").read_text(encoding="utf-8")
    except Exception:
        return info
    block = re.search(r"(?ms)^model:\s*\n((?:[ \t]+.*\n|\s*\n)*)", text)
    scope = block.group(1) if block else text
    m = re.search(r"(?m)^[ \t]+default:\s*['\"]?([^\s'\"]+)", scope)
    if m:
        info["default"] = m.group(1)
    m = re.search(r"(?m)^[ \t]+context_length:\s*['\"]?([0-9_]+)", scope)
    if m:
        try:
            info["context_length"] = f"{int(m.group(1).replace('_', '')) // 1000}K"
        except Exception:
            info["context_length"] = m.group(1)
    return info


def _current_model() -> str:
    return _model_info().get("default") or "?"


def _skills_index() -> Tuple[int, List[Tuple[str, int]]]:
    """返回 (技能总数, [(分类, 数量)...])"""
    try:
        home = Path(__import__("os").environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        root = home / "skills"
        buckets: Dict[str, int] = {}
        total = 0
        for skill_md in root.glob("*/*/SKILL.md"):
            buckets[skill_md.parent.parent.name] = buckets.get(skill_md.parent.parent.name, 0) + 1
            total += 1
        for skill_md in root.glob("*/SKILL.md"):
            buckets.setdefault("(未分类)", 0)
            buckets["(未分类)"] += 1
            total += 1
        return total, sorted(buckets.items(), key=lambda kv: -kv[1])
    except Exception:
        return 0, []


def _pt_sites() -> int:
    """站点总数：优先 state/sites.json（站点清单），退回根目录 *.json 计数。"""
    try:
        p = Path(_PT_DIR + "/state/sites.json")
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return len(data)
    except Exception:
        pass
    try:
        root = Path(_PT_DIR)
        # 兜底①：sites.json 的两个候选位置（state/ 是实际位置）
        for _p in (root / "state" / "sites.json", root / "sites.json"):
            try:
                _d = json.loads(_p.read_text(encoding="utf-8"))
                if isinstance(_d, list) and _d:
                    return len(_d)
            except Exception:
                continue
        # 兜底②：从最近一轮签到记录数去重站点（真实数据，绝不猜数）
        _rec = json.loads((root / "state" / "checkin_runs.json").read_text(encoding="utf-8"))
        _runs = [r for r in (_rec.get("runs") or []) if isinstance(r, dict)]
        if _runs:
            _seen = {str(x.get("site")) for x in (_runs[-1].get("sites") or [])
                     if isinstance(x, dict)}
            if _seen:
                return len(_seen)
    except Exception:
        pass
    return 0


def _now_hm() -> str:
    return time.strftime("%H:%M")


def _bg_tasks() -> int:
    """后台任务数：未完成的委托/子代理（async_delegations）。-1 = 取不到。"""
    try:
        import os as _os

        home = Path(_os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        conn = _ro_conn(home)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM async_delegations WHERE completed_at IS NULL"
                " AND state IN ('running','queued','pending','dispatched')").fetchone()
            return int(row[0] or 0) if row else 0
        finally:
            conn.close()
    except Exception:
        return -1


def _session_ctx(chat_id: str, source: str = "feishu") -> Tuple[str, str]:
    """当前会话上下文 ≈（active 消息字符数 / 4，与网关压缩口径一致）与上限（config context_length）。"""
    limit = _model_info().get("context_length") or "?"
    if not chat_id:
        return "—", limit
    try:
        import os as _os

        home = Path(_os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        key = "agent:main:%s:dm:%s" % (source, chat_id)
        conn = _ro_conn(home)
        try:
            row = conn.execute(
                "SELECT (SELECT COALESCE(SUM(LENGTH(COALESCE(m.content,''))),0) FROM messages m"
                " WHERE m.session_id = s.id AND m.active = 1)"
                " FROM sessions s WHERE s.session_key = ? AND s.message_count > 0"
                " ORDER BY s.started_at DESC LIMIT 1", (key,)).fetchone()
        finally:
            conn.close()
        if row and row[0]:
            return "≈" + _fmt_tokens(int(row[0]) // 4), limit
    except Exception:
        logger.info("[FeishuMenuBridge] ctx estimate failed", exc_info=True)
    return "—", limit


def _session_info(chat_id: str, source: str = "feishu") -> Tuple[str, str, str]:
    """当前会话：(已运行时长, 起始时刻, 消息数)。取不到一律给 '—'。"""
    if not chat_id:
        return "—", "—", "—"
    try:
        import datetime as _dt
        import os as _os

        home = Path(_os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        key = "agent:main:%s:dm:%s" % (source, chat_id)
        conn = _ro_conn(home)
        try:
            row = conn.execute(
                "SELECT started_at, COALESCE(message_count,0) FROM sessions"
                " WHERE session_key = ? AND message_count > 0"
                " ORDER BY started_at DESC LIMIT 1", (key,)).fetchone()
        finally:
            conn.close()
        if not row:
            return "—", "—", "—"
        started = float(row[0] or 0)
        n = int(row[1] or 0)
        if started <= 0:
            return "—", "—", (f"{n} 条" if n else "—")
        t = _dt.datetime.fromtimestamp(started)
        mins = int((time.time() - started) // 60)
        if mins < 60:
            dur = f"{mins}m"
        elif mins < 1440:
            dur = f"{mins // 60}h{mins % 60:02d}m"
        else:
            dur = f"{mins // 1440}d{mins % 1440 // 60}h"
        return dur, t.strftime("%H:%M"), (f"{n} 条" if n else "—")
    except Exception:
        logger.info("[FeishuMenuBridge] session info failed", exc_info=True)
        return "—", "—", "—"


_CAT_EMOJI = {
    "autonomous-ai-agents": "🤖", "creative": "🎨", "devops": "🛠", "email": "✉️",
    "media": "🎬", "note-taking": "📝", "productivity": "📄", "research": "🔬",
    "social-media": "💬", "software-development": "💻",
    "web": "🌐", "(未分类)": "📦",
}

#: 悬浮菜单五组各自的图标（与菜单项图标一致）
_GROUP_EMOJI = {"面板": "📊", "会话": "💬", "任务": "🎯", "设置": "⚙️", "运维": "🔧"}


_CAT_ZH = {
    "autonomous-ai-agents": "代理编排", "creative": "创意", "devops": "运维",
    "email": "邮件", "media": "媒体", "note-taking": "笔记", "productivity": "效率",
    "research": "研究", "social-media": "消息平台", "software-development": "软件开发",
    "web": "网页",
}



def _pt_last_run() -> Optional[Dict[str, Any]]:
    """最近一轮 PT 签到记录（$PT_SESSIONS_DIR/state/checkin_runs.json；默认 ~/.pt-sessions）。"""
    try:
        data = json.loads(Path(_PT_DIR + "/state/checkin_runs.json").read_text(encoding="utf-8"))
        runs = list(data.get("runs") or [])
        return runs[-1] if runs else None
    except Exception:
        return None


def _pt_ready() -> bool:
    """本机是否具备 PT 签到能力 = 装了响应「签到pt」的技能（pt-site-keepalive）。

    为什么门控：PT 卡的签到按钮回注的是**自然语言**「签到pt」，网关不认它、必然落进模型。
    没有该技能的机器上点一下 = 让模型空转烧 token（「误触模型」的根因）。
    所以按钮按能力渲染；点击时再校验一次，防「渲染时有、点击时没了」的旧卡。
    """
    try:
        root = Path(_HOME_DIR) / "skills"
        return (root / "pt-site-keepalive" / "SKILL.md").is_file() or any(
            root.glob("*/pt-site-keepalive/SKILL.md"))
    except Exception:
        return False


# 按钮能力表：按钮值里的 ``hermes_menu_require`` 指向这里的名字。
_CAPABILITIES = {"pt": _pt_ready}

_CAP_HINT = {
    "pt": "本机没有 PT 签到能力（未装 pt-site-keepalive 技能），已跳过——不会让模型空转。",
}


def _cap_ok(name: str) -> bool:
    """能力是否就绪。未登记的能力名一律放行（只拦明确登记过的）。"""
    fn = _CAPABILITIES.get(str(name))
    return True if fn is None else bool(fn())


# ── 卡片构件（schema 2.0：等宽按钮行 + 2×2 指标格 + 蓝灰分层）──────────
#
# 设计要点（来自官方设计规范 + 真机样张自检）：
#   · schema 2.0 才支持 background_style / body.padding / vertical_spacing；
#     1.0 的 action 标签在 2.0 已废弃 → 按钮一律走 column_set + width:auto/weighted。
#   · 按钮一行四个、等分等宽（weighted 1 + fill），标签两字，302px 手机宽度不折行。
#   · 指标用 2×2 网格：302px 下每格约 119px，数值单行放得下；蓝只做点缀（blue-50 + 蓝字）。
#   · 全卡 ≤1 条 hr，其余靠 vertical_spacing 与块底差异分区；长信息进折叠面板。

_ACCENT = "indigo"           # 品牌蓝（header / 强调数字）；= _DOM_ENTRY，面板卡用
_BLOCK = "grey-50"         # 中性块底
_BLOCK_ACCENT = "indigo-50"  # 强调块底
# 2026-10-04 配色收敛：7 色 → 3 个功能域色（OKLab 色差选型，两两最小 0.092；
# 收敛前有 4 对色差 < 0.10，面板与技能仅 0.043，肉眼等同）。
_DOM_ENTRY = "indigo"        # 入口/总览：面板、菜单速查、命令表
_DOM_DATA = "turquoise"    # 状态/数据：系统、用量、PT
#: tokens 口径唯一文案（2026-10-04 审计 C）：改口径只改这一处，三张卡共用。
_TOKENS_CALIBER = "含缓存读（与中转站一致）· 快照差值 · 不摊分"
_DOM_TOOL = "indigo"         # 工具/个人：技能、人格


def _btn(label: str, value: Dict[str, Any], kind: str = "default") -> Dict[str, Any]:
    return {
        "tag": "button",
        "type": kind,
        "size": "small",  # medium 在 302px 手机宽度下会把两字标签截成「新…」；small 字号+内边距都更小
        "width": "fill",
        "text": {"tag": "plain_text", "content": str(label)[:40]},
        "behaviors": [{"type": "callback", "value": value}],
    }


def _cmd_btn(label: str, cmd: str, kind: str = "default",
             require: str = "") -> Dict[str, Any]:
    """回注一条命令的按钮。``require`` 非空时，值里带能力名，点击侧会再校验一次。"""
    value: Dict[str, Any] = {"hermes_menu_cmd": cmd}
    if require:
        value["hermes_menu_require"] = require
    return _btn(label, value, kind)


def _refresh_btn(name: str) -> Dict[str, Any]:
    """统一的「🔄 刷新」按钮（2026-10-04 一致性修复）：全 9 张卡统一 primary_filled 蓝，
    避免面板/PT 两张卡灰色、其余蓝色。（原默认灰 = _btn 的 kind 缺省值。）"""
    return _btn("🔄 刷新", {"hermes_menu_refresh": name}, "primary_filled")


def _rows(buttons: List[Dict[str, Any]], per_row: int = 2) -> List[Dict[str, Any]]:
    """等宽按钮行：列 weighted 等分 + 按钮 fill → 同排宽度完全一致，不折行。

    默认每行 2 个：302px 手机宽度下四个按钮同排每格只剩约 63px，文字会被挤扁
    （「停止」这种实心按钮最明显）；2×2 后每格约 135px。用户 2026-09-30 选定此布局。
    """
    out: List[Dict[str, Any]] = []
    for i in range(0, len(buttons), per_row):
        chunk = buttons[i:i + per_row]
        out.append({
            "tag": "column_set", "flex_mode": "none", "background_style": "default",
            "horizontal_spacing": "8px",
            "columns": [{"tag": "column", "width": "weighted", "weight": 1, "elements": [b]}
                        for b in chunk],
        })
    return out


def _metric_row(*cells: Dict[str, Any]) -> Dict[str, Any]:
    return {"tag": "column_set", "flex_mode": "none", "background_style": "default",
            "horizontal_spacing": "8px", "columns": list(cells)}


def _md(text: str) -> Dict[str, Any]:
    return {"tag": "markdown", "content": text}


def _note(text: str) -> Dict[str, Any]:
    return {"tag": "div", "text": {"tag": "plain_text", "content": text, "text_size": "notation",
                                   "text_color": "grey-500"}}


def _panel_element(title: str, body: str, size: str = "notation",
                   expanded: bool = False) -> Dict[str, Any]:
    return {
        "tag": "collapsible_panel",
        "expanded": bool(expanded),
        "background_color": _BLOCK,
        "padding": "8px 8px 8px 8px",
        "border": {"color": "grey-300", "corner_radius": "6px"},
        "vertical_spacing": "8px",
        "header": {
            "title": {"tag": "markdown", "content": title},
            "background_color": "grey-100",
            "padding": "6px 8px 6px 8px",
            "vertical_align": "center",
            "width": "auto_when_fold",
            "icon": {"tag": "standard_icon", "token": "down-small-ccm_outlined",
                     "color": "grey-600", "size": "16px 16px"},
            "icon_position": "follow_text",
            "icon_expanded_angle": -180,
        },
        "elements": [{"tag": "markdown", "text_size": size, "content": body}],
    }


def _card(title: str, template: str, elements: List[Dict[str, Any]],
          subtitle: Optional[str] = None,
          tags: Optional[List[Tuple[str, str]]] = None) -> Dict[str, Any]:
    """骨架卡片。tags = 标题右侧状态标签 [(颜色, 文本)]，最多 3 个（2026-10-04 卡片化研究新增）。

    颜色只用 neutral / red：越界量给红、其余中性 —— 与这套卡片的克制蓝灰体系一致，不用绿。
    字段名 text_tag_list 为官方 2.0 头域能力，已用真卡实发验证（见本文件版本日志）。
    """
    el = list(elements)
    header: Dict[str, Any] = {
        "template": template,
        "padding": "12px 12px 12px 12px",
        "title": {"tag": "plain_text", "content": title},
    }
    if subtitle:
        header["subtitle"] = {"tag": "plain_text", "content": subtitle}
    if tags:
        header["text_tag_list"] = [
            {"tag": "text_tag", "text": {"tag": "plain_text", "content": str(c)[:24]},
             "color": str(k)}
            for k, c in list(tags)[:3]
        ]
    return {
        "schema": "2.0",
        "config": {"update_multi": True, "width_mode": "fill"},
        "header": header,
        "body": {"direction": "vertical", "padding": "12px 12px 12px 12px",
                 "vertical_spacing": "12px", "horizontal_spacing": "8px", "elements": el},
    }


def _zh_uptime(raw: str) -> str:
    """'up 1 week, 7 minutes' → '已运行 1 周'（认 year/month/week/day/hour/minute，中文卡不混英文）。"""
    s = raw or ""
    y = re.search(r"(\d+)\s*year", s)
    mo = re.search(r"(\d+)\s*month", s)
    wk = re.search(r"(\d+)\s*week", s)
    d = re.search(r"(\d+)\s*day", s)
    h = re.search(r"(\d+)\s*hour", s)
    m = re.search(r"(\d+)\s*minute", s)
    parts = []
    if y:
        parts.append(f"{y.group(1)} 年")
    if mo:
        parts.append(f"{mo.group(1)} 个月")
    if wk:
        parts.append(f"{wk.group(1)} 周")
    if d:
        parts.append(f"{d.group(1)} 天")
    if h:
        parts.append(f"{h.group(1)} 小时")
    if not parts and m:
        parts.append(f"{m.group(1)} 分钟")
    return "已运行 " + " ".join(parts) if parts else (s or "—")


_QUOTA_CACHE: Dict[str, Any] = _shared("quota_cache", lambda: {"ts": 0.0, "text": ""})


def _fmt_tokens(n: Any) -> str:
    """12345678 → '12.3M'（图表下方三格指标用）；None → '—'（读不到 ≠ 0）。"""
    if n is None:
        return "—"
    try:
        n = int(n or 0)
    except Exception:
        return "—"
    if n >= 1_000_000_000:
        return f"{n / 1e9:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    if n >= 1_000:
        return f"{n / 1e3:.0f}K"
    return str(n)


def _usage_snapshot_records() -> List[Dict[str, Any]]:
    """读用量快照文件（usage_snapshots.jsonl）：每行 {ts, sessions:{会话id: 累计tokens}}。

    由 systemd 定时器 hermes-usage-snapshot.timer 每 10 分钟追加一行（只读 state.db）。
    这是「今天用了多少 / 每天总量」唯一的真实数据源——Hermes 自己不存逐日切片。
    """
    import json as _json
    import os as _os

    home = Path(_os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
    path = home / "usage_snapshots.jsonl"
    recs: List[Dict[str, Any]] = []
    if not path.exists():
        return recs
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = _json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict) and rec.get("ts") and isinstance(rec.get("sessions"), dict):
                    recs.append(rec)
    except OSError:
        return recs
    recs.sort(key=lambda r: str(r["ts"]))
    return recs


def _snap_sum(rec: Any) -> Optional[Dict[str, int]]:
    """快照记录 → {会话id: 累计tokens}；坏值跳过。"""
    if not isinstance(rec, dict):
        return None
    out: Dict[str, int] = {}
    for k, v in (rec.get("sessions") or {}).items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


_CHANNEL_DEFS: List[Tuple[str, str, Tuple[str, ...]]] = [
    ("weixin", "📱 微信", ("weixin",)),
    ("telegram", "✈️ Telegram", ("telegram",)),
    ("feishu", "🐦 飞书", ("feishu",)),
    ("system", "🐾 系统", ("subagent", "cron", "oneshot", "cli", "tui", "local", "api", "")),
]


def _channel_of(src: Any) -> str:
    """会话 source → 渠道键（认不出的都归「系统」）。"""
    s = str(src or "").strip().lower()
    for key, _label, members in _CHANNEL_DEFS:
        if s in members:
            return key
    return "system"


def _ro_conn(home: Path):
    """state.db 只读连接（**带 timeout**：快照定时器会同时读同一个库，
    缺 timeout 时并发下会 'database is locked'，异常被上层吞掉后整张卡变空）。"""
    import sqlite3 as _sqlite
    return _sqlite.connect("file:%s?mode=ro" % (home / "state.db"), uri=True, timeout=15)


def _usage_stats(days: int = 7) -> Dict[str, Any]:
    """近 N 天 tokens + 逐渠道合计。

    口径 = **含缓存读**（input+output+cache_read），和中转站对齐——中转把缓存命中
    也算进 token 总量，所以只看 input+output 会少一个数量级。
    「累计」直接读 sessions 表（精确）；「今天」用快照差值（快照 v2 起才记 cache）。
    更早的日子没有快照 → 折线留空，不编数；全程不做任何摊分。
    """
    import datetime as _dt
    import os as _os

    now = _dt.datetime.now()
    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week0 = today0 - _dt.timedelta(days=now.weekday())
    home = Path(_os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))

    cur: Dict[str, int] = {}
    cur_io: Dict[str, int] = {}
    cur_cr: Dict[str, int] = {}
    meta: Dict[str, Dict[str, str]] = {}
    try:
        conn = _ro_conn(home)
        try:
            for sid, io, cr, title, disp, src in conn.execute(
                "SELECT id, COALESCE(input_tokens,0)+COALESCE(output_tokens,0),"
                " COALESCE(cache_read_tokens,0), COALESCE(title,''),"
                " COALESCE(display_name,''), COALESCE(source,'') FROM sessions"
            ):
                sid = str(sid)
                cur_io[sid] = int(io or 0)
                cur_cr[sid] = int(cr or 0)
                cur[sid] = cur_io[sid] + cur_cr[sid]
                meta[sid] = {"title": str(title), "disp": str(disp), "src": str(src)}
        finally:
            conn.close()
    except Exception:
        logger.warning("[FeishuMenuBridge] usage query failed", exc_info=True)

    recs = _usage_snapshot_records()

    def _has_cache(rec: Any) -> bool:
        return isinstance(rec, dict) and isinstance(rec.get("cache"), dict)

    def _at(iso: str) -> Optional[Dict[str, int]]:
        """ts <= iso 的最后一条快照，**只取输入+输出**（折线用，逐日可比）。"""
        pick = None
        for r in recs:
            if str(r["ts"]) <= iso:
                pick = r
            else:
                break
        return _snap_sum(pick)

    def _key(d) -> str:
        return d.isoformat()

    def _tot(rec: Optional[Dict[str, int]]) -> Optional[int]:
        return None if rec is None else sum(rec.values())

    bounds: Dict[str, Optional[Dict[str, int]]] = {}
    for off in range(days + 1):
        d = today0 - _dt.timedelta(days=off)
        bounds[_key(d)] = _at(d.isoformat(timespec="seconds"))

    first_today: Optional[Dict[str, int]] = None
    for r in recs:
        if str(r["ts"])[:10] == today0.strftime("%Y-%m-%d"):
            first_today = _snap_sum(r)
            break

    week = 0
    for off in range(days - 1, -1, -1):
        d = today0 - _dt.timedelta(days=off)
        # 2026-10-07 审计修复（#1）：日增量 = 本日 00:00 累计 → 次日 00:00 累计。
        # 原来下界取 bounds[d-1]（前一天 00:00）→ 窗口跨 2 天，逐日互相包含，
        # 累加后整周数字系统性接近翻倍。
        lo = bounds.get(_key(d))
        hi: Optional[Dict[str, int]] = cur_io if off == 0 else bounds.get(
            _key(d + _dt.timedelta(days=1)))
        if lo is None and off == 0:
            lo = first_today
        a, b = _tot(lo), _tot(hi)
        if a is None or b is None:
            continue
        val = max(0, b - a)
        if d >= week0:
            week += val

    # 今日基线：输入+输出用今天第一条快照（旧版就有）；缓存用今天第一条带 cache 的（v2 起）
    base_io: Dict[str, int] = {}
    base_cr: Dict[str, int] = {}
    since = ""
    for r in recs:
        if str(r["ts"])[:10] != today0.strftime("%Y-%m-%d"):
            continue
        if not base_io:
            base_io = _snap_sum(r) or {}
            since = str(r["ts"])[11:16]
        if not base_cr and _has_cache(r):
            base_cr = {str(k): int(v) for k, v in (r.get("cache") or {}).items()
                       if isinstance(v, (int, float))}
            since = str(r["ts"])[11:16]
            break

    rows: List[Dict[str, Any]] = []
    for sid, total in cur.items():
        m = meta.get(sid, {})
        rows.append({
            "id": sid,
            "label": (m.get("title") or m.get("disp") or sid[:12]),
            "source": m.get("src", ""),
            "channel": _channel_of(m.get("src")),
            # 批4-d（A1-B1/B2）：无当日基线时不拿「累计−0」冒充今日——记 None，卡片显示「—」；
            # 缓存基线缺失（当天还没有带 cache 的快照）时缓存差按 0，不把全量 cache_read 算进今日。
            "today": ((max(0, cur_io.get(sid, 0) - base_io.get(sid, 0))
                       + (max(0, cur_cr.get(sid, 0) - base_cr.get(sid, 0)) if base_cr else 0))
                      if base_io else None),
            "total": total,
        })
    rows.sort(key=lambda r: r["total"], reverse=True)

    chans: List[Dict[str, Any]] = []
    for key, label, _members in _CHANNEL_DEFS:
        mine = [r for r in rows if r["channel"] == key]
        chans.append({
            "key": key, "label": label, "sessions": len(mine),
            "today": (sum(int(r["today"]) for r in mine) if base_io else None),
            "total": sum(int(r["total"]) for r in mine),
        })

    return {
        "today": (sum(int(r["today"]) for r in rows) if base_io else None),
        "week": week,
        "total": sum(cur.values()), "sessions": rows, "channels": chans,
        "since": since, "snapshot_ok": bool(recs),
        "cr_base_missing": bool(base_io and not base_cr),
    }
def _quota_status(ttl: float = 600.0) -> str:
    """中转站额度概览（10 分钟缓存；只读探测，失败给 '—'）。"""
    now = time.time()
    if _QUOTA_CACHE.get("text") and (now - float(_QUOTA_CACHE.get("ts") or 0.0)) < ttl:
        return str(_QUOTA_CACHE["text"])
    text = "—"
    try:
        import os as _os
        import urllib.request as _ur

        home = Path(_os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        cfg = (home / "config.yaml").read_text(encoding="utf-8")
        m = re.search(r"(?m)^\s*base_url:\s*['\"]?(https?://[^\s'\"]+)", cfg)
        base = m.group(1).rstrip("/") if m else ""
        _ke = re.search(r"(?m)^\s*key_env:\s*['\"]?([A-Z0-9_]+)", cfg)
        _ke = _ke.group(1) if _ke else "OPENAI_API_KEY"
        key = (_os.environ.get(_ke) or "").strip()
        envf = home / ".env"
        if not key and envf.exists():
            em = re.search(r"(?m)^%s=(.*)$" % re.escape(_ke),
                           envf.read_text(encoding="utf-8", errors="ignore"))
            key = em.group(1).strip().strip('"').strip("'") if em else ""
        if base and key:
            req = _ur.Request(base + "/dashboard/billing/subscription")
            req.add_header("Authorization", "Bearer " + key)
            with _ur.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read() or b"{}")
            if float(data.get("hard_limit_usd") or 0) > 0:
                text = "充足"
    except Exception:
        logger.info("[FeishuMenuBridge] quota probe failed", exc_info=True)
    _QUOTA_CACHE.update(ts=now, text=text)
    return text


def _pct_num(pct: Any) -> float:
    """'34%' / '34' → 34.0；取不到给 0.0。"""
    try:
        return max(0.0, min(100.0, float(str(pct or "").strip().rstrip("%"))))
    except Exception:
        return 0.0


def _bar(pct: Any, width: int = 10, with_pct: bool = True) -> str:
    """百分比 → 文字进度条：34 → '▓▓▓░░░░░░░ 34%'（比例字号下仍读得出进度）。
    with_pct=False 只要方块本体（原来另有一份 _mini_bar，2026-10-04 审计后合并到此）。"""
    n = _pct_num(pct)
    full = int(round(n / 100.0 * width))
    bar = "▓" * full + "░" * (width - full)
    return bar + f" {int(round(n))}%" if with_pct else bar


def _pct_of(a: Any, b: Any) -> Optional[float]:
    """两个可读数字串（'≈20K' / '200K'）求百分比；任一取不到给 None。"""
    def num(x: Any) -> float:
        t = str(x or "").strip().lstrip("≈~").replace(",", "")
        mult = 1.0
        if t[-1:] in ("K", "k"):
            mult, t = 1e3, t[:-1]
        elif t[-1:] in ("M", "m"):
            mult, t = 1e6, t[:-1]
        return float(t) * mult
    try:
        d = num(b)
        if d <= 0:
            return None
        return max(0.0, min(100.0, num(a) / d * 100.0))
    except Exception:
        return None


def _usage_cell(k1: str, v: str, k2: str, accent: bool = False,
                vsize: str = "heading", tone: str = _ACCENT) -> Dict[str, Any]:
    """设计稿三行式格：上标签 / 数值 / 下标签（如 今日｜1.2M｜tokens）。

    tone = 功能域色（_DOM_ENTRY 蓝 / _DOM_DATA 青 / _DOM_TOOL 灰）：强调格底色与数字都用它。
    2026-10-04 由「六张卡各一色」收敛为 3 个功能域色。
    """
    return {
        "tag": "column", "width": "weighted", "weight": 1, "vertical_align": "center",
        "background_style": f"{tone}-50" if accent else _BLOCK,
        "padding": "10px 6px 10px 6px",
        "elements": [
            {"tag": "div", "text": {"tag": "plain_text", "content": k1, "text_size": "notation",
                                    "text_color": "grey-600", "text_align": "center"}},
            {"tag": "div", "text": {"tag": "plain_text", "content": v, "text_size": vsize,
                                    "text_color": tone if accent else "grey-900", "text_align": "center"}},
            {"tag": "div", "text": {"tag": "plain_text",
                                    "content": ("" if k2 is None else k2),
                                    "text_size": "notation",
                                    "text_color": "grey-600", "text_align": "center"}},
        ],
    }


def _model_line(chat_id: str = "") -> str:
    """「当前模型 + 上下文占用条」那一行 —— 面板卡与模型卡共用（改一处两边同变）。

    2026-10-04 审计：模型卡原来是照抄面板卡的一行，属于典型复制粘贴债。
    """
    ctx, limit = _session_ctx(chat_id)
    ctx_pct = _pct_of(ctx, limit)
    ctx_line = f"**上下文** {ctx} / {limit}" + (f"　{_bar(ctx_pct)}" if ctx_pct is not None else "")
    return f"🤖 **模型** `{_current_model()}`\n📚 " + ctx_line


def build_panel_card(chat_id: str = "") -> Dict[str, Any]:
    """设计稿 v7：后台/本会话 两格 + 模型/上下文（带占用条）+ 新会话/停止/刷新。
    资源明细只归「系统状态」卡、用量趋势只归「用量」卡，本卡不重复（2026-10-02）。
    2026-10-04：删掉「🤖 模型 ▾」按钮（和「设置 → 模型」的选择卡重复，用户提出）——
    模型那行保留（看当前模型 + 上下文占用），只是不再当入口。"""
    model = _current_model()
    bg = _bg_tasks()
    bg_v = "—" if bg < 0 else f"{bg} 个"
    bg_k = "🐾 正在忙" if bg > 0 else ("🐾 很清闲" if bg == 0 else "取不到")
    dur, start, nmsg = _session_info(chat_id)
    sess_k = f"{nmsg} · 起 {start}" if (nmsg != "—" and start != "—") else "本会话"
    el = [
        _metric_row(_usage_cell("⏳ 后台", bg_v, bg_k, accent=bg > 0),
                    _usage_cell("💬 本会话", dur, sess_k)),
        _md(_model_line(chat_id)),
        {"tag": "hr"},
    ]
    el += _rows([
        _cmd_btn("✨ 新会话", "/new", "primary_filled"),
        _cmd_btn("⏹ 停止", "/stop", "danger"),
        _refresh_btn("面板"),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("📊 控制台", _ACCENT, el, subtitle=f"刷新于 {_now_hm()}")


def build_system_card(chat_id: str = "") -> Dict[str, Any]:
    """设计稿 v7：磁盘/内存（带进度条）/负载/运行 四格 + 分区明细 + 刷新/详情/清理/收起。"""
    s = _host_stats()
    # 2026-10-04 审计修复：$HOME 不是独立挂载点时 df 会把同一分区打两遍（每个参数一行）——按设备去重。
    disk_detail = _run("df -h / $HOME 2>/dev/null | tail -n +2 | awk '!seen[$1]++'")
    load1 = (s["load"].split() or ["?"])[0]
    up = _zh_uptime(s["uptime"]).replace("已运行 ", "")
    el = [
        _metric_row(_usage_cell("💾 磁盘", s["disk_used"], _bar(s["disk_pct"]), tone=_DOM_DATA,
                                accent=_pct_num(s["disk_pct"]) >= 85),
                    _usage_cell("🧠 内存", s["mem_used"], _bar(s["mem_pct"]), tone=_DOM_DATA,
                                accent=_pct_num(s["mem_pct"]) >= 85)),
        _metric_row(_usage_cell("⚡ 负载", load1, "1 分钟"),
                    _usage_cell("⏱ 运行", up, "自上次重启", vsize="normal")),
        _panel_element("💽 **分区明细**", "```\n" + (disk_detail or "无数据")[:600] + "\n```"),
        {"tag": "hr"},
    ]
    el += _rows([
        _refresh_btn("系统"),
        _btn("📊 详情", {"hermes_menu_card": "系统详情"}),
        _cmd_btn("🧹 清理", "清理磁盘：先只做只读盘点并告诉我能回收多少，等我确认再删"),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("🖥 系统状态", _DOM_DATA, el, subtitle=f"刷新于 {_now_hm()}",
                 tags=[
                     ("red" if _pct_num(s["disk_pct"]) >= 85 else "neutral", f"磁盘 {s['disk_pct']}"),
                     ("red" if _pct_num(s["mem_pct"]) >= 85 else "neutral", f"内存 {s['mem_pct']}"),
                 ])


def _pick(pattern: str, text: str, default: str = "—") -> str:
    """从命令输出里抠第一捕获组；没匹配返回 default（卡片不显示空串/None）。"""
    m = re.search(pattern, text or "")
    return m.group(1) if m else default


def build_system_detail_card(chat_id: str = "") -> Dict[str, Any]:
    """「系统详情」卡：系统卡那颗「📊 详情」的落点 —— 把**主机这一层**摊开。

    2026-10-08 修复：系统卡的「📊 详情」原先误指向「洞察」卡（复制粘贴债），
    用户点「详情」看到的是用量洞察、与「洞察」按钮一模一样。本卡补上真正的系统详情；
    系统卡保持摘要四格（磁盘/内存/负载/运行），细节都收在这里。

    数据全部本机只读采集（``_run``），取不到显示「—」，不编造、不写盘、不改配置。
    """
    s = _host_stats()
    os_pretty = _run(". /etc/os-release 2>/dev/null && printf '%s' \"$PRETTY_NAME\"") or "—"
    kernel = _run("uname -sr") or "—"
    arch = _run("uname -m") or "—"
    host = _run("hostname") or "—"
    cpu_model = _run("grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//'") or "—"
    modules = _run("lsmod | tail -n +2 | wc -l") or "—"
    mem = _run("free -h | awk 'NR==2{print $3\"|\"$2\"|\"$7}'")
    m_used, m_total, m_avail = (mem.split("|") + ["—", "—", "—"])[:3]
    sw = _run("free -h | awk 'NR==3{print $3\"|\"$2}'")
    sw_used, sw_total = (sw.split("|") + ["—", "—"])[:2]
    df_out = _run("df -h -x tmpfs -x devtmpfs -x squashfs -x efivarfs -x overlay 2>/dev/null") or "（无数据）"
    ps_out = _run("ps -eo pid,comm,%cpu,%mem --sort=-%cpu 2>/dev/null | head -6") or "（无数据）"
    route = _run("ip route 2>/dev/null | grep -m1 default")
    gw, iface = _pick(r"via\s+(\S+)", route), _pick(r"dev\s+(\S+)", route)
    ips = _run("hostname -I 2>/dev/null").split()
    ip4 = next((x for x in ips if ":" not in x), "—")
    ip6 = next((x for x in ips if ":" in x), "")

    el: List[Dict[str, Any]] = [
        _panel_element("🧾 **主机**", "\n".join([
            "**主机**　`%s`" % host,
            "**系统**　%s" % os_pretty,
            "**内核**　`%s` · %s" % (kernel, arch),
            "**处理器**　%s（%s 核）" % (cpu_model, s.get("cpu", "?")),
            "**运行**　%s" % _zh_uptime(s.get("uptime", "")),
            "**内核模块**　%s 个" % modules,
        ]), expanded=True),
        _metric_row(
            _usage_cell("⚡ 负载", (s.get("load", "").split() or ["—"])[0], "1 / 5 / 15 分", tone=_DOM_DATA),
            _usage_cell("🧠 内存", m_used, "共 %s · 可用 %s" % (m_total, m_avail), tone=_DOM_DATA),
            _usage_cell("💱 交换", sw_used, "共 %s" % sw_total, tone=_DOM_DATA),
        ),
        _panel_element("💽 **挂载点明细**", "```\n%s\n```" % df_out[:700]),
        _panel_element("🔥 **占用最高的进程**", "```\n%s\n```" % ps_out[:700]),
        _panel_element("🌐 **网络**", "\n".join(
            ["**默认网关**　%s（%s）" % (gw, iface), "**本机地址**　%s" % ip4]
            + (["**IPv6**　%s" % ip6] if ip6 else [])
        )),
        _note("口径：本机实时只读读数；取不到的项显示「—」。磁盘/内存是整机口径，不是单进程。"),
        {"tag": "hr"},
    ]
    el += _rows([
        _refresh_btn("系统详情"),
        _btn("🖥 系统卡", {"hermes_menu_card": "系统"}),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    tags = []
    if _pct_num(s.get("disk_pct")) >= 85:
        tags.append(("red", "磁盘 %s" % s["disk_pct"]))
    if _pct_num(s.get("mem_pct")) >= 85:
        tags.append(("red", "内存 %s" % s["mem_pct"]))
    return _card("🧾 系统详情", _DOM_DATA, el,
                 subtitle="%s · 刷新于 %s" % (host, _now_hm()), tags=tags or None)


def build_pt_card(chat_id: str = "") -> Dict[str, Any]:
    """设计稿 v7：站点/已签到 两格（有失败才高亮）+ 最近一轮逐站明细 + 刷新/收起；
    PT 就绪（装了 pt-site-keepalive 技能）时多两个签到按钮。零数据时走空状态早返回。"""
    total_all = _pt_sites()
    run = _pt_last_run() or {}
    sites = [x for x in list(run.get("sites") or []) if isinstance(x, dict)]
    # 2026-10-05 修（X6-D31 re-base：X5 调整本块行序后适配）：分子 run["ok"] 与分母
    # sites.json 异源，站点清单增删时与下方逐站明细对不上；total==0 时还会渲染 "N/0"。
    # 2026-10-07 修：中途叫停的轮次只记了 6 站，用 len(sites) 当分母会渲染成 "6/6"
    # （看着像整轮全过）。分母改为优先用**本轮自己声明的 total**（与分子 run["ok"] 同源），
    # 再退回逐站条数，最后退回站点清单；两者皆无（total<=0）时不再拼假分数。
    total = int(run.get("total") or 0) or (len(sites) if sites else total_all)
    ok_n = int(run.get("ok") or 0)
    date = str(run.get("date") or "")
    end = str(run.get("ended") or "")
    running = bool(run) and not run.get("ended")   # 轮次进行中（未收口）
    done_v = (f"{ok_n}/{total}" if total > 0 else f"{ok_n}") if run else "—"
    done_k = (date + (" " + (end or "进行中") if (end or running) else "")).strip() or "尚无记录"
    if not run:
        # 2026-10-07 WS2：零数据时给「可操作的空状态」，而不是一张「? 站 + 空明细」的破卡。
        # 口径（用户 2026-10-07 定）：主卡只显示最基本的签到否；流式卡负责过程与魔力。
        # 本卡只读、不发起签到。
        if total_all > 0:
            el0 = [
                _metric_row(_usage_cell("🌐 站点", str(total_all), "已发现",
                                        accent=True, tone=_DOM_DATA),
                            _usage_cell("✅ 已签到", "—", "尚无记录",
                                        vsize="normal", tone=_DOM_DATA)),
                _note(f"已发现 {total_all} 个站点，但还没有签到记录——等待首次签到。"),
                _note("本卡只读，不发起签到。"),
            ]
        else:
            el0 = [
                _metric_row(_usage_cell("🌐 站点", "—", "未配置",
                                        accent=True, tone=_DOM_DATA),
                            _usage_cell("✅ 已签到", "—", "尚无记录",
                                        vsize="normal", tone=_DOM_DATA)),
                _note("未找到站点清单，PT 卡暂无数据。"),
                _panel_element("📥 **怎么接上数据**",
                               "1. 建数据目录 `~/.pt-sessions/state/`（或用环境变量 "
                               "`PT_SESSIONS_DIR` 指向别处）\n"
                               "2. 写站点清单 `state/sites.json`，内容为站点名数组，"
                               "如 `[\"站点A\", \"站点B\"]`\n"
                               "3. 每轮签到逐站写入记录（格式见仓库 `SETUP.md` 的 PT 章节），"
                               "卡面即自动显示进度。", expanded=True),
            ]
        el0 += _rows([_refresh_btn("PT"), _btn("✕ 收起", {"hermes_menu_close": True})])
        # 副标题也不能出现「? 站」——那正是本次要消灭的破卡形态（实测被验证脚本抓到）。
        sub0 = (f"{total_all} 站 · 尚无记录" if total_all else "尚无数据 · 等待接入")
        return _card("🌱 PT 签到", _DOM_DATA, el0, subtitle=sub0)

    lines: List[str] = []
    for it in sites:
        st = str(it.get("status") or "")
        word = _PT_STATUS_TEXT.get(st, st or "—")
        line = f"`{it.get('site', '?')}`　{word}"
        if it.get("note"):
            line += f"　{it['note']}"
        if it.get("time"):
            line += f"　{it['time']}"
        lines.append(("　" if st == "ok" else "") + line)
    bad = [lines[i] for i, it in enumerate(sites)
           if str(it.get("status") or "") in ("fail", "skip")]
    # 2026-10-04 用户要求：明细显示全部站点（原来截断到 8 行）；失败/跳过仍排在最前。
    body = "\n".join(bad + [x for x in lines if x not in bad])
    if not body:
        body = str(run.get("note") or "（本轮没有逐站记录）")
    el = [
        _metric_row(_usage_cell("🌐 站点", str(total) if total else "?", "已配置",
                                accent=True, tone=_DOM_DATA),
                    _usage_cell("✅ 已签到", done_v, done_k, accent=bool(bad),
                                vsize="normal", tone=_DOM_DATA)),
        # 2026-10-07：备注按能力二选一——没有签到能力时不该提「点全部签到」。
        _note("🚫 签到一律不走代理（避免国外 IP 触发风控）；点「全部签到」按顺序逐站跑一遍。"
              if _pt_ready() else
              "数据来自 $PT_SESSIONS_DIR/state/（默认 ~/.pt-sessions/state/）："
              "sites.json 存站点清单，checkin_runs.json 存每轮结果。本卡只读，不发起签到。"),
    ]
    # 2026-10-04：异常站改用表格（彩色状态标签 + 对齐更清楚），只列失败/跳过；
    # 全部通过时给一行确认，不占地方。数据源与下面的文字明细同一份（run["sites"]）。
    bad_sites = [it for it in sites if str(it.get("status") or "") in ("fail", "skip")]
    if bad_sites:
        el.append({
            "tag": "table", "page_size": 10, "row_height": "low",
            "header_style": {"text_align": "left", "text_size": "normal",
                             "background_style": "grey", "text_color": "grey",
                             "bold": True, "lines": 1},
            "columns": [
                {"name": "site", "display_name": "异常站点", "data_type": "text",
                 "horizontal_align": "left", "vertical_align": "center", "width": "auto"},
                {"name": "state", "display_name": "状态", "data_type": "options",
                 "horizontal_align": "left", "vertical_align": "center", "width": "auto"},
                {"name": "note", "display_name": "备注", "data_type": "text",
                 "horizontal_align": "left", "vertical_align": "center", "width": "auto"},
            ],
            "rows": [
                {"site": str(it.get("site") or "?"),
                 "state": [{"text": {"fail": "失败", "skip": "跳过"}.get(
                                str(it.get("status") or ""), "未知"),
                            "color": {"fail": "red", "skip": "orange"}.get(
                                str(it.get("status") or ""), "grey")}],
                 "note": "　".join(x for x in (str(it.get("note") or ""),
                                              str(it.get("time") or "")) if x) or "—"}
                for it in bad_sites
            ],
        })
    elif sites and not running and all(str(x.get("status") or "") == "ok" for x in sites):
        # 2026-10-04 审计 A1-B4 + X5-D16：必须**轮次已收口(ended)** 且逐站全 ok 才宣布「全部成功」，
        # 进行中轮次（started 有、ended 无）不得提前宣告成功，交给明细如实展示。
        el.append(_md(f"✅ 本轮 {len(sites)} 站全部签到成功" + (f"　{end}" if end else "")))
    el += [
        _panel_element("📋 **最近一轮明细**　" + (f"{len(sites)}/{total or '?'} 站" if sites else "未逐站记录"), body),
        {"tag": "hr"},
    ]
    # 2026-10-07：签到按钮按能力渲染——没装 PT 技能的机器上，这两个按钮回注的
    # 自然语言命令没人认，只能落进模型空转（「误触模型」）。能力在就显示、不在就不显示。
    _pt_btns = ([_cmd_btn("🌱 全部签到", "签到pt", "primary_filled", require="pt"),
                 _cmd_btn("🔍 只看失败", "签到pt，只看失败的", require="pt")]
                if _pt_ready() else [])
    el += _rows(_pt_btns + [
        _refresh_btn("PT"),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("🌱 PT 签到", _DOM_DATA, el, subtitle=f"{total if total else '?'} 站 · {date or '尚无记录'}")


def _skills_flat() -> List[Dict[str, str]]:
    """平铺技能清单 [(分类, 名字, SKILL.md 路径)]；分类按数量降序，分类内按名字排序。"""
    import os as _os

    try:
        home = Path(_os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        root = home / "skills"
        buckets: Dict[str, List[Tuple[str, Path]]] = {}
        for p in root.glob("*/*/SKILL.md"):
            buckets.setdefault(p.parent.parent.name, []).append((p.parent.name, p))
        for p in root.glob("*/SKILL.md"):
            buckets.setdefault("(未分类)", []).append((p.parent.name, p))
        out: List[Dict[str, str]] = []
        for cat, items in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
            for nm, p in sorted(items):
                out.append({"cat": cat, "name": nm, "path": str(p)})
        return out
    except Exception:
        logger.warning("[FeishuMenuBridge] 读技能目录失败", exc_info=True)
        return []


def _skill_desc(path: str) -> str:
    """SKILL.md frontmatter 里的 description（一行）。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            head = fh.read(1500)
        m = re.search(r"^description:\s*(.+)$", head, re.M)
        if not m:
            return ""
        return m.group(1).strip().strip('"').strip("'")
    except Exception:
        return ""


def build_skills_card(chat_id: str = "", page: int = 1) -> Dict[str, Any]:
    """技能全表（翻页）：每页 _SKILL_PAGE_SIZE 个，全宽按钮点了直接跑 + 一行描述。"""
    rows = _skills_flat()
    total = len(rows)
    cats = len({r["cat"] for r in rows})
    pages = max(1, (total + _SKILL_PAGE_SIZE - 1) // _SKILL_PAGE_SIZE) if total else 1
    try:
        page = min(max(1, int(page or 1)), pages)
    except Exception:
        page = 1
    chunk = rows[(page - 1) * _SKILL_PAGE_SIZE: page * _SKILL_PAGE_SIZE]

    el: List[Dict[str, Any]] = [
        _metric_row(_usage_cell("🧰 已装载", f"{total}", "个技能", accent=True, tone=_DOM_TOOL),
                    _usage_cell("🗂 分类", f"{cats}", "个分类", tone=_DOM_TOOL),
                    _usage_cell("📖 页码", f"{page}/{pages}", f"每页 {_SKILL_PAGE_SIZE} 个", tone=_DOM_TOOL)),
        _note("点技能名直接运行（等于发送 /技能名）；按钮下方一行是技能说明。"),
    ]
    last_cat = ""
    for r in chunk:
        if r["cat"] != last_cat:
            last_cat = r["cat"]
            el.append(_note(_CAT_EMOJI.get(r["cat"], "📦") + " " + _CAT_ZH.get(r["cat"], r["cat"])))
        el += _rows([_cmd_btn("▶ " + r["name"], "/" + r["name"])], per_row=1)
        d = _skill_zh(r["name"]) or _skill_desc(r["path"])
        if d:
            el.append(_note(d[:34]))
    _miss = _skill_zh_missing()
    if _miss:
        el.append(_note(f"⏳ 另有 {_miss} 条说明还没中文化：正在用你自己的模型自动补译"
                        f"（每次打开补 20 条），稍后重开这张卡即可看到中文。"))
    if not rows:
        el.append(_note("读不到技能目录，稍后再点一次。"))
    _nav = _nav_row("技能", page, pages)
    if _nav:
        el.append(_nav)
    el += _rows([
        _cmd_btn("🔍 搜索", "/help skills"),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    _skill_zh_autofill_kick()      # 非阻塞：本次没译完的，下次开卡继续补
    return _card("🧰 技能", _DOM_TOOL, el, subtitle=f"第 {page}/{pages} 页 · 共 {total} 个技能")


def build_help_card(chat_id: str = "") -> Dict[str, Any]:
    el: List[Dict[str, Any]] = [
        _metric_row(_usage_cell("🧭 菜单组", f"{len(GROUPS)}", "悬浮菜单",
                                accent=True, tone=_DOM_ENTRY),
                    _usage_cell("📋 菜单项", f"{sum(len(i) for _g, i in GROUPS)}", "点按即用",
                                tone=_DOM_ENTRY)),
        _note("点菜单即触发；下面按组展开看全部条目。"),
    ]
    for gname, items in GROUPS:
        body = "　".join(f"`{i}`" for i in items)
        el.append(_panel_element(f"{_GROUP_EMOJI.get(gname, '•')} **{gname}**　{len(items)} 项", body))
    el.append({"tag": "hr"})
    el += _rows([
        _btn("📜 命令表", {"hermes_menu_card": "命令表"}, "primary_filled"),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("❓ 菜单速查", _DOM_ENTRY, el, subtitle=f"5 组 × {sum(len(i) for _g, i in GROUPS)} 项")


def _mini_bar(pct: Any, width: int = 10) -> str:
    """比例 → 纯方块进度条（= _bar 不带百分号；保留这个名字是因为调用点很多）。"""
    return _bar(pct, width, with_pct=False)


# ── 批4-b：路径可迁移化（环境变量覆盖，默认=本机现值，行为零变化）──
_PT_DIR = os.environ.get("PT_SESSIONS_DIR") or os.path.expanduser("~/.pt-sessions")
_HOME_DIR = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")


def _detect_agent_dir() -> str:
    """Hermes 安装目录（`hermes_cli/`、`hermes_constants.py` 所在的那一层）。

    修因（2026-10-07 实测）：原来写死 `/usr/local/lib/hermes-agent`，装到
    pipx / venv / `~/.local` 的机器上会让两张卡**静默**降级 ——
    人格卡 14 → 0 个内置、命令表卡 67 → 23 条，且不报错，很难发现。

    优先级：
      1) 显式环境变量 `HERMES_AGENT_DIR`（存在即用，尊重用户/发行版选择）
      2) 直接问已装好的 `hermes_cli` 包（本插件就跑在 Hermes 进程里，最可靠）
      3) 扫 `sys.path`，找含 `hermes_cli/personality.py` 的目录
      4) 常见安装位置探测
      5) 退回历史默认值（与改前行为一致，不引入新失败模式）
    """
    env = (os.environ.get("HERMES_AGENT_DIR") or "").strip()
    if env and os.path.isdir(env):
        return env
    try:
        import hermes_cli  # type: ignore
        p = Path(getattr(hermes_cli, "__file__", "") or "")
        if p.name == "__init__.py":
            cand = p.parent.parent
            if (cand / "hermes_constants.py").exists() or (cand / "hermes_cli").is_dir():
                return str(cand)
    except Exception:
        pass
    try:
        for entry in list(sys.path):
            if not entry:
                continue
            if (Path(entry) / "hermes_cli" / "personality.py").exists():
                return str(Path(entry))
    except Exception:
        pass
    for cand in ("/usr/local/lib/hermes-agent", "/opt/hermes-agent",
                 os.path.expanduser("~/.local/share/hermes-agent"),
                 os.path.expanduser("~/hermes-agent")):
        if os.path.isdir(cand):
            return cand
    return env or "/usr/local/lib/hermes-agent"


_AGENT_DIR = _detect_agent_dir()
_PY_BIN = os.environ.get("HERMES_PYTHON") or "/usr/bin/python3"
_WAVE_STATE = _HOME_DIR + "/state/usage_wave.json"
_WAVE_CACHE: Dict[str, Any] = {}

#: PT 签到状态 → 中文文案（2026-10-04 审计：原来文字映射在 PT 卡里抄了两处）。
_PT_STATUS_TEXT: Dict[str, str] = {"ok": "已签到", "fail": "失败", "skip": "跳过"}


def _wave_state() -> Dict[str, Any]:
    """状态文件（按 (mtime, size) 缓存 —— 点按路径每次渲染都要读一遍，别反复吃盘）。"""
    try:
        stt = os.stat(_WAVE_STATE)
        sig = (stt.st_mtime_ns, stt.st_size)
        if _WAVE_CACHE.get("sig") == sig:
            return _WAVE_CACHE.get("data") or {}
        with open(_WAVE_STATE, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            data = {}   # 2026-10-04 审计修复：合法 JSON 但非 dict（如 [1]）会让下游 .get 崩
        _WAVE_CACHE["sig"], _WAVE_CACHE["data"] = sig, data
        return data
    except Exception:
        return {}


# ── 波形口径共享模块（纯 stdlib；与 tools/usage_wave.py 是同一份实现）──────────
# 2026-10-04 审计 P2：以前「抬头的合计/口径句、图表结构、k 单位」在本插件与
# usage_wave.py 各写一份，改一处忘一处（已实际分叉过一次）。现在只有一份。
_WAVE_SHARED_PATH = _HOME_DIR + "/tools/wave_shared.py"


def _load_wave_shared():
    """加载共享口径模块；失败返回 None（不因此炸掉网关，只在日志里留痕）。"""
    try:
        import importlib.util as _iu
        spec = _iu.spec_from_file_location("wave_shared", _WAVE_SHARED_PATH)
        if spec is None or spec.loader is None:
            return None
        mod = _iu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        logger.warning("[FeishuMenuBridge] wave_shared 加载失败（用量波形块会隐藏）",
                       exc_info=True)
        return None


_WS = _load_wave_shared()


def _fmt_rounds(n: Any) -> str:
    """用量数值：优先用共享实现（与波形图/图表完全同口径），共享缺失时退回本地算法。"""
    if _WS is not None:
        try:
            return _WS.fmt_k(n)
        except Exception:
            pass
    try:
        v = float(n or 0)
    except (TypeError, ValueError):
        return str(n)
    if v >= 1000:
        return ("%.1f" % (v / 1000.0)).rstrip("0").rstrip(".") + "k"
    return "%d" % round(v)


def _wave_asof(wst: Dict[str, Any]) -> str:
    """批4-c：波形数据的「截至时刻」标注——快照不是实时，必须让人一眼看见时效。"""
    try:
        _g = str((wst or {}).get("generated_at") or "")
        if len(_g) >= 16:
            # 2026-10-04 修：usage_wave.py 写的是带 +02:00 偏移的 aware ISO（其 TZ 固定 +2）。
            # 原实现裸切片且假定已是本地时 → DST 切换/环境时区不同时「数据截至」整体偏。
            # 改为 ISO 解析 + astimezone() 归一到本机真实时区；解析失败退回原切片逻辑。
            _hm = ""
            try:
                from datetime import datetime as _dt, timezone as _tzm
                _t = (_g[:-1] + "+00:00") if _g.endswith("Z") else _g
                _dto = _dt.fromisoformat(_t)
                if _dto.tzinfo is None:
                    _dto = _dto.replace(tzinfo=_tzm.utc)
                _loc = _dto.astimezone()
                _hm = _loc.strftime("%H:%M")
                _d = _loc.strftime("%m/%d")
                _today = _dt.now().strftime("%m/%d")
            except Exception:
                pass
            if not _hm:
                _hm = _g[11:16]
                _d = _g[5:10].replace("-", "/")
                _today = time.strftime("%Y-%m-%d")[5:10].replace("-", "/")
            _when = ("今天 " if _d == _today else (_d + " ")) + _hm
            return "\n_数据截至 %s（点刷新按钮或切换档位更新）_" % _when
    except Exception:
        pass
    return ""


def _wave_block() -> List[Dict[str, Any]]:
    """用量卡顶部的波形块：**原生图表** + 四档按钮。

    文案/图表结构/单位全部来自 wave_shared（与 usage_wave.py 同一份，不再各写一套）；
    数据取自 usage_wave.py 的状态文件（真实 token，不重算）。
    按钮回调走 hermes_menu_wave，和独立波形卡同一套逻辑。
    """
    if _WS is None:
        # 修因（2026-10-07）：原来静默 return []，别人机器上没有 tools/wave_shared.py
        # 时波形块凭空消失、卡片看着像坏了。现在给一行可读的说明。
        return [
            {"tag": "markdown", "element_id": "wave_missing",
             "content": "_🌊 波形块未启用：本机缺少 `tools/wave_shared.py`（可选增强，"
                        "卡片其余部分不受影响）。_"},
            {"tag": "hr"},
        ]
    wst = _wave_state()
    rng = str(wst.get("current") or _WS.ORDER[0])
    info = (wst.get("ranges") or {}).get(rng) or {}
    vals = info.get("vals") or []
    labels = info.get("labels") or []
    if not vals or not labels:
        logger.info("[FeishuMenuBridge] 波形块跳过：档位 %s 缺 vals/labels（状态文件没就绪？）", rng)
        return [
            {"tag": "markdown", "element_id": "wave_nodata",
             "content": "_🌊 波形块暂无数据（`state/usage_wave.json` 还没有这个档位的记录）。_"},
            {"tag": "hr"},
        ]
    opts = []
    for lb, n in zip(_WS.range_labels(rng), _WS.ORDER):
        opts.append({"text": {"tag": "plain_text",
                              "content": str(lb) + ("　— 当前" if n == rng else "")},
                     "value": json.dumps({"hermes_menu_wave": n}, ensure_ascii=False)})
    return [
        {"tag": "markdown", "element_id": "wave_head",
         "content": _WS.head_content(rng, info.get("total"), "**🌊 用量波形 · Token**　")},
        _WS.chart_el(rng, vals, labels, "wave_chart"),
        {"tag": "select_static", "element_id": "wave_sel", "width": "fill",
         "placeholder": {"tag": "plain_text", "content": "切换档位（当前 %s）" % rng},
         "options": opts},
        {"tag": "markdown", "element_id": "wave_foot",
         "content": "下拉切换档位（只有这块会动，卡片其余部分不动）。" + _wave_asof(wst)},
        {"tag": "hr"},
    ]


def build_usage_card(chat_id: str = "") -> Dict[str, Any]:
    """设计稿 v9「用量」：波形图（顶部）+ 按渠道分组（微信 / Telegram / 飞书 / 系统）。

    口径 = 含缓存读，和中转站一致（详见 _usage_stats）。全部真实值，不摊分。
    会话明细收进折叠栏并按渠道归类，不再平铺 100 多个会话。
    2026-10-04 用户要求：去掉原来那条 token 折线（和顶部波形图重复），只留波形图。
    """
    st = _usage_stats(7)
    chans = st.get("channels") or []
    rows = st.get("sessions") or []
    top = max([int(c.get("total") or 0) for c in chans] or [1]) or 1

    def _clean(text: Any) -> str:
        out = str(text or "")
        for ch in ("*", "_", "`", "[", "]"):
            out = out.replace(ch, "")
        return out.strip() or "未命名"

    def _chan_body(key: str, empty: str) -> str:
        items = [c for c in chans if int(c.get(key) or 0) > 0]
        if not items:
            return empty
        return "\n".join(
            "%s　%s　**%s**" % (c["label"], _mini_bar(int(c[key]) / top * 100.0), _fmt_tokens(c[key]))
            for c in items
        )

    def _detail_body() -> str:
        out: List[str] = []
        for c in chans:
            mine = [r for r in rows if r["channel"] == c["key"] and int(r["total"]) > 0]
            if not mine:
                continue
            out.append("**%s**　%d 个会话 · %s" % (c["label"], len(mine), _fmt_tokens(c["total"])))
            for r in mine[:3]:
                out.append("　%s　%s" % (_clean(r["label"])[:22], _fmt_tokens(r["total"])))
            if len(mine) > 3:
                out.append("　_其余 %d 个　%s_" % (len(mine) - 3,
                                                  _fmt_tokens(sum(int(r["total"]) for r in mine[3:]))))
        return "\n".join(out) if out else "还没有会话数据。"

    if not st.get("snapshot_ok"):
        note = "口径：%s · 快照尚未就绪，今日数据稍后出现" % _TOKENS_CALIBER
    elif st.get("since"):
        note = ("口径：%s · 今日的缓存部分自 %s 起算"
                "（此前快照不记缓存）" % (_TOKENS_CALIBER, st["since"]))
    else:
        note = "口径：%s · 全部真实值" % _TOKENS_CALIBER
    if st.get("cr_base_missing"):
        note += " · 今日缓存基线未就绪（缓存差暂未计入）"

    el: List[Dict[str, Any]] = _wave_block() + [
        _metric_row(_usage_cell("📅 今日", ("—（快照未就绪）" if st["today"] is None else _fmt_tokens(st["today"])),
                                "本周 %s · 仅输入+输出" % _fmt_tokens(st["week"]),
                                accent=True, tone=_DOM_DATA),
                    _usage_cell("📚 累计", _fmt_tokens(st["total"]), "含缓存读", tone=_DOM_DATA),
                    _usage_cell("💳 额度", _quota_status(), "未限流", tone=_DOM_DATA)),
        _panel_element("📊 按渠道 · 累计", _chan_body("total", "还没有数据。"), expanded=True),
        _panel_element("🕐 今天 · 按渠道", _chan_body("today", "今天还没有新增消耗。")),
        _panel_element("🗂 会话明细 · 按渠道", _detail_body()),
        _note(note),
        {"tag": "hr"},
    ]
    el += _rows([
        _refresh_btn("用量"),
        _btn("🔍 洞察", {"hermes_menu_card": "洞察"}),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("📈 用量", _DOM_DATA, el,
                 subtitle="%d 个渠道 · %d 个会话 · 含缓存" % (len(chans), len(rows)))


_PERSONALITY_SRC = _AGENT_DIR + "/hermes_cli/personality.py"


def _personality_rows() -> List[Dict[str, str]]:
    """内置人格清单：静态解析 personality.py 的 BUILTIN_PERSONALITIES（零依赖）。"""
    import ast
    import os

    rows: List[Dict[str, str]] = []
    if not os.path.isfile(_PERSONALITY_SRC):
        return rows
    try:
        with open(_PERSONALITY_SRC, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            targets = node.targets if isinstance(node, ast.Assign) else (
                [node.target] if isinstance(node, ast.AnnAssign) else [])
            if not any(getattr(t, "id", "") == "BUILTIN_PERSONALITIES" for t in targets):
                continue
            if isinstance(node.value, ast.Dict):
                for k, v in zip(node.value.keys, node.value.values):
                    if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                        rows.append({"name": str(k.value), "preview": str(v.value)})
    except Exception:
        logger.warning("[FeishuMenuBridge] 解析内置人格表失败", exc_info=True)
    return rows


def _active_personality() -> str:
    """config.yaml 的 display.personality（没设就空串）。"""
    import os

    try:
        home = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
        with open(os.path.join(home, "config.yaml"), "r", encoding="utf-8") as fh:
            txt = fh.read()
        m = re.search(r"^\s{2}personality:\s*(.*)$", txt, re.M)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def build_personality_card(chat_id: str = "", page: int = 1) -> Dict[str, Any]:
    """内置人格清单（翻页）：当前项打勾，点按钮即切换（/personality <名字>）。"""
    rows = _personality_rows()
    cur = _active_personality()
    # 内置人格的中文说明：对照 personality.py 的 BUILTIN_PERSONALITIES 原文意译；
    # 表里没有的名字（如用户自定义人格）回退显示原始 preview，不编造。
    _zh = {
        "helpful": "友好、乐于助人的通用助手。",
        "concise": "回答简短、直奔要点。",
        "technical": "技术专家，给详尽准确的技术细节。",
        "creative": "脑洞大开，给有创意的方案。",
        "teacher": "耐心的老师，用例子把概念讲清楚。",
        "kawaii": "可爱风：颜文字 + 闪闪发光的热情语气。",
        "catgirl": "猫娘：nya~ 口癖 + 猫脸颜文字，俏皮好奇。",
        "pirate": "海盗船长口吻：航海黑话 + Yo ho ho。",
        "shakespeare": "莎翁腔：华丽辞藻与戏剧独白。",
        "surfer": "冲浪风：超 chill 的美式口语。",
        "noir": "黑色电影旁白：侦探腔 + 氛围感。",
        "uwu": "卖萌风：uwu~ 软糯口癖。",
        "philosopher": "哲人：爱追问意义与本质。",
        "hype": "亢奋风：全大写 + 满格能量。",
    }
    # 每页 8 个：内置 14 个 → 2 页（若沿用 _PAGE_SIZE=15 会一页装完，达不到缩短卡片的目的）
    per_page = 8
    total = len(rows)
    pages = max(1, (total + per_page - 1) // per_page) if total else 1
    try:
        page = min(max(1, int(page or 1)), pages)
    except Exception:
        page = 1
    chunk = rows[(page - 1) * per_page: page * per_page]

    el: List[Dict[str, Any]] = [
        _metric_row(_usage_cell("🎭 当前", cur or "未设置", "display.personality",
                                accent=not cur, tone=_DOM_TOOL),
                    _usage_cell("📚 可选", f"{total}", "个内置人格", tone=_DOM_TOOL),
                    _usage_cell("📖 页码", f"{page}/{pages}", f"每页 {per_page} 个", tone=_DOM_TOOL)),
        _note("这里切的是内置人格预设；自定义人设（SOUL.md），不受影响。"),
        _note("点人格名即切换（等于发送 /personality <名字>），按钮下方一行是该人格的中文说明。"),
    ]
    if not rows:
        el.append(_note("读不到内置人格表（版本变动？），可以直接发 /人格 看清单。"))
    for r in chunk:
        is_cur = r["name"] == cur
        el += _rows([_cmd_btn(f"🎭 {r['name']}" + ("　✓ 当前" if is_cur else ""),
                              "/personality " + r["name"],
                              "primary_filled" if is_cur else "default")], per_row=1)
        desc = _zh.get(r["name"]) or (r["preview"][:40] if r["preview"] else "")
        if desc:
            el.append(_note(desc))
    _nav = _nav_row("人格", page, pages)
    if _nav:
        el.append(_nav)
    el += _rows([
        _cmd_btn("🚫 关闭人格", "/personality none"),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("🎭 人格", _DOM_TOOL, el,
                 subtitle=f"第 {page}/{pages} 页 · 共 {total} 个内置 · 当前 {cur or '未设置'}")


# ── 推理卡 ──────────────────────────────────────────────────────
#: 档位真源：hermes_constants.VALID_REASONING_EFFORTS（/reasoning 命令接受的取值）
_REASONING_SRC = _AGENT_DIR + "/hermes_constants.py"
#: /reasoning 的关闭取值：parse_reasoning_effort 把 none/false/disabled 归一为「禁用」
_REASONING_OFF = "none"
#: 源码解析失败时的兜底档位，与 hermes_constants.VALID_REASONING_EFFORTS 逐字一致
_REASONING_FALLBACK = ("minimal", "low", "medium", "high", "xhigh", "max", "ultra")


def _reasoning_levels() -> List[str]:
    """真实可选档位：静态解析 hermes_constants.VALID_REASONING_EFFORTS（零依赖、不 import）。"""
    import ast as _ast
    import os as _os

    if _os.path.isfile(_REASONING_SRC):
        try:
            with open(_REASONING_SRC, "r", encoding="utf-8") as fh:
                tree = _ast.parse(fh.read())
            for node in tree.body:
                targets = node.targets if isinstance(node, _ast.Assign) else (
                    [node.target] if isinstance(node, _ast.AnnAssign) else [])
                if not any(getattr(t, "id", "") == "VALID_REASONING_EFFORTS" for t in targets):
                    continue
                if isinstance(node.value, (_ast.Tuple, _ast.List)):
                    vals = [str(e.value) for e in node.value.elts if isinstance(e, _ast.Constant)]
                    if vals:
                        return vals
        except Exception:
            logger.warning("[FeishuMenuBridge] 解析 VALID_REASONING_EFFORTS 失败", exc_info=True)
    return list(_REASONING_FALLBACK)


def _reasoning_current() -> str:
    """当前推理档位：config.yaml 顶层 ``agent.reasoning_effort``；读不到返回空串（卡上显示 —）。"""
    import os as _os

    try:
        home = _os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
        with open(_os.path.join(home, "config.yaml"), "r", encoding="utf-8") as fh:
            txt = fh.read()
    except Exception:
        return ""
    block = re.search(r"(?ms)^agent:\s*\n((?:[ \t]+.*\n|\s*\n)*)", txt)
    scope = block.group(1) if block else txt
    m = re.search(r"(?m)^[ \t]+reasoning_effort:\s*(.*)$", scope)
    if not m:
        return ""
    return m.group(1).strip().strip('"').strip("'")


def build_reasoning_card(chat_id: str = "", cur_override: Optional[str] = None) -> Dict[str, Any]:
    """推理档位点选卡：当前档打勾，点按钮即切换（/reasoning <真实取值> --global）。

    取值真源 = hermes_constants.VALID_REASONING_EFFORTS + 「关闭」(none)；档位从源码静态解析，
    避免与命令端漂移。当前档从 config.yaml 的 agent.reasoning_effort 读。

    2026-10-04 修：`/reasoning <档位>` 不带 --global 时只作用于**本会话**（cli_commands_mixin.py
    的 explicit_global 分支），而本卡读的是**配置文件** —— 于是点了 ultra 生效了、卡上却还勾着 max。
    现在按钮一律发 `--global`，写文件 + 本卡读文件，两边永远一致（也顺带让它跨重启保留）。
    """
    levels = _reasoning_levels()
    # cur_override：乐观渲染用（点击那刻先按意图画上，稍后用真实配置校验校正）
    cur_raw = str(cur_override) if cur_override else _reasoning_current()
    # 2026-10-04 修：官方 parse_reasoning_effort 把 none/false/disabled 三者都归一为「禁用」，
    # 且 /reasoning false --global 会把 "false" 原样写进 config → 旧逻辑当未知档：刻度全空、无勾、无中文。
    # 展示侧统一归一到关闭档 "none"（_REASONING_ZH 已含 "none": "关闭"）。
    cur = _REASONING_OFF if cur_raw.strip().lower() in ("false", "disabled") else cur_raw
    cur_shown = cur or "—"
    _seq = [_REASONING_OFF] + [str(lv) for lv in levels]      # 关闭 + 7 档 = 8 格刻度
    try:
        _ci = _seq.index(str(cur))
    except ValueError:
        _ci = -1
    _scale = "".join("▰" if 0 <= i <= _ci else "▱" for i in range(len(_seq)))
    _zh_cur = _REASONING_ZH.get(str(cur), "")
    el: List[Dict[str, Any]] = [
        _md("🧠 **当前推理档位：%s**%s\n`%s`　轻 → 重" % (
            cur_shown, ("　（%s）" % _zh_cur) if _zh_cur else "", _scale)),
        _metric_row(_usage_cell("🎚 档位阶梯", f"{len(levels)} 档", "外加「关闭」", tone=_DOM_ENTRY),
                    _usage_cell("⏱ 代价", "越高越慢", "思考与用量 ↑", tone=_DOM_ENTRY)),
        _note("点档位即切换推理强度（全局写入配置文件，对所有会话生效）；「关闭」= 不请求推理。"),
    ]
    # 档位格阵（4×2 紧凑 chip）：一眼看全 8 档，当前档实心高亮；替代原生下拉
    # （2026-10-04：下拉弹层是飞书原生控件、样式改不了，用户要求美化 → 回到卡内视觉格阵）。
    _all_opts: List[Tuple[str, str]] = []
    for lv in levels:
        # 标签只留「emoji + 英文档名」：2 列宽度下「英文+中文」双拼必被省略号截断（实测）
        _all_opts.append((str(lv), "%s %s" % (_REASONING_EMOJI.get(str(lv), "•"), lv)))
    _all_opts.append((_REASONING_OFF, "🚫 关闭"))
    _btns: List[Dict[str, Any]] = [
        _cmd_btn(lb, f"/reasoning {key} --global",
                 "primary_filled" if key == cur else "default")
        for key, lb in _all_opts
    ]
    el += _rows(_btns, per_row=2)          # 2 列 × 4 行：4 列会被飞书压缩到看不清
    el += _rows([_btn("✕ 收起", {"hermes_menu_close": True})], per_row=1)
    return _card("🧠 推理", _DOM_ENTRY, el,
                 subtitle=f"当前 {cur_shown} · 共 {len(levels) + 1} 档")


# ── 命令表卡（第一张翻页卡：框架见 _nav_row / hermes_menu_page） ──────

# 技能卡：每页 5 个（2026-10-04 用户要求「五个一页，8 个还是太长」——
# 15 条/页时整卡过高，每条 = 按钮 + 说明两行，所以单列一档）。
# 命令表（_PAGE_SIZE）与人格（自带 per_page=8）各有自己的常量。
# 2026-10-04 用户要求：命令表也改成 5 条/页 + 「和技能一样的显示效果」（全宽按钮 + 说明行）。
_SKILL_PAGE_SIZE = 5
_PAGE_SIZE = 5


#: 命令注册表的分类英文标识 → 中文（commands.py 的 _CATEGORY_SLUGS 只做 i18n，这里直接给中文）
_CMD_CAT_ZH = {
    "Session": "会话", "Configuration": "配置", "Info": "信息",
    "Tools & Skills": "工具与技能", "Plugins": "插件", "Exit": "退出",
    "Context": "上下文", "Background & Automation": "后台与自动化",
}

#: 分类英文标识 → i18n slug（与 commands.py 的 _CATEGORY_SLUGS 一致）
_CMD_CAT_SLUG = {
    "Session": "session", "Configuration": "configuration", "Info": "info",
    "Tools & Skills": "tools_skills", "Plugins": "plugins", "Exit": "exit",
    "Context": "context", "Background & Automation": "background_automation",
}

_REGISTRY_CANDIDATES = (_AGENT_DIR + "/hermes_cli/commands.py",)


def _registry_path() -> str:
    import os
    for p in _REGISTRY_CANDIDATES:
        if os.path.isfile(p):
            return p
    try:
        import hermes_cli  # noqa: PLC0415
        cand = os.path.join(os.path.dirname(os.path.abspath(hermes_cli.__file__)), "commands.py")
        if os.path.isfile(cand):
            return cand
    except Exception:
        pass
    return ""


def _command_rows() -> List[Dict[str, str]]:
    """命令表数据源。

    直接 `import hermes_cli.commands` 会连带拉 ruamel（本机网关环境没装）→ 改成**静态解析**注册表
    源文件里的 `CommandDef(...)` 字面量：只读、无副作用、不依赖第三方包。
    解析不出来时退回悬浮菜单那 23 项，保证卡片不空。
    """
    import ast
    rows: List[Dict[str, str]] = []
    # 描述/分类走 Hermes 自己的 i18n（网关进程里可用）；拿不到就退回英文原文
    i18n_t = None
    try:
        try:
            import hermes_bootstrap  # noqa: F401
        except Exception:
            pass
        from agent.i18n import t as _t  # noqa: PLC0415
        i18n_t = _t
    except Exception:
        i18n_t = None
    path = _registry_path()
    if path:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "CommandDef"):
                    continue
                vals: Dict[str, Any] = {}
                for i, a in enumerate(node.args[:3]):
                    if isinstance(a, ast.Constant):
                        vals[("name", "description", "category")[i]] = a.value
                for kw in node.keywords:
                    if isinstance(kw.value, ast.Constant):
                        vals[str(kw.arg)] = kw.value.value
                if not vals.get("name") or vals.get("cli_only"):
                    continue
                cat = str(vals.get("category") or "")
                desc = str(vals.get("description") or "")
                if i18n_t is not None:
                    kd = "slash.%s.description" % vals["name"]
                    try:
                        v = str(i18n_t(kd) or "")
                        if v and v != kd:
                            desc = v
                    except Exception:
                        pass
                    slug = _CMD_CAT_SLUG.get(cat)
                    if slug:
                        kc = "slash.category." + slug
                        try:
                            v = str(i18n_t(kc) or "")
                            if v and v != kc:
                                cat = v
                        except Exception:
                            pass
                rows.append({
                    "name": "/" + str(vals["name"]),
                    "args": str(vals.get("args_hint") or ""),
                    "desc": desc,
                    "cat": _CMD_CAT_ZH.get(cat, cat),
                })
        except Exception:
            logger.warning("[FeishuMenuBridge] 解析命令注册表失败", exc_info=True)
    if not rows:
        for gname, items in GROUPS:
            for nm in items:
                rows.append({"name": "/" + nm, "args": "",
                             "desc": "悬浮菜单项 / 中文别名", "cat": gname})
    return rows


async def _patch_card(adapter: Any, message_id: str, card: Dict[str, Any]) -> Tuple[bool, str]:
    """就地更新一张卡片消息（翻页 / 刷新用）。

    飞书把「改卡片」放在 PATCH /open-apis/im/v1/messages/{id}，body 只有 content；
    PUT（SDK 的 message.update）只改文本/富文本——对它传 msg_type=interactive 会报
    230001 "invalid msg_type"。所以必须走 patch，别用 update。
    """
    from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody

    body = PatchMessageRequestBody.builder().content(
        json.dumps(card, ensure_ascii=False)).build()
    req = PatchMessageRequest.builder().message_id(message_id).request_body(body).build()
    resp = await adapter._run_blocking(adapter._client.im.v1.message.patch, req)
    ok = _send_ok(resp)
    return ok, "code=%s msg=%s" % (getattr(resp, "code", None), getattr(resp, "msg", None))


def _nav_row(card: str, page: int, pages: int) -> Optional[Dict[str, Any]]:
    """‹ 上一页 / 下一页 ›：就地翻页（同一张卡走 PATCH，见 `_patch_card`；PUT message.update 对 interactive 报 230001）。

    只有一页时**整行不显示**（返回 None，调用方跳过）——省得观感上多一行废按钮。
    """
    if pages <= 1:
        return None
    cols: List[Dict[str, Any]] = []
    if page > 1:
        cols.append({"tag": "column", "width": "weighted", "weight": 1,
                     "elements": [_btn("‹ 上一页",
                                       {"hermes_menu_page": {"card": card, "page": page - 1}})]})
    if page < pages:
        cols.append({"tag": "column", "width": "weighted", "weight": 1,
                     "elements": [_btn("下一页 ›",
                                       {"hermes_menu_page": {"card": card, "page": page + 1}},
                                       "primary_filled")]})
    if not cols:
        return None
    return {"tag": "column_set", "flex_mode": "none", "columns": cols}


def build_commands_card(chat_id: str = "", page: int = 1) -> Dict[str, Any]:
    rows = _command_rows()
    total = len(rows)
    pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE) if total else 1
    try:
        page = min(max(1, int(page or 1)), pages)
    except Exception:
        page = 1
    chunk = rows[(page - 1) * _PAGE_SIZE: page * _PAGE_SIZE]

    el: List[Dict[str, Any]] = []
    _nav: Optional[Dict[str, Any]] = None      # 空数据分支不赋它，下面 if _nav 才不会 NameError/UnboundLocalError
    if not rows:
        el.append(_note("暂时读不到命令注册表（网关升级中/未就绪），稍后再点一次。"))
    else:
        el.append(_metric_row(
            _usage_cell("📜 命令", f"{total}", "聊天可用", accent=True, tone=_DOM_ENTRY),
            _usage_cell("📖 页码", f"{page}/{pages}", f"每页 {_PAGE_SIZE} 条", tone=_DOM_ENTRY)))
        last_cat = ""
        for r in chunk:
            if r["cat"] and r["cat"] != last_cat:
                last_cat = r["cat"]
                el.append(_note("— " + last_cat + " —"))
            nm = str(r["name"])
            if not nm.startswith("/"):
                nm = "/" + nm
            el += _rows([_cmd_btn("▶ " + nm, nm)], per_row=1)
            bits = []
            if r["args"]:
                bits.append("参数 " + str(r["args"]))
            if r["desc"]:
                bits.append(str(r["desc"])[:40])
            if bits:
                el.append(_note("　".join(bits)))
        _nav = _nav_row("命令表", page, pages)
    if _nav:
        el.append(_nav)
    el.append(_btn("✕ 收起", {"hermes_menu_close": True}))
    return _card("📜 命令表", _DOM_ENTRY, el,
                 subtitle=f"第 {page}/{pages} 页 · 共 {total} 条")


def build_status_card(chat_id: str = "") -> Dict[str, Any]:
    """「状态」卡：/status 的可视版（模型 / 后台 / 本会话 / 消息 / 上下文）。

    2026-10-04 审计 A：跨域重复项归位 —— 今日 tokens/额度归「用量」卡、主机归「系统」卡，
    本卡只留「现在」这一层。
    2026-10-04 卡片化研究：原「📊 详情 /status」「🧠 上下文 /context」两颗吐文字按钮已删——
    本卡就是 /status 的规范视图（卡内已含上下文占用），直输 /status 也会直接出这张卡。
    数据一律复用插件既有的真实采集器，不另起数据源、不编造；任一项取不到一律显示「—」。
    """
    model = _current_model()
    bg = _bg_tasks()
    bg_v = "—" if bg < 0 else str(bg)
    bg_k = "🐾 正在忙" if bg > 0 else ("🐾 很清闲" if bg == 0 else "取不到")
    dur, start, nmsg = _session_info(chat_id)
    ctx, limit = _session_ctx(chat_id)
    ctx_pct = _pct_of(ctx, limit)
    el: List[Dict[str, Any]] = [
        _md(f"🤖 **模型** `{model}`"),
        _metric_row(
            _usage_cell("🐾 后台", bg_v, bg_k, accent=bg > 0, tone=_DOM_DATA),
            _usage_cell("⏱ 本会话", dur, f"起 {start}" if start != "—" else "本会话", tone=_DOM_DATA),
        ),
        _metric_row(
            _usage_cell("💬 消息", nmsg, "本会话", tone=_DOM_DATA),
            _usage_cell("📚 上下文", ctx, limit,
                        accent=bool(ctx_pct is not None and ctx_pct >= 80), tone=_DOM_DATA),
        ),
        _note("口径同 /status：会话与用量取自 state.db，主机取自系统实时读数。"),
        {"tag": "hr"},
    ]
    el += _rows([
        _refresh_btn("状态"),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("🩺 运行状态", _DOM_DATA, el, subtitle=f"刷新于 {_now_hm()}")


# ── 任务 / 洞察 / 模型 / 忙时 / 版本 的数据源（全部只读本机，不写任何东西）─────

_VER_CACHE: Dict[str, Any] = {}
_MODEL_CACHE: Dict[str, Any] = {}
_SKILL_ZH_CACHE: Dict[str, Any] = {}


def _dur(secs: int) -> str:
    if secs < 60:
        return "%d 秒" % secs
    if secs < 3600:
        return "%d 分钟" % (secs // 60)
    if secs < 86400:
        return "%d 小时 %d 分" % (secs // 3600, (secs % 3600) // 60)
    return "%d 天 %d 小时" % (secs // 86400, (secs % 86400) // 3600)


def _ago(ts: Any) -> str:
    """时间戳 → 「x 分钟前」。"""
    try:
        delta = max(0.0, time.time() - float(ts))
    except Exception:
        return "—"
    if delta < 60:
        return "刚刚"
    if delta < 3600:
        return "%d 分钟前" % int(delta // 60)
    if delta < 86400:
        return "%d 小时前" % int(delta // 3600)
    return "%d 天前" % int(delta // 86400)


def _cron_jobs() -> List[Dict[str, Any]]:
    """定时任务清单（cron/jobs.json）。"""
    try:
        import os as _os

        home = Path(_os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        data = json.loads((home / "cron" / "jobs.json").read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("jobs") or []
        return [j for j in data if isinstance(j, dict)]
    except Exception:
        return []


def _delegations(limit: int = 6) -> Tuple[int, List[Dict[str, str]]]:
    """(进行中的后台委托数, 最近几条)。task_json 里的 goal 就是人话标签。"""
    running = 0
    rows: List[Dict[str, str]] = []
    try:
        import os as _os

        home = Path(_os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        conn = _ro_conn(home)
        try:
            running = int(conn.execute(
                "SELECT COUNT(*) FROM async_delegations WHERE completed_at IS NULL"
                " AND state IN ('running','queued','pending','dispatched')").fetchone()[0] or 0)
            for did, state, disp, comp, tj in conn.execute(
                    "SELECT delegation_id, state, dispatched_at, completed_at, task_json"
                    " FROM async_delegations ORDER BY dispatched_at DESC LIMIT ?", (limit,)):
                label = ""
                try:
                    obj = json.loads(tj or "{}")
                    if isinstance(obj, dict):
                        label = str(obj.get("goal") or obj.get("task") or "")
                except Exception:
                    label = ""
                rows.append({
                    "id": str(did), "state": str(state or ""),
                    "label": label.split(";")[0].strip(),
                    "when": _ago(disp), "done": _ago(comp) if comp else "",
                })
        finally:
            conn.close()
    except Exception:
        logger.info("[FeishuMenuBridge] 读后台委托失败", exc_info=True)
    return running, rows


def _model_usage(limit: int = 6) -> List[Dict[str, Any]]:
    """逐模型真实用量（session_model_usage 汇总，不摊分）。

    口径 = **含缓存读**（input+output+cache_read），与卡片总令牌、中转站一致。
    2026-10-07 审计修复（#7）：原来只 SUM(input+output)，而卡片总令牌标着「含缓存读」
    → 两个数字永远对不上（本机缓存读远大于输入，差距是数量级）。
    """
    out: List[Dict[str, Any]] = []
    try:
        import os as _os

        home = Path(_os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        conn = _ro_conn(home)
        try:
            for model, calls, toks, sessions in conn.execute(
                    "SELECT model, SUM(COALESCE(api_call_count,0)),"
                    " SUM(COALESCE(input_tokens,0)+COALESCE(output_tokens,0)"
                    "     +COALESCE(cache_read_tokens,0)),"
                    " COUNT(DISTINCT session_id) FROM session_model_usage"
                    " GROUP BY model ORDER BY 3 DESC LIMIT ?", (limit,)):
                out.append({"model": str(model or "?"), "calls": int(calls or 0),
                            "tokens": int(toks or 0), "sessions": int(sessions or 0)})
        finally:
            conn.close()
    except Exception:
        logger.info("[FeishuMenuBridge] 读模型用量失败", exc_info=True)
    return out


def _busy_mode() -> str:
    """当前忙线处理模式（config.yaml display.busy_input_mode）。"""
    try:
        import os as _os

        home = Path(_os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        txt = (home / "config.yaml").read_text(encoding="utf-8")
        block = re.search(r"(?ms)^display:\s*\n((?:[ \t]+.*\n|\s*\n)*)", txt)
        scope = block.group(1) if block else txt
        m = re.search(r"(?m)^[ \t]+busy_input_mode:\s*['\"]?([^\s'\"]+)", scope)
        return m.group(1).strip().lower() if m else "interrupt"
    except Exception:
        return "interrupt"


def _version_info() -> Dict[str, str]:
    """版本信息（30 分钟缓存，避免每次点卡都起进程）。"""
    now = time.time()
    cached = _VER_CACHE.get("data")
    if cached and now - float(_VER_CACHE.get("ts") or 0) < 1800:
        return dict(cached)
    out = {"hermes": "?", "install": "?", "gateway": "?"}
    raw = _run("hermes --version 2>&1 | head -3", timeout=15)
    m = re.search(r"Hermes Agent\s+(\S+)", raw)
    if m:
        out["hermes"] = m.group(1)
    m = re.search(r"Install directory:\s*(\S+)", raw)
    if m:
        out["install"] = m.group(1)
    raw2 = _run("ps -o etimes= -p $(systemctl show -p MainPID --value hermes-gateway)"
                " 2>/dev/null", timeout=8).strip()
    if raw2.isdigit():
        out["gateway"] = _dur(int(raw2))
    _VER_CACHE["ts"] = now
    _VER_CACHE["data"] = dict(out)
    return out


def _endpoint_models(ttl: float = 21600.0) -> List[str]:
    """端点 /v1/models 的通道清单（磁盘内存缓存 6 小时）。

    密钥只在本进程内用于本机请求，绝不写日志、绝不外传。
    """
    now = time.time()
    cached = _MODEL_CACHE.get("ids")
    if cached and now - float(_MODEL_CACHE.get("ts") or 0) < ttl:
        return list(cached)
    ids: List[str] = []
    try:
        import os as _os
        import urllib.request

        home = Path(_os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        cfg = (home / "config.yaml").read_text(encoding="utf-8")
        base = ""
        m = re.search(r"(?m)^\s*base_url:\s*['\"]?(https?://[^\s'\"]+)", cfg)
        if m:
            base = m.group(1).rstrip("/")
        key_env = "OPENAI_API_KEY"
        m = re.search(r"(?m)^\s*key_env:\s*['\"]?([A-Z0-9_]+)", cfg)
        if m:
            key_env = m.group(1)
        key = str(_os.environ.get(key_env) or "")
        if not key:
            try:
                for raw in (home / ".env").read_text(encoding="utf-8", errors="ignore").splitlines():
                    raw = raw.strip()
                    if raw.startswith(key_env + "="):
                        key = raw.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            except Exception:
                key = ""
        if base and key:
            req = urllib.request.Request(base + "/models",
                                         headers={"Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=6) as resp:
                payload = json.loads(resp.read().decode("utf-8", "ignore"))
            ids = sorted({str(x.get("id")) for x in (payload.get("data") or [])
                          if isinstance(x, dict) and x.get("id")})
    except Exception:
        logger.info("[FeishuMenuBridge] 端点模型清单取不到（沿用旧缓存）", exc_info=True)
    if ids:
        _MODEL_CACHE["ts"] = now
        _MODEL_CACHE["ids"] = list(ids)
    return ids or list(cached or [])


def _skill_zh_map() -> Dict[str, str]:
    """技能中文说明表（插件目录下 skill_zh.json；改了文件自动生效）。"""
    try:
        p = Path(__file__).with_name("skill_zh.json")
        stamp = p.stat().st_mtime
    except Exception:
        return {}
    if _SKILL_ZH_CACHE.get("stamp") == stamp:
        return _SKILL_ZH_CACHE.get("data") or {}
    try:
        data = json.loads(Path(__file__).with_name("skill_zh.json").read_text(encoding="utf-8"))
        data = {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:
        data = {}
    _SKILL_ZH_CACHE["stamp"] = stamp
    _SKILL_ZH_CACHE["data"] = data
    return data


def _skill_zh(name: str) -> str:
    """技能中文说明：先查包内静态表，再查自动翻译缓存，都没有返回空串。"""
    return str(_skill_zh_map().get(name) or _skill_zh_auto_map().get(name) or "")


# ── 技能说明「自动中文化」──────────────────────────────────────────
# 背景：包内 skill_zh.json 是**静态**表（离线、零成本），只覆盖通用技能；
# 接收方自己装的技能不在表里，卡片只能显示 SKILL.md 原文（可能是英文）。
# 这里让插件用**本机已配置的模型**自动补译，结果落盘缓存、之后一直复用。
# 三条硬约束：① 卡片渲染绝不能等模型（补译走后台线程）；
#             ② 任何失败都静默保留原文（不写、不抛）；
#             ③ 已经是中文的不送模型（省 token）。
_SKILL_ZH_AUTO = _HOME_DIR + "/state/skill_zh_auto.json"
_SKILL_ZH_AUTO_CACHE: Dict[str, Any] = {}
_SKILL_ZH_FILLING = threading.Event()

_SKILL_ZH_PROMPT = ("给技能写一行中文说明：不超过 16 个汉字，要点用顿号分隔，"
                    "保留专有名词/产品名/命令原文，不要句号。"
                    '只输出 JSON 对象 {"技能名":"说明"}，不要其他文字。')


def _skill_zh_auto_map() -> Dict[str, str]:
    """自动翻译缓存（$HERMES_HOME/state/skill_zh_auto.json；按 mtime 缓存）。"""
    try:
        stamp = os.stat(_SKILL_ZH_AUTO).st_mtime_ns
    except Exception:
        return {}
    if _SKILL_ZH_AUTO_CACHE.get("stamp") == stamp:
        return _SKILL_ZH_AUTO_CACHE.get("data") or {}
    try:
        with open(_SKILL_ZH_AUTO, encoding="utf-8") as fh:
            data = json.load(fh)
        data = {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:
        data = {}
    _SKILL_ZH_AUTO_CACHE["stamp"], _SKILL_ZH_AUTO_CACHE["data"] = stamp, data
    return data


def _is_chinese(text: str) -> bool:
    """说明是否已经是中文（汉字够多就不再送模型）。"""
    s = str(text or "")
    if not s.strip():
        return True
    han = len(re.findall(r"[\u4e00-\u9fff]", s))
    return han >= max(4, int(len(s) * 0.25))


def _llm_endpoint() -> Tuple[str, str, str]:
    """本机模型接入点 (base_url, api_key, model)；任一项缺失就返回三个空串。

    读 config.yaml 的 base_url / model.default；密钥变量名取 config 里
    providers.*.key_env（本机为 HERMES_RELAY_API_KEY），先查进程环境再读
    $HERMES_HOME/.env。**不打印、不外传密钥**。
    """
    base = model = cfg = ""
    try:
        cfg = (Path(_HOME_DIR) / "config.yaml").read_text(encoding="utf-8")
        m = re.search(r"(?m)^\s*base_url:\s*['\"]?(https?://[^\s'\"]+)", cfg)
        base = m.group(1) if m else ""
        m = re.search(r"(?m)^\s*default:\s*['\"]?([^\s'\"]+)", cfg)
        model = m.group(1) if m else ""
    except Exception:
        pass
    key_env = "OPENAI_API_KEY"
    try:
        _m = re.search(r"(?m)^\s*key_env:\s*['\"]?([A-Z0-9_]+)", cfg)
        if _m:
            key_env = _m.group(1)
    except Exception:
        pass
    key = (os.environ.get(key_env) or "").strip()
    if not key:
        try:
            for ln in (Path(_HOME_DIR) / ".env").read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if ln.startswith(key_env + "="):
                    key = ln.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        except Exception:
            pass
    if base and key and model:
        return base.rstrip("/"), key, model
    return "", "", ""


def _skill_zh_translate(items: List[Dict[str, str]]) -> Dict[str, str]:
    """调本机模型把 [{name, desc}] 译成 {name: 中文说明}；任何失败返回 {}。"""
    base, key, model = _llm_endpoint()
    if not (base and key and model) or not items:
        return {}
    try:
        import urllib.request
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": _SKILL_ZH_PROMPT},
                {"role": "user", "content": json.dumps(items, ensure_ascii=False)},
            ],
            "temperature": 0.2,
        }
        req = urllib.request.Request(
            base + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        txt = body["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            return {}
        got = json.loads(m.group(0))
        return {str(k): str(v).strip() for k, v in got.items()} if isinstance(got, dict) else {}
    except Exception:
        logger.warning("[FeishuMenuBridge] 技能说明翻译调用失败（保留原文）", exc_info=True)
        return {}


def skill_zh_autofill(limit: Optional[int] = None, batch: int = 20) -> Dict[str, Any]:
    """补齐技能中文说明：挑出「没有中文且原文也不是中文」的 → 分批送模型 → 落盘。

    幂等：静态表与自动缓存里已有的不再送模型。
    失败静默：不写、不抛，卡片继续显示原文。写入前重读文件并合并（防并发丢更新）。
    """
    known = _skill_zh_map()
    auto = dict(_skill_zh_auto_map())
    todo: List[Dict[str, str]] = []
    for r in _skills_flat():
        if r["name"] in known or r["name"] in auto:
            continue
        d = _skill_desc(r["path"])
        if not d or _is_chinese(d):
            continue
        todo.append({"name": r["name"], "desc": d[:300]})
    if limit:
        try:
            todo = todo[:max(1, int(limit))]
        except Exception:
            pass
    stats: Dict[str, Any] = {"candidates": len(todo), "translated": 0, "failed": 0}
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        got = _skill_zh_translate(chunk)
        if not got:
            stats["failed"] += len(chunk)
            continue
        for it in chunk:
            zh = _clean_md(got.get(it["name"]) or "")
            if zh:
                auto[it["name"]] = zh
                stats["translated"] += 1
            else:
                stats["failed"] += 1
    if stats["translated"]:
        try:
            p = Path(_SKILL_ZH_AUTO)
            cur: Dict[str, Any] = {}
            if p.exists():
                try:
                    cur = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    cur = {}
            if not isinstance(cur, dict):
                cur = {}
            cur.update(auto)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(cur, ensure_ascii=False, indent=1, sort_keys=True),
                         encoding="utf-8")
            _SKILL_ZH_AUTO_CACHE.clear()      # 让下一次读拿到新值
        except Exception:
            logger.warning("[FeishuMenuBridge] 技能中文缓存写入失败", exc_info=True)
    stats["remaining"] = max(0, len(todo) - stats["translated"])
    return stats


def _skill_zh_missing() -> int:
    """还有多少条技能说明没有中文（原文也不是中文的才算）。"""
    n = 0
    for r in _skills_flat():
        if _skill_zh(r["name"]):
            continue
        if _is_chinese(_skill_desc(r["path"])):
            continue
        n += 1
    return n


def _skill_zh_autofill_kick(batch: int = 20) -> None:
    """非阻塞触发一批补译（同一时刻只跑一个；卡片渲染绝不能等模型）。

    想彻底关掉自动补译：设环境变量 ``FMB_SKILL_ZH_AUTO=0`` 后重启网关。
    """
    if str(os.environ.get("FMB_SKILL_ZH_AUTO", "1")).strip().lower() in ("0", "false", "no", "off"):
        return
    if _SKILL_ZH_FILLING.is_set():
        return
    _SKILL_ZH_FILLING.set()

    def _run() -> None:
        try:
            skill_zh_autofill(limit=batch)
        except Exception:
            logger.warning("[FeishuMenuBridge] 技能自动翻译失败（忽略）", exc_info=True)
        finally:
            _SKILL_ZH_FILLING.clear()

    threading.Thread(target=_run, name="fmb-skill-zh-fill", daemon=True).start()


def _clean_md(text: str) -> str:
    """去掉会被卡片 markdown 误解析的字符（translate 一次完成，比循环 replace 快也直观）。"""
    return str(text or "").translate(str.maketrans("", "", "*_`[]")).strip()


# ── 任务卡 ───────────────────────────────────────────────────────

def build_tasks_card(chat_id: str = "") -> Dict[str, Any]:
    """「任务」卡：后台委托 + 定时任务（本机真实状态）。"""
    running, rows = _delegations(6)
    jobs = _cron_jobs()
    enabled = [j for j in jobs if j.get("enabled")]
    el: List[Dict[str, Any]] = [
        _metric_row(_usage_cell("🐾 后台", f"{running}", "进行中" if running else "空闲",
                                accent=True, tone=_DOM_DATA),
                    _usage_cell("⏰ 定时", f"{len(enabled)}/{len(jobs)}", "启用/总数", tone=_DOM_DATA),
                    _usage_cell("🕒 刷新", _now_hm(), "本地时间", tone=_DOM_DATA)),
    ]
    if rows:
        lines = []
        for r in rows:
            flag = "🟢" if r["state"] in ("running", "queued", "pending", "dispatched") else "⚪"
            tail = r["when"] if r["state"] in ("running", "queued", "pending", "dispatched") else r["done"]
            lines.append("%s %s　_%s_" % (flag, _clean_md(r["label"])[:34] or r["id"], tail))
        el.append(_panel_element("🐾 后台任务 · 最近 %d 条" % len(rows), "\n".join(lines)))
    else:
        el.append(_note("当前没有后台任务在跑。"))
    if jobs:
        lines = []
        for j in jobs[:10]:
            flag = "✅" if j.get("enabled") else "⏸"
            sched = j.get("schedule") or {}
            when = str(sched.get("display") or sched.get("expr") or "")
            lines.append("%s **%s**　`%s`" % (flag, _clean_md(str(j.get("name") or j.get("id")))[:24], when))
        el.append(_panel_element("⏰ 定时任务 · %d 个" % len(jobs), "\n".join(lines)))
    el.append({"tag": "hr"})
    el += _rows([
        _refresh_btn("任务"),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("🎯 任务", _DOM_DATA, el,
                 subtitle="后台 %d · 定时 %d 启用" % (running, len(enabled)))


# ── 洞察卡 ───────────────────────────────────────────────────────

_WEEKDAY_ZH = {"0": "周日", "1": "周一", "2": "周二", "3": "周三", "4": "周四", "5": "周五", "6": "周六"}


def _tz_off_s() -> int:
    """本机当前 UTC 偏移（秒）——随夏令时自动变化（2026-10-25 EU 切冬令时后 +2h→+1h）。"""
    try:
        return int(time.localtime().tm_gmtoff)
    except Exception:
        return 7200


def _insights_stats(days: int = 30) -> Dict[str, Any]:
    """官方 /insights 的同口径统计（会话级，只读 state.db）。

    口径已与官方逐项对账（2026-10-04）：会话数=COUNT(sessions)、消息数=SUM(message_count)、
    工具调用=SUM(tool_call_count)、令牌=SUM(input+output+cache_read)；时段/日期按 +2h 本地时。
    """
    out: Dict[str, Any] = {}
    conn = None
    try:
        import sqlite3 as _sqlite
        home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        conn = _sqlite.connect("file:%s?mode=ro" % (home / "state.db"), uri=True, timeout=15)
        conn.row_factory = _sqlite.Row
        cut = time.time() - days * 86400
        r = conn.execute(
            "SELECT COUNT(*) n, SUM(message_count) mc, SUM(tool_call_count) tc,"
            " SUM(input_tokens) ti, SUM(output_tokens) too, SUM(cache_read_tokens) tcr,"
            " SUM(reasoning_tokens) tr, SUM(api_call_count) ac"
            " FROM sessions WHERE started_at > ?", (cut,)).fetchone()
        out.update(sessions=r["n"] or 0, messages=r["mc"] or 0, tools=r["tc"] or 0,
                   tok_in=r["ti"] or 0, tok_out=r["too"] or 0, tok_cache=r["tcr"] or 0,
                   tok_reason=r["tr"] or 0, api_calls=r["ac"] or 0)
        out["tok_total"] = out["tok_in"] + out["tok_out"] + out["tok_cache"]
        _off = _tz_off_s()
        rows = conn.execute(
            "SELECT DISTINCT date(timestamp + " + str(_off) + ", 'unixepoch') d FROM messages"
            " WHERE timestamp > ? ORDER BY d", (cut,)).fetchall()
        ds = [x["d"] for x in rows]
        out["active_days"] = len(ds)
        streak = 0
        try:
            import datetime as _dt
            today = _dt.datetime.now(_dt.timezone(_dt.timedelta(seconds=_off))).date()
            have = set(ds)
            cur = today if today.isoformat() in have else today - _dt.timedelta(days=1)
            while cur.isoformat() in have:
                streak += 1
                cur -= _dt.timedelta(days=1)
        except Exception:
            streak = 0
        out["streak"] = streak
        hh = conn.execute(
            "SELECT strftime('%H', timestamp + " + str(_off) + ", 'unixepoch') h, COUNT(*) n FROM messages"
            " WHERE timestamp > ? GROUP BY h ORDER BY n DESC LIMIT 1", (cut,)).fetchone()
        wd = conn.execute(
            "SELECT strftime('%w', timestamp + " + str(_off) + ", 'unixepoch') w, COUNT(*) n FROM messages"
            " WHERE timestamp > ? GROUP BY w ORDER BY n DESC LIMIT 1", (cut,)).fetchone()
        out["busy_hour"] = (hh["h"] + "点") if hh else ""
        out["busy_wday"] = _WEEKDAY_ZH.get(wd["w"], "") if wd else ""
        out["platforms"] = [dict(x) for x in conn.execute(
            "SELECT source s, COUNT(*) n, COALESCE(SUM(message_count),0) mc FROM sessions"
            " WHERE started_at > ? GROUP BY source ORDER BY n DESC LIMIT 6", (cut,))]
        out["tools_top"] = [dict(x) for x in conn.execute(
            "SELECT tool_name t, COUNT(*) n FROM messages"
            " WHERE timestamp > ? AND tool_name IS NOT NULL AND tool_name != ''"
            " GROUP BY t ORDER BY n DESC LIMIT 5", (cut,))]
    except Exception:
        logger.warning("[FeishuMenuBridge] 读洞察统计失败", exc_info=True)
    finally:
        # 2026-10-07 审计修复（#14）：连接改在 finally 关，异常路径不再靠 GC 兜底。
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return out


_PLATFORM_ZH = {"telegram": "Telegram", "feishu": "飞书", "weixin": "微信", "cli": "命令行",
                "subagent": "子代理", "cron": "定时任务", "oneshot": "一次性", "system": "系统"}


def build_insights_card(chat_id: str = "") -> Dict[str, Any]:
    """「洞察」卡：官方 /insights 的**中文卡片版**（数字只读 state.db，口径与官方逐项对过账）。

    2026-10-04 用户要求：把 /insights 那页英文报告变成卡片 + 中文。
    """
    st = _usage_stats(7)
    ins = _insights_stats(30)
    models = _model_usage(6)
    rows = st.get("sessions") or []
    el: List[Dict[str, Any]] = []
    if ins:
        el.append(_metric_row(
            _usage_cell("🗂 会话", f"{ins.get('sessions', 0)}", "近 30 天", accent=True, tone=_DOM_DATA),
            _usage_cell("💬 消息", f"{ins.get('messages', 0)}", "人机对话", tone=_DOM_DATA),
            _usage_cell("🛠 工具调用", f"{ins.get('tools', 0)}", "次", tone=_DOM_DATA)))
        el.append(_metric_row(
            _usage_cell("🔤 令牌", _fmt_tokens(ins.get("tok_total", 0)), "含缓存读", tone=_DOM_DATA),
            _usage_cell("📥 输入", _fmt_tokens(ins.get("tok_in", 0)), "", tone=_DOM_DATA),
            _usage_cell("📤 输出", _fmt_tokens(ins.get("tok_out", 0)), "", tone=_DOM_DATA)))
        el.append(_metric_row(
            _usage_cell("📆 活跃", f"{ins.get('active_days', 0)}", "天", tone=_DOM_DATA),
            _usage_cell("🔥 连续", f"{ins.get('streak', 0)}", "天", tone=_DOM_DATA),
            _usage_cell("⏰ 最忙", f"{ins.get('busy_wday', '?')} {ins.get('busy_hour', '')}".strip(),
                        "本地时间", vsize="normal", tone=_DOM_DATA)))
    if ins.get("platforms"):
        lines = ["%s　**%s** 会话　%s 条" % (_PLATFORM_ZH.get(p["s"], p["s"]), p["n"], p["mc"])
                 for p in ins["platforms"]]
        el.append(_panel_element("🖥 按平台 · 近 30 天", "\n".join(lines), expanded=True))
    if ins.get("tools_top"):
        lines = ["`%s`　**%s** 次" % (t["t"], t["n"]) for t in ins["tools_top"]]
        el.append(_panel_element("🧰 最常用工具 · 近 30 天", "\n".join(lines)))
    if models:
        lines = ["**%s**　%s　_%s 次调用_" % (_clean_md(m["model"])[:30], _fmt_tokens(m["tokens"]), m["calls"])
                 for m in models]
        el.append(_panel_element("🤖 按模型 · 累计", "\n".join(lines)))
    top = sorted(rows, key=lambda r: int(r.get("total") or 0), reverse=True)[:8]
    if top:
        lines = ["**%s**　%s" % (_clean_md(r["label"])[:20], _fmt_tokens(int(r["total"]))) for r in top]
        el.append(_panel_element("💬 最耗会话 · 累计", "\n".join(lines)))
    el.append(_note("口径与官方 /insights 一致：会话级统计（会话数/消息数/工具调用/令牌），"
                    "数字全部来自本机 state.db，不摊分；时段按本地时区（UTC%+d）。"
                    % (int(_tz_off_s() // 3600),)))
    el.append({"tag": "hr"})
    el += _rows([
        _refresh_btn("洞察"),
        _btn("📈 用量卡", {"hermes_menu_card": "用量"}),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("🔍 洞察", _DOM_DATA, el,
                 subtitle="近 30 天 · %d 个会话 · %d 个模型" % (ins.get("sessions", len(rows)), len(models)))


# ── 模型卡（已删）───────────────────────────────────────────────
# 2026-10-04 卡片化研究（G1）：本卡已不可达（「模型」被 COMMANDS 优先拦截 → 走 /model 点选器；
# CARD_NAMES 也不含它）→ 按审计建议删除死代码。设置里的「模型」继续发 /model，
# 由 feishu-model-picker 插件渲染「切换模型 · 选择提供方」交互卡。


# ── 忙时卡 ───────────────────────────────────────────────────────

_REASONING_ZH: Dict[str, str] = {
    "none": "关闭", "minimal": "极简", "low": "低", "medium": "中",
    "high": "高", "xhigh": "极高", "max": "最高", "ultra": "极致", "auto": "自动",
}

#: 推理档位的个性小图标（下拉选项用；克制的活泼，不抢戏）
_REASONING_EMOJI: Dict[str, str] = {
    "none": "🚫", "minimal": "▫️", "low": "🐢", "medium": "⚖️",
    "high": "🚀", "xhigh": "🔥", "max": "🌋", "ultra": "💎", "auto": "🤖",
}


_BUSY_LABELS: Dict[str, Tuple[str, str]] = {
    "interrupt": ("✋ 插话", "新消息立刻打断当前回合"),
    "queue": ("⏳ 排队", "新消息排队，等当前回合跑完"),
    "steer": ("🧭 转向", "把新消息插到下一次工具调用后"),
}


def build_busy_card(chat_id: str = "") -> Dict[str, Any]:
    """「忙时」卡：我在忙的时候你发的消息怎么处理。"""
    cur = _busy_mode()
    label, desc = _BUSY_LABELS.get(cur, (cur, ""))
    el: List[Dict[str, Any]] = [
        _metric_row(_usage_cell("🎛 当前", label, desc or "—", accent=True, tone=_DOM_DATA),
                    _usage_cell("📖 模式", f"{len(_BUSY_LABELS)}", "种可选", tone=_DOM_DATA)),
        _note("点下面任一项即切换（等于发送 /busy 模式名），改的是 config.yaml 的 display.busy_input_mode。"),
    ]
    btns: List[Dict[str, Any]] = []
    for mode, (lb, ds) in _BUSY_LABELS.items():
        is_cur = mode == cur
        btns.append(_cmd_btn(("✅ " if is_cur else "▶ ") + lb,
                             "/busy " + mode,
                             "primary_filled" if is_cur else "default"))
    el += _rows(btns, per_row=1)
    el.append({"tag": "hr"})
    el += _rows([
        _refresh_btn("忙时"),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("🎛 忙时", _DOM_DATA, el, subtitle="当前 %s" % label)


# ── 版本卡 ───────────────────────────────────────────────────────

def build_version_card(chat_id: str = "") -> Dict[str, Any]:
    """「版本」卡：Hermes 版本 / 网关运行时长 / 模型 / 上下文 / 家底。"""
    v = _version_info()
    info = _model_info()
    skills_total, _ = _skills_index()
    el: List[Dict[str, Any]] = [
        _metric_row(_usage_cell("🏷 Hermes", str(v.get("hermes", "?"))[:18], "上游版本",
                                accent=True, tone=_DOM_ENTRY),
                    _usage_cell("⏱ 网关", str(v.get("gateway", "?")), "已运行", tone=_DOM_ENTRY),
                    _usage_cell("📏 上下文", info.get("context_length", "?"), "上限", tone=_DOM_ENTRY)),
        _panel_element("🧩 家底", "\n".join([
            "**模型**　%s" % _clean_md(info.get("default", "?")),
            "**技能**　%d 个" % skills_total,
            "**PT 站**　%d 个" % _pt_sites(),
            "**安装目录**　`%s`" % _clean_md(str(v.get("install", "?"))),
        ])),
    ]
    el.append({"tag": "hr"})
    el += _rows([
        _refresh_btn("版本"),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("🏷 版本", _DOM_ENTRY, el, subtitle="刷新于 %s" % _now_hm())


# ── 出站文本 → 卡片（2026-10-04 卡片化研究 ⑥⑦：定时任务 + 服务错误）─────────
# 机制：包住 FeishuAdapter._feishu_send_with_retry —— 所有文本出站的最低公共口子。
# 命中「已知机器文本」前缀表 → 改发卡片；任何异常/不命中 → 原样放行，绝不吞消息。
# 想秒关：_SEND_CARDIFY = False + 升 _CODE_V 重启。
# ── PT 签到静音窗（2026-10-04 用户要求）────────────────────────────────
# 只在签到流程进行期间（record_checkin.py --begin 写标记 → --finish 删；超时自动失效）
# 拦掉飞书侧的工具进度提示与后台任务完成卡；其他时段/其他卡片一律不变。
_PT_LIVE_PATH = _PT_DIR + "/state/checkin_live.json"
_PT_QUIET_TTL = 4 * 3600.0            # v1 旧格式（仅 started）兼容 TTL——保持改前语义
_PT_QUIET_HB_TTL = 45 * 60.0          # v2：心跳有效期；>45min 无心跳 = 签到停摆，静音自灭
_PT_QUIET_HARD_CAP = 12 * 3600.0      # v2：自 started 起绝对上限（防残留标记永久静音）


def _pt_quiet_active() -> bool:
    """签到静音窗是否生效？（v2 心跳制：hb 新鲜且在硬上限内；v1 旧格式回退旧语义）"""
    try:
        with open(_PT_LIVE_PATH, encoding="utf-8") as fh:
            st = json.load(fh)
        if not isinstance(st, dict):
            return False
        now = time.time()
        started = float(st.get("started") or 0.0)
        hb = float(st.get("hb") or 0.0)
        if hb <= 0.0:
            # v1 旧格式（现网残留 / 未升级的脚本）：4h-from-started，与改前行为完全一致
            return 0.0 < (now - started) < _PT_QUIET_TTL
        if not (0.0 < (now - started) < _PT_QUIET_HARD_CAP):
            return False   # started 缺失/异常/超 12h 硬上限 → 视为停摆
        return (now - hb) < _PT_QUIET_HB_TTL
    except Exception:
        return False


# ── PT 静音窗 · 延迟补发队列（A5：静音≠丢消息）────────────────
# 说明：无来源鉴别手段（W2-09 S2：feishu 出站无 _non_conversational_metadata，
# run.py:3013 的 no-op 是 discord-only），故不做内容过滤，改为「静音期内入队、
# 静音结束后合并补发」——非 PT 消息不丢、PT 降噪目标仍达成。
_PT_DEFER_PATH = _PT_DIR + "/state/quiet_deferred.jsonl"
_PT_DEFER_MAX = 100                    # 队列上限（丢最旧），防无界增长
_PT_FLUSH_STATE: Dict[str, Any] = {"thread": None, "loop": None, "adapter": None}
_PT_FLUSH_LOCK = threading.Lock()


def _pt_defer_bg(text: str, chat_id: str, adapter: Any) -> None:
    """静音窗内把「后台完成」提示写入延迟队列（JSONL 追加），并确保补发线程在跑。"""
    entry = {"ts": time.time(), "chat_id": chat_id, "text": (text or "")[:2000]}
    with _PT_FLUSH_LOCK:
        try:
            os.makedirs(os.path.dirname(_PT_DEFER_PATH), exist_ok=True)
        except Exception:
            pass
        with open(_PT_DEFER_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        try:                                   # 队列上限：截尾保留最近 N 条
            with open(_PT_DEFER_PATH, encoding="utf-8") as fh:
                lines = [x for x in fh.read().splitlines() if x.strip()]
            if len(lines) > _PT_DEFER_MAX:
                tmp = _PT_DEFER_PATH + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(lines[-_PT_DEFER_MAX:]) + "\n")
                os.replace(tmp, _PT_DEFER_PATH)
                logger.warning("[FeishuMenuBridge] PT 静音窗延迟队列超限，丢弃最旧 %d 条",
                               len(lines) - _PT_DEFER_MAX)
        except Exception:
            pass
    try:
        _PT_FLUSH_STATE["loop"] = asyncio.get_running_loop()
        _PT_FLUSH_STATE["adapter"] = adapter
    except Exception:
        pass
    _pt_kick_flush()


def _pt_kick_flush() -> None:
    """确保补发守护线程在跑（幂等；网关重启后由下一次出站/入队再拉起）。"""
    t = _PT_FLUSH_STATE.get("thread")
    if t is not None and t.is_alive():
        return
    try:
        t = threading.Thread(target=_pt_flush_loop, name="fmb-pt-defer-flush", daemon=True)
        _PT_FLUSH_STATE["thread"] = t
        t.start()
    except Exception:
        pass


def _pt_flush_loop() -> None:
    """60s 一拍：静音窗不生效且队列非空 → 在网关事件循环里补发。"""
    while True:
        time.sleep(60.0)
        try:
            if _pt_quiet_active():
                continue
            try:
                with open(_PT_DEFER_PATH, encoding="utf-8") as fh:
                    if not fh.read().strip():
                        continue
            except Exception:
                continue
            loop = _PT_FLUSH_STATE.get("loop")
            adapter = _PT_FLUSH_STATE.get("adapter")
            if loop is None or loop.is_closed() or adapter is None:
                continue
            fut = asyncio.run_coroutine_threadsafe(_pt_flush_once(adapter), loop)
            try:
                fut.result(timeout=120)
            except Exception:
                logger.debug("[FeishuMenuBridge] PT 延迟补发未完成，下拍重试", exc_info=True)
        except Exception:
            logger.debug("[FeishuMenuBridge] PT 延迟补发轮询异常", exc_info=True)


async def _pt_flush_once(adapter: Any) -> None:
    """逐条补发延迟的后台完成提示；每条成功即出队（失败保留、下拍重试）。"""
    with _PT_FLUSH_LOCK:
        try:
            with open(_PT_DEFER_PATH, encoding="utf-8") as fh:
                entries = [json.loads(x) for x in fh.read().splitlines() if x.strip()]
        except Exception:
            return
    while entries:
        e = entries[0]
        chat_id = str(e.get("chat_id") or "")
        if not chat_id:
            entries.pop(0)
            continue
        try:
            head = "⏳ **【延迟补发】** 签到静音窗期间收到的后台任务完成提示：\n\n"
            card = await asyncio.to_thread(build_bg_done_card, head + str(e.get("text") or ""), True)
            res = await _send_card(adapter, chat_id, card)
            ok = _send_ok(res)
        except Exception:
            ok = False
        if not ok:
            logger.warning("[FeishuMenuBridge] PT 延迟补发单条失败，保留队列下拍重试")
            break
        entries.pop(0)
        with _PT_FLUSH_LOCK:
            tmp = _PT_DEFER_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in entries))
            os.replace(tmp, _PT_DEFER_PATH)
        logger.info("[FeishuMenuBridge] PT 延迟补发 1 条（剩余 %d）", len(entries))


# ── A6 · 静音窗「伪成功响应」──────────────────────────────────
from types import SimpleNamespace as _SimpleNamespace

#: 静音窗「伪成功响应」（A6）：官方 _response_succeeded 取 getattr(resp,"success",… )() 判定，
#: success 必须是**可调用**且返回 True；裸 True（getattr 取到默认 lambda→False）与
#: SendResult.success（bool，调用即 TypeError）都会被判失败——只有这种形态才两全。
_SILENT_OK = _SimpleNamespace(success=lambda: True, code=0, msg="pt-quiet-silent", data=None)


_SEND_CARDIFY = True
_SEND_CARDIFY_COOLDOWN = 120.0          # 同类「服务错误卡」最短间隔（防刷屏）
_SEND_CARDIFY_LAST: Dict[str, float] = {}

#: 命令型按钮 → 命令生效后需原地刷新的卡（2026-10-04：点了 /reasoning ultra 后卡面不动的修复）
#: 2026-10-04 审计补充：/personality（含「关闭人格」）——人格卡同样需要点后自刷。
_CMD_REFRESH_CARD: Dict[str, str] = {"/reasoning": "推理", "/busy": "忙时", "/personality": "人格"}

#: 刷新任务的「让位」序列：同一张卡连点时，旧任务的后续拍发现被新点击接管即放弃（防乱序回退）
_REFRESH_SEQ: Dict[str, int] = {}

#: 忙时提示的开头（官方 _compose_busy_ack_message 的 6 种 head，全是稳定文案前缀）
_BUSY_HEAD_PREFIXES = (
    "⏩ 已引导至当前运行", "↪ 已重定向当前运行", "⏳ 子代理正在工作",
    "⏳ 正在压缩上下文", "⏳ 已排队至下一回合", "⚡ 正在中断当前任务",
)
_BUSY_CARD_LAST: Dict[str, float] = {}
_BUSY_CARD_COOLDOWN = 90.0             # 每会话忙时卡最短间隔（连发消息时不刷屏）


def _cardify_key(text: str) -> str:
    """已知机器文本 → 类别键（保守：必须从头匹配）；不命中 → ''。"""
    t = (text or "").lstrip()
    # E2 修复：失败判定必须先于成功——cron 失败通知同样被 "Cronjob Response:" 包装头包住
    if t.startswith("⚠️ Cron ") and " failed:" in t:
        return "cron_fail"                              # 无包装头（wrap_response=false）
    if t.startswith("Cronjob Response:") and re.search(r"\n⚠️ Cron '.*?' failed:", t):
        return "cron_fail"                              # 有包装头（现状被 cron_ok 截胡）
    if t.startswith("Cronjob Response:"):
        return "cron_ok"
    if t.startswith("✅ 后台任务") and "完成" in t[:16]:
        return "bg_ok"
    # E3 修复：/bg 失败文案是「❌ 你的后台任务 … 未完成即失败。」，前缀与短句版并存；
    # 失败词不在前 16 字内，放宽窗口。
    if t.startswith(("❌ 后台任务", "❌ 你的后台任务")) and "失败" in t[:80]:
        return "bg_fail"
    if t.startswith(_BUSY_HEAD_PREFIXES):
        return "busy"
    if t.startswith("⏱️ AI 模型服务正在限流"):
        return "err_rate"
    if t.startswith("⚠️ AI 模型服务拒绝了此请求"):
        return "err_reject"
    if t.startswith("⏱️ 已达到 AI 模型服务的用量上限"):
        return "err_quota"
    return ""


def _cardify_extract_text(msg_type: str, payload: str) -> str:
    """从出站 payload 里取出可读文本（text / post 两种；其它类型返回 ''）。"""
    try:
        data = json.loads(payload or "{}")
    except Exception:
        return ""
    if msg_type == "text":
        return str((data or {}).get("text") or "")
    if msg_type == "post":
        try:
            data = json.loads(payload or "{}") or {}
            # 真实结构：{"zh_cn": {"content": [[{"tag": "md", "text": …}]]}} —— 没有 "post" 外包装；
            # 兼容带包装的旧形态（= 两种都试）。2026-10-04 实测定案（cron 投递全部走 post）。
            block = data.get("post") or data
            lang = block.get("zh_cn") or (next(iter(block.values())) if block else {})
            parts: List[str] = []
            for line in (lang or {}).get("content") or []:
                parts.append("".join(str(run.get("text") or "") for run in line))
            return "\n".join(parts)
        except Exception:
            return ""
    return ""


_ERR_TITLES = {"err_rate": "⏱️ 服务限流", "err_reject": "⚠️ 请求被拒", "err_quota": "⏱️ 用量上限"}


def build_cron_result_card(job_name: str, job_id: str, content: str) -> Dict[str, Any]:
    """定时任务结果卡：原文不改字（只截断），数据全部来自投递文本本身。"""
    body = (content or "").strip()
    clipped = len(body) > 1800
    body = body[:1800] + ("\n\n…（全文过长，已截断显示）" if clipped else "")
    el: List[Dict[str, Any]] = [
        _metric_row(_usage_cell("⏰ 任务", (job_name or "—")[:16], "定时任务", accent=True, tone=_DOM_DATA),
                    _usage_cell("🆔 编号", (job_id or "—")[:12], "job id", tone=_DOM_DATA)),
        _panel_element("📄 任务输出" + ("（截断）" if clipped else ""), body or "（空）", expanded=True),
        _note("由定时任务按排程投递；内容为任务真实输出，未改动。"),
        {"tag": "hr"},
    ]
    el += _rows([_btn("✕ 收起", {"hermes_menu_close": True})])
    return _card("⏰ 定时任务结果", _DOM_DATA, el, subtitle="投递于 %s" % _now_hm())


def build_cron_fail_card(text: str) -> Dict[str, Any]:
    _body = _clean_md(text or "")
    if len(_body) > 1800:
        # 2026-10-04 审计修复：长错误体不截断会超卡片体积上限被拒（卡化静默失效）。
        _body = _body[:1800] + "\n\n…（全文过长，已截断显示）"
    el: List[Dict[str, Any]] = [
        _md(_body),
        _note("可以到「任务」卡里看全部定时任务；修好后它会按原排程继续跑。"),
        {"tag": "hr"},
    ]
    el += _rows([
        _btn("🎯 任务卡", {"hermes_menu_card": "任务"}, "primary_filled"),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("⚠️ 定时任务失败", "red", el)


def build_error_card(text: str, kind: str) -> Dict[str, Any]:
    _body = _clean_md(text or "")
    if len(_body) > 1800:
        # 2026-10-04 审计修复：同 build_cron_fail_card —— 超长先截断再入卡。
        _body = _body[:1800] + "\n\n…（全文过长，已截断显示）"
    el: List[Dict[str, Any]] = [
        _md(_body),
        {"tag": "hr"},
    ]
    el += _rows([
        _btn("🔁 重试 /retry", {"hermes_menu_cmd": "/retry"}, "primary_filled"),
        _btn("🤖 换模型", {"hermes_menu_cmd": "/model"}),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card(_ERR_TITLES.get(kind, "⚠️ 服务提示"), "orange", el)


def build_busy_ack_card(text: str) -> Dict[str, Any]:
    """忙时提示卡（⑨）：我正在忙时你发来的消息的反馈；高信息密度 + 一键停。

    数据全部来自投递文本本身（官方 _compose_busy_ack_message 的组合文案）；
    每会话 90 秒冷却、失败自动回退原文，不改变忙碌路径的语义。
    """
    el: List[Dict[str, Any]] = [
        _md(_clean_md(text)[:500] or "—"),
        {"tag": "hr"},
    ]
    el += _rows([
        _btn("⏹ 停掉当前任务", {"hermes_menu_cmd": "/stop"}, "primary_filled"),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("⏳ 我正在忙", _DOM_DATA, el, subtitle="你的消息已收到 · 不会丢")


def build_bg_done_card(text: str, ok: bool) -> Dict[str, Any]:
    """后台任务完成/失败卡（⑧）：原文不改字（只截断），数据来自投递文本本身。"""
    body = (text or "").strip()
    clipped = len(body) > 1800
    body = body[:1800] + ("\n\n…（全文过长，已截断显示）" if clipped else "")
    el: List[Dict[str, Any]] = [
        _panel_element("📄 任务输出" + ("（截断）" if clipped else ""), body or "（空）", expanded=True),
        _note("由后台任务自动投递；内容为任务真实输出，未改动。"),
        {"tag": "hr"},
    ]
    el += _rows([
        _btn("🎯 任务卡", {"hermes_menu_card": "任务"}),
        _btn("✕ 收起", {"hermes_menu_close": True}),
    ])
    return _card("🐾 后台任务完成" if ok else "⚠️ 后台任务失败",
                 _DOM_DATA if ok else "red", el, subtitle="投递于 %s" % _now_hm())


_CARD_BODY_LIMIT = 1800


def _cardify_build(key: str, text: str):
    """整文级：返回 (card, overflow)。overflow 为卡面 1800 字之外仍需补发的纯文本。"""
    if key == "cron_ok":
        head, _sep, rest = text.partition("-------------")
        name = ""
        m = re.match(r"\s*Cronjob Response:\s*(.*)", (head or "").splitlines()[0] if head else "")
        if m:
            name = (m.group(1) or "").strip()
        jm = re.search(r"\(job_id:\s*([^)]+)\)", head or "")
        jid = jm.group(1).strip() if jm else ""
        body = re.split(r"\nTo stop or manage this job", (rest or "").strip(), maxsplit=1)[0].strip()
        return build_cron_result_card(name, jid, body), (body[_CARD_BODY_LIMIT:] if len(body) > _CARD_BODY_LIMIT else "")
    if key == "cron_fail":
        _ft = _strip_cron_wrap(text)          # 见 §3
        return build_cron_fail_card(_ft), (_ft[_CARD_BODY_LIMIT:] if len(_ft) > _CARD_BODY_LIMIT else "")
    if key in ("bg_ok", "bg_fail"):
        body = (text or "").strip()
        return build_bg_done_card(text, key == "bg_ok"), (body[_CARD_BODY_LIMIT:] if len(body) > _CARD_BODY_LIMIT else "")
    if key == "busy":
        return build_busy_ack_card(text), ""
    if key.startswith("err_"):
        return build_error_card(text, key), ""
    return None, ""


def _strip_cron_wrap(text: str) -> str:
    """剥掉 cron 投递的统一包装头与尾注，返回正文。"""
    t = text or ""
    if t.lstrip().startswith("Cronjob Response:"):
        _h, _s, rest = t.partition("-------------")
        t = re.split(r"\nTo stop or manage this job", (rest or "").strip(), maxsplit=1)[0].strip()
    return t


def _send_ok(res: Any) -> bool:
    """把发送结果统一判成 bool —— ``success`` 可能是布尔，也可能是方法（两种都见过，别炸也别双发）。"""
    if res is None:
        return False
    v = getattr(res, "success", False)
    try:
        v = v() if callable(v) else v
    except Exception:
        return False
    return bool(v)


def _ensure_send_cardify(adapter: Any) -> bool:
    """给适配器**类**装出站卡化包装（幂等；类级补丁对新实例同样有效）。

    参数可以是实例或类本身 —— 类出现的那一刻（batch hook 安装时）就该装上，
    否则在无人发消息的时间段里，定时投递会以原始文本漏出去。
    """
    if not _SEND_CARDIFY or adapter is None:
        return False
    try:
        cls = adapter if isinstance(adapter, type) else type(adapter)
        # 2026-10-04 洁癖档批3：改用 _Guard 版本门控（与其余补丁族一致）。
        # 旧版布尔标记（True）经 _mk 读为 1 < _CODE_V → 自动触发重装；旧 _Guard 也按代数比较。
        if _mk(cls, "_fmb_send_cardify") >= _CODE_V:
            return True
        orig = getattr(cls, "_feishu_send_with_retry", None)
        # 剥链：上一次安装的包装保留真身在 _hermes_orig，这里收敛回原始实现，防套娃。
        if getattr(orig, "_fmb_cardify_wrapped", False):
            orig = getattr(orig, "_hermes_orig", orig)
        if orig is None or not callable(orig):
            # 2026-10-04 审计修复：官方改名/重构时这里会静默失效（出站卡化消失）——留告警痕迹。
            _warn_once(("cardify-noattr", cls.__name__),
                       "[FeishuMenuBridge] 出站卡化：%s 缺 _feishu_send_with_retry（官方改名？）——卡化静默失效",
                       cls.__name__)
            return False

        async def _patched_send(self, *args, **kwargs):
            try:
                msg_type = str(kwargs.get("msg_type") or "")
                chat_id = str(kwargs.get("chat_id") or "")
                text = ""
                if msg_type in ("text", "post"):
                    text = _cardify_extract_text(msg_type, str(kwargs.get("payload") or ""))
                key = _cardify_key(text) if text else ""
                try:
                    # 定向诊断：疑似机器文本却没命中时记一行（低频、不刷屏），便于发现入口/形状变化
                    if text and not key and ("Cronjob" in text or "AI 模型服务" in text):
                        logger.warning("[FeishuMenuBridge] 出站机器文本未命中：type=%s head=%r",
                                       msg_type, text[:80])
                except Exception:
                    pass
                if key and chat_id:
                    now = time.time()
                    _cool = False
                    if key.startswith("err_") and now - _SEND_CARDIFY_LAST.get(key, 0.0) < _SEND_CARDIFY_COOLDOWN:
                        _cool = True
                    if key == "busy" and now - _BUSY_CARD_LAST.get(chat_id, 0.0) < _BUSY_CARD_COOLDOWN:
                        _cool = True
                    if _cool:
                        logger.info("[FeishuMenuBridge] 出站卡化冷却跳过 %s", key)
                    else:
                        card = None
                        if key == "cron_ok":
                            head, _sep, rest = text.partition("-------------")
                            name = ""
                            m = re.match(r"\s*Cronjob Response:\s*(.*)", (head or "").splitlines()[0] if head else "")
                            if m:
                                name = (m.group(1) or "").strip()
                            jm = re.search(r"\(job_id:\s*([^)]+)\)", head or "")
                            jid = jm.group(1).strip() if jm else ""
                            body = re.split(r"\nTo stop or manage this job", (rest or "").strip(),
                                            maxsplit=1)[0].strip()
                            card = await asyncio.to_thread(build_cron_result_card, name, jid, body)
                        elif key == "cron_fail":
                            card = await asyncio.to_thread(build_cron_fail_card, _strip_cron_wrap(text))
                        elif key == "bg_ok":
                            if _pt_quiet_active():
                                try:
                                    _pt_defer_bg(text, chat_id, self)
                                    logger.info("[FeishuMenuBridge] PT 静音窗：后台完成提示转入延迟队列（%d 字）", len(text))
                                    return _SILENT_OK   # A5/A6：延迟补发 + 伪成功响应
                                except Exception:
                                    logger.warning("[FeishuMenuBridge] PT 静音窗延迟入队失败，改走正常完成卡", exc_info=True)
                            card = await asyncio.to_thread(build_bg_done_card, text, True)
                        elif key == "bg_fail":
                            # A7 + E3：失败通知**永不静音**——失败可见性优先；照常发卡（延迟补发不适用于失败）。
                            card = await asyncio.to_thread(build_bg_done_card, text, False)
                        elif key == "busy":
                            card = await asyncio.to_thread(build_busy_ack_card, text)
                        elif key.startswith("err_"):
                            card = await asyncio.to_thread(build_error_card, text, key)
                        if card is not None:
                            res = await _send_card(self, chat_id, card)
                            if _send_ok(res):
                                _SEND_CARDIFY_LAST[key] = time.time()
                                if key == "busy":
                                    _BUSY_CARD_LAST[chat_id] = time.time()
                                logger.info("[FeishuMenuBridge] 出站文本→卡片 %s（原文 %d 字）", key, len(text))
                                return res
                            logger.warning("[FeishuMenuBridge] 出站卡化发送失败，放行原文 %s", key)
            except Exception:
                logger.warning("[FeishuMenuBridge] 出站卡化异常，放行原文", exc_info=True)
            return await orig(self, *args, **kwargs)

        _patched_send._fmb_cardify_wrapped = True
        _patched_send._hermes_orig = orig
        cls._feishu_send_with_retry = _patched_send
        # ── E1 修复：整文级卡化包装（分片在 send() 内、早于 _feishu_send_with_retry）──
        # 片级包装只对首片生效 → 长文 >8000 时中段丢失、尾部裸片。这里在 truncate_message
        # 之前拿到完整文本，命中前缀即整文卡化；卡面截断的溢出正文再经官方分片补发，零丢失。
        orig_send = getattr(cls, "send", None)
        if getattr(orig_send, "_fmb_cardify_send", False):
            orig_send = getattr(orig_send, "_hermes_orig_send", orig_send)

        async def _patched_send_whole(self, chat_id, content, *args, **kwargs):
            try:
                # 只处理纯文本入参；卡片/interactive 走 dict，直接放行，避免递归 _send_card
                if isinstance(content, str) and chat_id:
                    full = self.format_message(content) if hasattr(self, "format_message") else content
                    key = _cardify_key(full)
                    if key:
                        card, overflow = _cardify_build(key, full)
                        if card is not None:
                            res = await _send_card(self, chat_id, card)
                            if _send_ok(res):
                                if overflow:
                                    # 溢出正文（卡面 1800 之外）走官方分片续发，保证全文可达
                                    await orig_send(self, chat_id, overflow, *args, **kwargs)
                                logger.info("[FeishuMenuBridge] 整文卡化 %s（原文 %d 字，溢出 %d 字）",
                                            key, len(full), len(overflow))
                                return res
            except Exception:
                logger.warning("[FeishuMenuBridge] 整文卡化异常，放行原文", exc_info=True)
            return await orig_send(self, chat_id, content, *args, **kwargs)

        _patched_send_whole._fmb_cardify_send = True
        _patched_send_whole._hermes_orig_send = orig_send
        cls.send = _patched_send_whole
        cls._fmb_send_cardify = _Guard(_CODE_V)
        logger.info("[FeishuMenuBridge] 出站卡化包装已装到 %s", cls.__name__)
        return True
    except Exception:
        logger.warning("[FeishuMenuBridge] 装出站卡化包装失败", exc_info=True)
        return False


CARD_BUILDERS = {
    "面板": build_panel_card,
    "系统": build_system_card,
    "系统详情": build_system_detail_card,
    "PT": build_pt_card,
    "技能": build_skills_card,
    "帮助": build_help_card,
    "用量": build_usage_card,
    "命令表": build_commands_card,
    "人格": build_personality_card,
    "状态": build_status_card,
    "推理": build_reasoning_card,
    "任务": build_tasks_card,
    "洞察": build_insights_card,
    "忙时": build_busy_card,
    "版本": build_version_card,
}

#: 带页码参数的卡片（build_card 会多传一个 page）
PAGED_CARDS = {"命令表", "技能", "人格"}


def build_card(name: str, chat_id: str = "", page: int = 1) -> Optional[Dict[str, Any]]:
    fn = CARD_BUILDERS.get(name)
    if fn is None:
        return None
    try:
        return fn(chat_id, page) if name in PAGED_CARDS else fn(chat_id)
    except Exception:
        logger.warning("[FeishuMenuBridge] build card %s failed", name, exc_info=True)
        return None


# ── 发送 ────────────────────────────────────────────────────────

def _feishu_adapter(gateway: Any, source: Any = None):
    try:
        from gateway.config import Platform
    except Exception:
        return None
    try:
        if source is not None:
            adapter = gateway._delivery_adapter_for(source)
            if adapter is not None:
                return adapter
    except Exception:
        pass
    try:
        return (getattr(gateway, "adapters", None) or {}).get(Platform.FEISHU)
    except Exception:
        return None


async def _send_card(adapter: Any, chat_id: str, card: Dict[str, Any]) -> Any:
    payload = json.dumps(card, ensure_ascii=False)
    resp = await adapter._feishu_send_with_retry(
        chat_id=chat_id, msg_type="interactive", payload=payload,
        reply_to=None, metadata=None,
    )
    ok = _send_ok(resp)
    body = dict(card.get("body") or {})
    els = list(body.get("elements") or [])
    # 退化链：被拒时先去掉折叠面板，再去掉图表组件（客户端版本旧时兜底）
    for drop in ({"collapsible_panel"}, {"collapsible_panel", "chart"}):
        if ok:
            break
        kept = [e for e in els if not (isinstance(e, dict) and e.get("tag") in drop)]
        if len(kept) == len(els):
            continue
        resp = await adapter._feishu_send_with_retry(
            chat_id=chat_id, msg_type="interactive",
            payload=json.dumps({**card, "body": {**body, "elements": kept}}, ensure_ascii=False),
            reply_to=None, metadata=None,
        )
        ok = _send_ok(resp)
    return resp


async def _send_text(adapter: Any, chat_id: str, text: str) -> None:
    try:
        await adapter._feishu_send_with_retry(
            chat_id=chat_id, msg_type="text",
            payload=json.dumps({"text": text}, ensure_ascii=False),
            reply_to=None, metadata=None,
        )
    except Exception:
        logger.warning("[FeishuMenuBridge] text fallback failed", exc_info=True)


# ── 钩子：菜单名 → 命令 / 卡片 ──────────────────────────────────

def _sender_authorized(gateway: Any, source: Any) -> bool:
    """复用网关自己的授权判断（与 ``_hm_admit_event`` 同一个谓词）。

    仅用于「要发卡并吞掉消息」的路径。未授权 / 判断抛异常 / 谓词不存在，一律按**未授权**处理
    （fail-closed），调用方必须放行原文，让网关照常走配对或拒绝。绝不在此改写或丢弃消息。
    """
    if gateway is None or source is None:
        return False
    try:
        check = getattr(gateway, "_is_user_authorized_for_source", None)
        if check is None:
            logger.warning("[FeishuMenuBridge] 网关无 _is_user_authorized_for_source；"
                           "按未授权处理（菜单卡片暂停，避免越权发卡）")
            return False
        return bool(check(source))
    except Exception:
        logger.warning("[FeishuMenuBridge] 授权判断异常，按未授权处理", exc_info=True)
        return False


async def _on_pre_gateway_dispatch(**kwargs: Any) -> Optional[dict]:
    event = kwargs.get("event")
    gateway = kwargs.get("gateway")
    if event is None or gateway is None:
        return None
    try:
        source = getattr(event, "source", None)
        platform = getattr(getattr(source, "platform", None), "value", None)
        if platform != "feishu":
            return None
        chat_id = str(getattr(source, "chat_id", "") or "")
        text = str(getattr(event, "text", "") or "").strip()
        if not text or chat_id == "":
            return None
        # F01（审计修复）：本钩子由上游在**鉴权之前**调用（run_inbound._hm_admit_event：
        # 先跑本钩子，再查 _is_user_authorized_for_source）。所以发卡 / 吞消息之前必须先
        # 复用网关的授权判断；未授权一律 return None 放行原文，交回网关的配对 / 拒绝流程
        # —— 保留菜单改写能力，但不越权发卡。
        if not _sender_authorized(gateway, source):
            logger.info("[FeishuMenuBridge] 未授权来源，跳过菜单处理（交回网关）：chat=%s", chat_id)
            return None
        # 记录来源，供卡片按钮回注消息时复用（加锁 + 快照迭代，避免并发改 dict 抛异常）
        with _STATE_LOCK:
            _SOURCES[chat_id] = source
            _SOURCES_TS[chat_id] = time.time()
            if len(_SOURCES) > 64:
                for k in sorted(list(_SOURCES_TS), key=lambda k: _SOURCES_TS.get(k, 0.0))[:16]:
                    _SOURCES.pop(k, None)
                    _SOURCES_TS.pop(k, None)

        # 每次入站（任意消息）都补一次**活对象自己的类**上的卡片回调补丁：
        # 这是拿到线上适配器实例最可靠的途径（gc 被冻结时扫不到旧对象）。
        global _LAST_ROUTE_TS
        if time.time() - _LAST_ROUTE_TS > 10.0:
            _LAST_ROUTE_TS = time.time()
            _ad = _feishu_adapter(gateway, source)
            if _ad is not None:
                try:
                    await asyncio.to_thread(_ensure_card_routing, _ad)
                except Exception:
                    logger.warning("[FeishuMenuBridge] inbound routing patch failed", exc_info=True)
                try:
                    await asyncio.to_thread(_ensure_send_cardify, _ad)
                except Exception:
                    logger.warning("[FeishuMenuBridge] send cardify patch failed", exc_info=True)
            # 2026-10-04 修：busy hook 是次高价扫描（sys.modules + dir(cls)），原每条消息都全量跑；
            # 移入 10s 节流，异常不再静默吞掉（原 except Exception: pass 无日志）。
            try:
                await asyncio.to_thread(_install_busy_hook)
            except Exception:
                logger.warning("[FeishuMenuBridge] busy hook install failed", exc_info=True)

        # 菜单名可能带开头图标（📊面板）→ 统一走 _resolve_menu_key（四处共用一份）
        key = _resolve_menu_key(text) or text

        # 直输斜杠命令 → 同一张卡（失败/异常一律放行官方文本路径，不吞消息）
        _slash = _SLASH_CARD_MAP.get(text)
        if _slash is not None and _slash in CARD_BUILDERS:
            _ad_s = _feishu_adapter(gateway, source)
            if _ad_s is not None:
                _card_s = await asyncio.to_thread(build_card, _slash, chat_id)
                if _card_s is not None:
                    await asyncio.to_thread(_ensure_card_routing, _ad_s)
                    _ok_s = False
                    try:
                        _resp_s = await asyncio.wait_for(_send_card(_ad_s, chat_id, _card_s), timeout=20)
                        _ok_s = _send_ok(_resp_s)
                    except Exception:
                        logger.warning("[FeishuMenuBridge] slash card %s failed", text, exc_info=True)
                    if _ok_s:
                        logger.info("[FeishuMenuBridge] slash %r → card %r", text, _slash)
                        return {"action": "skip", "reason": "feishu slash card: %s" % _slash}
                    logger.warning("[FeishuMenuBridge] slash card %s not delivered; 放行官方文本", text)

        if key in COMMANDS:
            logger.info("[FeishuMenuBridge] rewrite %r → %r", text, COMMANDS[key])
            return {"action": "rewrite", "text": COMMANDS[key]}

        if key in CARD_BUILDERS:
            adapter = _feishu_adapter(gateway, source)
            card = await asyncio.to_thread(build_card, key, chat_id)
            if adapter is None or card is None:
                # 发不了卡片就不要吞掉这条消息：放行原文，让它照常进 agent
                logger.warning("[FeishuMenuBridge] card %r 无法发送 (adapter=%s card=%s)；放行原文",
                               key, adapter is not None, card is not None)
                return None
            # 已连接的适配器可能是在插件加载前建的分发器 → 先补挂卡片回调
            await asyncio.to_thread(_ensure_card_routing, adapter)
            ok = False
            try:
                resp = await asyncio.wait_for(_send_card(adapter, chat_id, card), timeout=20)
                ok = _send_ok(resp)
            except Exception:
                logger.warning("[FeishuMenuBridge] card send failed for %s", key, exc_info=True)
            if not ok:
                logger.warning("[FeishuMenuBridge] card %r NOT delivered; falling back to text", key)
                await _send_text(adapter, chat_id,
                                 "卡片没发出去。可以发 /commands 看命令清单，或稍后再点一次。")
                return {"action": "skip", "reason": f"feishu menu card fallback: {text}"}
            logger.info("[FeishuMenuBridge] card %r sent, dispatch skipped", key)
            return {"action": "skip", "reason": f"feishu menu card: {key}"}
    except Exception:
        logger.warning("[FeishuMenuBridge] pre_gateway_dispatch error", exc_info=True)
    return None


# ── 卡片按钮 → 回注消息 ─────────────────────────────────────────

def _synth_source(chat_id: str, open_id: str = "") -> Any:
    """没有历史 source 时（网关刚重启、用户直接点卡）按会话信息合成一个，别让点击静默失效。"""
    try:
        from gateway.config import Platform
        from gateway.session import SessionSource
        return SessionSource(platform=Platform.FEISHU, chat_id=chat_id, chat_type="dm",
                             user_id=open_id or None)
    except Exception:
        logger.warning("[FeishuMenuBridge] 合成 source 失败", exc_info=True)
        return None


async def _inject(adapter: Any, chat_id: str, text: str, open_id: str = "") -> None:
    from gateway.platforms.event import MessageEvent, MessageType
    source = _SOURCES.get(chat_id)
    # 2026-10-07 审计修复（#6）：群聊里 _SOURCES[chat_id] 存的是**最后一个发言者**的
    # source，而点卡的人未必是他 —— 沿用会拿别人的身份去执行菜单命令。带上点击者
    # open_id 且与缓存 source 不一致时，克隆一份只换 user_id（保留 chat_type 等字段；
    # 克隆失败退回 _synth_source）。DM 里两者一致，行为完全不变。
    if open_id and getattr(source, "user_id", None) != open_id:
        _fresh = None
        try:
            import dataclasses as _dc
            _fresh = _dc.replace(source, user_id=open_id)
        except Exception:
            _fresh = None
        if _fresh is None:
            _fresh = _synth_source(chat_id, open_id)
        if _fresh is not None:
            source = _fresh
    if source is None:
        source = _synth_source(chat_id, open_id)
        if source is not None:
            # 2026-10-04 修：与 :2611 同锁纪律——`_SOURCES/_SOURCES_TS` 的一切写操作持 _STATE_LOCK。
            with _STATE_LOCK:
                _SOURCES[chat_id] = source
                _SOURCES_TS[chat_id] = time.time()
    if source is None:
        logger.warning("[FeishuMenuBridge] no source for chat %s; cannot inject", chat_id)
        return
    ev = MessageEvent(
        text=text, message_type=MessageType.TEXT, source=source,
        metadata={"feishu_menu_bridge": True},
    )
    try:
        await adapter.handle_message(ev)
    except Exception:
        logger.warning("[FeishuMenuBridge] inject failed: %r", text, exc_info=True)


async def _recall(adapter: Any, message_id: str) -> None:
    """撤回卡片消息（机器人可撤回自己发的消息）；失败就留着，不报错给用户。"""
    try:
        from lark_oapi.api.im.v1 import DeleteMessageRequest
        req = DeleteMessageRequest.builder().message_id(message_id).build()
        resp = await asyncio.to_thread(adapter._client.im.v1.message.delete, req)
        ok = _send_ok(resp)
        logger.info("[FeishuMenuBridge] recall %s ok=%s code=%s", message_id, ok, getattr(resp, "code", None))
    except Exception:
        logger.warning("[FeishuMenuBridge] recall failed for %s", message_id, exc_info=True)


# ── 卡片点击动作（原为 _handle_card_click 内嵌闭包，逐字搬为模块级；形参名=原自由变量名）──


def _not_delivered() -> Any:
    """「操作未送达（连接中）」统一守卫（原来 6 处逐字节重复）。"""
    return _toast("操作未送达（连接中），请稍后再试", "warning")


def _closed_card() -> Dict[str, Any]:
    """「已收起」收尾卡：点 ✕ 时把原卡**原地换成它**（不撤回 —— 撤回会留下「撤回了一条消息」）。"""
    return {
        "schema": "2.0",
        "config": {"update_multi": True, "summary": {"content": "已收起"}},
        "header": {"title": {"tag": "plain_text", "content": "🌙 已收起"}, "template": "grey"},
        "body": {"elements": [
            {"tag": "markdown", "content": "需要时从底部菜单再打开即可。"},
        ]},
    }


async def _close_card(adapter: Any, mid: str) -> None:
    """收起动作：优先原地改写成「已收起」小卡；改写不动才回退撤回（保功能可用）。"""
    try:
        ok, why = await _patch_card(adapter, mid, _closed_card())
        if ok:
            return
        logger.warning("[FeishuMenuBridge] 收起原地改写失败 %s，回退撤回", why)
    except Exception:
        logger.warning("[FeishuMenuBridge] 收起原地改写异常，回退撤回", exc_info=True)
    await _recall(adapter, mid)


async def _repost_card(adapter: Any, chat_id: str, card_name: Any) -> None:
    c = await asyncio.to_thread(build_card, str(card_name), chat_id)
    if c is None:
        logger.warning("[FeishuMenuBridge] 换卡 %r 构建失败（返回空）", card_name)
        return
    res = await _send_card(adapter, chat_id, c)
    if not _send_ok(res):
        # 2026-10-04 审计修复：换卡失败此前无检查无日志，用户表现为「点了没反应」。
        logger.warning("[FeishuMenuBridge] 换卡 %r 未投递（用户可能表现为点击后无反应）", card_name)


async def _flip_card(adapter: Any, chat_id: str, mid: str, _card_name: str, _page_no: int) -> None:
    c = await asyncio.to_thread(build_card, _card_name, chat_id, _page_no)
    if c is None:
        return
    try:
        ok, why = await _patch_card(adapter, mid, c)
        if not ok:
            logger.warning("[FeishuMenuBridge] 翻页原地更新失败 %s", why)
            # 2026-10-04 审计修复：此前 toast 已先报「第 N 页」，失败仅写日志 → 用户不知情。
            await _send_text(adapter, chat_id, "⚠️ 翻页没成功（网络抖动？）——再点一次试试")
        else:
            logger.info("[FeishuMenuBridge] 翻页 %s → %s OK", mid[-8:], _page_no)
    except Exception:
        logger.warning("[FeishuMenuBridge] 翻页原地更新异常", exc_info=True)
        await _send_text(adapter, chat_id, "⚠️ 翻页没成功（网络抖动？）——再点一次试试")


async def _wave_card(adapter: Any, chat_id: str, ctx: Any, wave_range: Any) -> None:
    """波形档位切换。注意：mid / _wave_state() 必须在协程运行时求值（时序不能提前）。"""
    import subprocess
    try:
        r = await asyncio.to_thread(
            subprocess.run,
            [_PY_BIN, _HOME_DIR + "/tools/usage_wave.py", "tap", str(wave_range)],
            capture_output=True, text=True, timeout=90)
        logger.warning("[FeishuMenuBridge] 波形切换 %s rc=%s %s",
                       wave_range, r.returncode, (r.stdout or "").strip())
    except Exception:
        logger.warning("[FeishuMenuBridge] 波形切换失败 range=%s", wave_range, exc_info=True)
    # 点的是独立波形卡（卡片实体那条消息）时，usage_wave.py 已经把实体更新好了；
    # 点的是「用量卡」里那块波形时，那张是普通 card_json 消息，得原地换成新档位。
    mid = str(getattr(ctx, "open_message_id", "") or "")
    if not mid or mid == str(_wave_state().get("message_id") or ""):
        return
    try:
        c = await asyncio.to_thread(build_card, "用量", chat_id)
        if c is None:
            return
        ok, why = await _patch_card(adapter, mid, c)
        if not ok:
            logger.warning("[FeishuMenuBridge] 用量卡波形原地更新失败 %s", why)
            # 2026-10-04 审计修复：同 _flip_card —— 失败给用户一个可见回执。
            await _send_text(adapter, chat_id, "⚠️ 档位切换没成功（网络抖动？）——再点一次试试")
    except Exception:
        logger.warning("[FeishuMenuBridge] 用量卡波形原地更新异常", exc_info=True)
        await _send_text(adapter, chat_id, "⚠️ 档位切换没成功（网络抖动？）——再点一次试试")


async def _refresh_card(adapter: Any, chat_id: str, mid: str, name: Any,
                        override: Optional[str] = None, *, delayed: bool = False) -> None:
    """点后把**同一张卡**原地刷新——两种节奏合一（2026-10-04 洁癖档批2，原 _refresh_card + _refresh_card_delayed）。

    · 默认（刷新按钮）：重建一次 + PATCH 一次；失败退回「改发新卡」。
    · delayed=True（命令型按钮 /reasoning /busy /personality）：立即乐观首刷（override 只作用首刷）
      → 2.2 秒真值校正；与首刷一致则跳过；同卡连点时旧任务让位。
    """
    if not delayed:
        c = await asyncio.to_thread(build_card, str(name), chat_id)
        if c is None:
            return
        try:
            ok, why = await _patch_card(adapter, mid, c)
            if ok:
                return
            logger.warning("[FeishuMenuBridge] 刷新原地更新失败 %s，改发新卡", why)
        except Exception:
            logger.warning("[FeishuMenuBridge] 刷新原地更新异常，改发新卡", exc_info=True)
        await _send_card(adapter, chat_id, c)
        return
    try:
        _seq = _REFRESH_SEQ.get(mid, 0) + 1
        if len(_REFRESH_SEQ) > 256:
            # 2026-10-04 修：原 clear() 连在途延迟刷新的 mid 一起清 → 其「让位」保护失效，
            # 旧任务可能乱序把旧值盖回新卡。改成只淘汰最早插入的 64 个键（dict 保序），
            # 其余在途 mid 的 _seq 序列不受影响。
            for _k in list(_REFRESH_SEQ)[:64]:
                _REFRESH_SEQ.pop(_k, None)
        _REFRESH_SEQ[mid] = _seq
        _prev_json = None
        for _i, _wait in enumerate((0.0, 2.2)):
            if _wait:
                await asyncio.sleep(_wait)
            if _REFRESH_SEQ.get(mid) != _seq:
                logger.info("[FeishuMenuBridge] 刷新 %s 第%d次 跳过：已有更新的点击接管", name, _i + 1)
                return
            try:
                if _i == 0 and name == "推理" and override:
                    card = await asyncio.to_thread(build_reasoning_card, chat_id, override)
                else:
                    card = await asyncio.to_thread(build_card, name, chat_id)
            except Exception:
                card = None
            if card is None:
                logger.warning("[FeishuMenuBridge] 刷新 %s 跳过：build 返回空", name)
                return
            if _i == 1 and _prev_json is not None:
                try:
                    if json.dumps(card, sort_keys=True, ensure_ascii=False) == _prev_json:
                        logger.info("[FeishuMenuBridge] 刷新 %s 第2次 跳过：与首刷一致（已对时）", name)
                        return
                except Exception:
                    pass
            ok, why = await _patch_card(adapter, mid, card)
            logger.info("[FeishuMenuBridge] 刷新 %s 第%d次 %s", name, _i + 1,
                        "OK" if ok else ("失败 " + str(why)))
            if ok:
                if _i == 0:
                    try:
                        _prev_json = json.dumps(card, sort_keys=True, ensure_ascii=False)
                    except Exception:
                        _prev_json = None
                else:
                    return
    except Exception:
        logger.warning("[FeishuMenuBridge] 延迟刷新异常 %s", name, exc_info=True)


def _ctx_mid(ctx: Any) -> str:
    """从回调 ctx 提取 open_message_id（4 处曾各自展开，统一走这里）。"""
    return str(getattr(ctx, "open_message_id", "") or "")


def _click_guard(loop: Any, mid: str, what: str, detail: str = "", need_mid: bool = False):
    """统一的「loop/mid 可用性」守卫：合格返回 None，不合格打日志并给未送达响应。

    2026-10-04 洁癖档批2：原函数里 6 段分支各自复制同一段判断，收敛到此处。
    """
    if loop is None or (need_mid and not mid):
        logger.warning("[FeishuMenuBridge] %s未送达：loop%s不可用 %s", what,
                       "/message_id" if need_mid else "", detail)
        return _not_delivered()
    return None


def _handle_card_click(adapter: Any, event: Any, value: Dict[str, Any]):
    try:
        ctx = getattr(event, "context", None)
        chat_id = str(getattr(ctx, "open_chat_id", "") or getattr(ctx, "chat_id", "") or "")
        operator = getattr(event, "operator", None)
        open_id = str(getattr(operator, "open_id", "") or "")
        try:
            authorized = adapter._is_interactive_operator_authorized(open_id)
        except Exception:
            logger.warning("[FeishuMenuBridge] 操作人鉴权异常，按未授权处理", exc_info=True)
            authorized = False
        if not authorized:
            return adapter._card_response(_card("⛔ 无权限", "red", [_md("此操作仅限授权操作人。")]))

        loop = _usable_loop(adapter)
        if loop is None:
            # 本实例 loop 不可用（尚未连上/已关闭）→ 试试其它活实例
            for _a in _live_adapters():
                if _a is adapter:
                    continue
                _l = _usable_loop(_a)
                if _l is not None:
                    adapter, loop = _a, _l
                    break

        # 收起：**原地换成「已收起」小卡**（不撤回，避免「撤回了一条消息」那条丑提示）
        if value.get("hermes_menu_close"):
            mid = _ctx_mid(ctx)
            if _bad := _click_guard(loop, mid, "收起", "mid=%s" % bool(mid), need_mid=True):
                return _bad
            adapter._submit_on_loop(loop, _close_card(adapter, mid))
            return _toast("已收起")

        cmd = value.get("hermes_menu_cmd")
        card_name = value.get("hermes_menu_card")
        if cmd:
            # 2026-10-07：能力门控（见 _cmd_btn 的 require 参数）。旧卡（渲染时有能力、
            # 点击时没了）也拦得住——否则会回注一条模型读不懂的命令、白烧 token。
            _need = str(value.get("hermes_menu_require") or "")
            if _need and not _cap_ok(_need):
                return _toast(_CAP_HINT.get(_need,
                               "本机未配置该能力（%s），已跳过" % _need), "warning")
            _cmd_s = str(cmd)
            if _bad := _click_guard(loop, "", "命令", "cmd=%s" % _cmd_s):
                return _bad
            adapter._submit_on_loop(loop, _inject(adapter, chat_id, _cmd_s, open_id))
            # 状态类命令（改配置→卡面跟着变的那种）：等命令生效后把**这张卡原地刷新**
            _mid = _ctx_mid(ctx)
            _rk = next((v for k, v in _CMD_REFRESH_CARD.items() if _cmd_s.startswith(k)), None)
            if _rk and _mid:
                # 乐观值：从命令里抽第一参数（/reasoning max --global → "max"）
                _ov = None
                try:
                    _parts = _cmd_s.split()
                    if len(_parts) >= 2 and not _parts[1].startswith("-"):
                        _ov = _parts[1]
                except Exception:
                    _ov = None
                adapter._submit_on_loop(loop, _refresh_card(adapter, chat_id, _mid, _rk, _ov, delayed=True))
                return _toast("已切换 ✓ 卡片即将刷新")
            if _rk:
                logger.warning("[FeishuMenuBridge] 刷新 %s 跳过：ctx 里没有 open_message_id", _rk)
                return _toast("已执行，但卡片未能自动刷新（请重开面板）", "warning")
            return _toast(f"已执行 {cmd}")
        if card_name:
            if _bad := _click_guard(loop, "", "换卡", "card=%s" % card_name):
                return _bad
            adapter._submit_on_loop(loop, _repost_card(adapter, chat_id, card_name))
            return adapter._card_response()
        page_spec = value.get("hermes_menu_page")
        if isinstance(page_spec, dict) and page_spec.get("card"):
            mid = _ctx_mid(ctx)
            _card_name = str(page_spec.get("card") or "")
            try:
                _page_no = int(page_spec.get("page") or 1)
            except Exception:
                _page_no = 1
            if _bad := _click_guard(loop, mid, "翻页", "mid=%s" % bool(mid), need_mid=True):
                return _bad
            adapter._submit_on_loop(loop, _flip_card(adapter, chat_id, mid, _card_name, _page_no))
            return _toast(f"第 {_page_no} 页")

        wave_range = value.get("hermes_menu_wave")
        if wave_range:
            if _bad := _click_guard(loop, "", "波形切换", "range=%s" % wave_range):
                return _bad
            adapter._submit_on_loop(loop, _wave_card(adapter, chat_id, ctx, wave_range))
            return _toast("已切到 %s" % wave_range)

        refresh_name = value.get("hermes_menu_refresh")
        if refresh_name:
            mid = _ctx_mid(ctx)
            if _bad := _click_guard(loop, mid, "刷新", "mid=%s" % bool(mid), need_mid=True):
                return _bad
            adapter._submit_on_loop(loop, _refresh_card(adapter, chat_id, mid, refresh_name))
            return _toast("已刷新")
        return adapter._card_response()
    except Exception:
        logger.warning("[FeishuMenuBridge] card click error", exc_info=True)
        try:
            return adapter._card_response()
        except Exception:
            return None


# ── 装入官方卡片回调通道 ────────────────────────────────────────

_MARKER_VER = "_hermes_menu_bridge_code_v"
_MARKER_DO = "_hermes_menu_bridge_dispatcher_v"
# 2026-10-05 D2：三族裸布尔标记的数值版本位（旧布尔仍写，仅供遗留读取）
_MARKER_SENDFINAL = "_fmb_sendfinal_v"
_MARKER_PTGATE = "_fmb_ptgate_v"
_MARKER_RES2 = "_fmb_res2_v"
_MARKER_SLASHH = "_fmb_slashhandler_v"


def _ns(**kw: Any) -> Any:
    from types import SimpleNamespace
    return SimpleNamespace(**kw)


class _Guard(int):
    """版本守卫：让**旧版插件实例**的 `== 旧版本号` 判断同样为真，避免它们反复覆盖新补丁。

    多份插件模块实例（多次热加载）各有自己的 watcher 线程；用普通整数做标记时，
    旧实例永远判定「未安装」并不断重装，把新补丁套在旧补丁外面。
    """

    def __eq__(self, other: Any) -> bool:  # type: ignore[override]
        return isinstance(other, int) and int(other) <= int(self)

    def __ne__(self, other: Any) -> bool:  # type: ignore[override]
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return int.__hash__(self)


def _mk(obj: Any, name: str) -> int:
    """读版本标记（非整数视为 0）。多份插件实例并存时，只允许更高版本覆盖。"""
    try:
        v = getattr(obj, name, 0)
        return v if isinstance(v, int) else 0
    except Exception:
        logger.debug("[FeishuMenuBridge] _mk 读取标记失败：%s", name, exc_info=True)
        return 0

_CODE_V = 117  # 改本文件里任何「卡片/点击」逻辑时 +1：强制重建已连接的分发器
              # 109 = 2026-10-05 已处理卡并入插件视觉体系 + 斜杠确认卡带命令名
              # 110 = 2026-10-07 F01 修复：发卡/吞消息前先复用网关授权判断（钩子 + 批处理）
              # 115 = 2026-10-07 PT 签到按钮改**能力门控**：装了 pt-site-keepalive 技能才渲染/才可点
# 116 = 2026-10-08 系统卡「📊 详情」误指洞察 → 新增「系统详情」卡并指向它


def _is_our_value(value: Any) -> bool:
    """判断卡片按钮 value 是否属于本插件（任一键命中即可）。

    规则：新加的键**必须以 `hermes_menu_` 开头**。这里用前缀判定，与 `_intercept_card_action`
    的原始字符串快速过滤（`"hermes_menu_" not in raw`）**口径一致**——凡能过快速过滤的键，
    这里都认，不再出现「过了快筛却被白名单静默丢弃（无日志）」的坑。
    """
    return isinstance(value, dict) and any(
        isinstance(k, str) and k.startswith("hermes_menu_") for k in value
    )


def _adapter_usable(a: Any) -> bool:
    """粗判适配器是否还活着（ws 在、loop 未关）；用于剔除断线后的死实例。"""
    try:
        ws = getattr(a, "_ws_client", None)
        loop = getattr(a, "_loop", None)
        if ws is None or loop is None:
            return False
        is_closed = getattr(loop, "is_closed", None)
        return not (callable(is_closed) and is_closed())
    except Exception:
        return False


def _usable_loop(a: Any) -> Any:
    """取适配器上可用的 loop（不可用返回 None），替代裸的 adapter._loop 访问。"""
    try:
        loop = getattr(a, "_loop", None)
        if loop is not None and a._loop_accepts_callbacks(loop):
            return loop
    except Exception:
        pass
    return None


_DROP_COUNT: Dict[str, int] = {}
_STATE_LOCK = threading.Lock()
_INSTALL_LOCK = threading.Lock()
_LIVE_CACHE: List[Any] = []
_LIVE_CACHE_TS = 0.0


def _count_drop(key: str, msg: str, *args: Any) -> int:
    """静默丢弃计数：前 3 次与每 50 次打一条 error —— 既暴露丢弃率，又不刷屏。
    计数在 _STATE_LOCK 里做（并发点击下 get→+1→set 非原子会丢数）。"""
    with _STATE_LOCK:
        n = _DROP_COUNT.get(key, 0) + 1
        _DROP_COUNT[key] = n
    if n <= 3 or n % 50 == 0:
        logger.error(msg + "（累计 %d 次）", *args, n)
    return n


def _sweep_stale_live_adapter() -> None:
    """断线后清理 _LIVE_ADAPTER，避免后续一直拿到死适配器。"""
    global _LIVE_ADAPTER
    try:
        if _LIVE_ADAPTER is not None and not _adapter_usable(_LIVE_ADAPTER):
            logger.info("[FeishuMenuBridge] 清理已断线的 _LIVE_ADAPTER")
            _LIVE_ADAPTER = None
    except Exception:
        pass


# ── 让「已经连上」的分发器也走我们的卡片回调 ────────────────────
# 官方适配器在 connect() 时把 self._on_card_action_trigger 的**绑定方法**注册进分发器；
# 绑定方法在注册那一刻就固定了，之后打类补丁也换不掉它 → 必须重建分发器并换给 ws 客户端
# （lark ws Client 每次分发都读 self._event_handler，换掉即刻生效）。
_LAST_ROUTE_TS = 0.0
_LIVE_ADAPTER: Any = None  # 最近一次由钩子/守护线程确认过的线上适配器


def _ensure_card_routing(adapter: Any) -> bool:
    """把「当前已连接」的分发器换成经我们包装的版本（注册早于插件加载时必需）。

    同时对**活对象自己的类**补两层（不依赖模块导入、不依赖重建时序）：
      · 分发器类：`_do_without_validation` —— 所有事件的总入口，调用期按实例的类查找；
      · 适配器类：`_handle_card_action_event` —— 官方卡片回调的异步分支。
    这样即使适配器实例来自被重新导入前的旧类对象，也一定被拦到。
    """
    global _LIVE_ADAPTER
    if _adapter_usable(adapter):
        _LIVE_ADAPTER = adapter
    done = False
    try:
        h = getattr(adapter, "_event_handler", None)
        if h is not None:
            done = _patch_dispatcher_class(type(h)) or done
        # ws 客户端手里的分发器可能是**另一个对象、甚至另一个类对象**（模块被重新导入时）
        ws = getattr(adapter, "_ws_client", None)
        wh = getattr(ws, "_event_handler", None) if ws is not None else None
        if wh is not None and wh is not h:
            done = _patch_dispatcher_class(type(wh)) or done
        if ws is not None:
            done = _patch_ws_class(type(ws)) or done
        done = _patch_adapter_class(type(adapter)) or done
        # 不再重建分发器：分发器层的拦截对当前连接已即时生效，重建反而可能换上
        # 由旧版包装器构建的分发器（其注册函数拿不到适配器引用）。
    except Exception:
        logger.warning("[FeishuMenuBridge] card routing rewire failed", exc_info=True)
    return done


def _live_adapters(ttl: float = 5.0) -> List[Any]:
    """gc 扫描活着的飞书适配器实例（带 TTL 缓存：全堆扫描很贵，稳态每 5 秒一次即可）。

    按**类名 + 属性**判定（鸭子类型），不用 isinstance：平台插件被重新导入后会生成新的
    类对象，而线上实例仍属于旧类对象，isinstance 会漏掉它。
    """
    global _LIVE_CACHE, _LIVE_CACHE_TS
    now = time.monotonic()
    # 用 _LIVE_CACHE_TS 判定（不是 _LIVE_CACHE 本身）：空结果也要进缓存，
    # 否则「找不到适配器」这条最贵最常失败的路径每次都全堆 gc 重扫。
    if _LIVE_CACHE_TS and (now - _LIVE_CACHE_TS) < ttl:
        return _LIVE_CACHE
    out: List[Any] = []
    try:
        import gc
        for obj in gc.get_objects():
            try:
                cls = type(obj)
                if cls.__name__ != "FeishuAdapter":
                    continue
                if not hasattr(obj, "_event_handler") or not hasattr(obj, "_build_event_handler"):
                    continue
                out.append(obj)
            except Exception:
                continue
    except Exception:
        pass
    _LIVE_CACHE = out
    _LIVE_CACHE_TS = now
    return out


def _install_lark_builder_hook() -> bool:
    try:
        from lark_oapi.event.dispatcher_handler import EventDispatcherHandlerBuilder
    except Exception:
        return False
    if _mk(EventDispatcherHandlerBuilder, _MARKER_LARK) >= _CODE_V:
        return True
    # 2026-10-07 审计修复（#3）：取原始实现必须剥掉我们自己打的包装（_orig_of），
    # 否则升版后新包装调用旧包装、旧闭包里的判断先执行 → 新版点击逻辑被永久冻结。
    orig = _orig_of(EventDispatcherHandlerBuilder.register_p2_card_action_trigger)

    def _patched_register(self, f):
        # 2026-10-04 审计修复：本插件的包装可能被其它插件（如选单器）再包一层，
        # 那时 __self__ 丢失 —— 补一条 _hermes_adapter 取回路径，别让 adapter 变 None。
        _bound = getattr(f, "__self__", None) or getattr(f, "_hermes_adapter", None)  # 适配器实例

        def _wrapped(data):
            try:
                adapter = _bound
                ev = getattr(data, "event", None)
                action = getattr(ev, "action", None)
                _decode_option_value(action)   # 2c：lark builder 入口也接选项解码（三入口全覆盖）
                value = getattr(action, "value", {}) or {}
                if _is_our_value(value):
                    try:
                        result = _handle_card_click(adapter, ev, value) if adapter is not None else None
                        if result is None:
                            result = adapter._card_response() if adapter is not None else _ack()
                        return result
                    except Exception:
                        logger.warning("[FeishuMenuBridge] lark hook error", exc_info=True)
                        return _ack()  # 是我方卡片：不落回官方路径
            except Exception:
                logger.warning("[FeishuMenuBridge] lark hook error", exc_info=True)
            return f(data) if callable(f) else None

        _wrapped.__name__ = "hermes_menu_bridge_card_handler"
        _wrapped._hermes_adapter = _bound  # 供 _adapter_from_handler 取回线上适配器
        try:
            return orig(self, _wrapped)
        except Exception as e:
            # 旧版插件实例留在类上的坏补丁会抛 NameError → 自己写映射；必须 return self，否则 builder 链断掉
            logger.warning("[FeishuMenuBridge] register fallback used: %s: %s", type(e).__name__, e)
            try:
                from lark_oapi.event.callback.processor import P2CardActionTriggerProcessor
                self._callback_processor_map["p2.card.action.trigger"] = P2CardActionTriggerProcessor(_wrapped)
            except Exception:
                logger.warning("[FeishuMenuBridge] register fallback 彻底失败", exc_info=True)
            return self

    _patched_register.__name__ = "register_p2_card_action_trigger"
    _patched_register._hermes_orig = orig   # 登记链尾：_orig_of 才找得到 SDK 原实现
    EventDispatcherHandlerBuilder.register_p2_card_action_trigger = _patched_register

    # build() 出来的处理器打上版本戳，供 _ensure_card_routing 判断是否需要重建
    orig_build = _orig_of(EventDispatcherHandlerBuilder.build)

    def _patched_build(self):
        handler = orig_build(self)
        try:
            setattr(handler, _MARKER_VER, _Guard(_CODE_V))
        except Exception:
            pass
        return handler

    _patched_build.__name__ = "build"
    _patched_build._hermes_orig = orig_build   # 登记链尾（同 #3）
    EventDispatcherHandlerBuilder.build = _patched_build

    setattr(EventDispatcherHandlerBuilder, _MARKER_LARK, _Guard(_CODE_V))
    logger.info("[FeishuMenuBridge] lark builder hook installed")
    return True


_CONFIRM_BULLET_RE = re.compile(r"^\s*[•·‣◦▪*\-–—]\s")


#: 执行审批 choice → 官方动作键名（与 feishu adapter 的 _EA_CARD_ACTIONS 逐字一致）
_EA_ACTION_KEYS = {"once": "approve_once", "session": "approve_session",
                   "always": "approve_always", "deny": "deny"}


def _approval_tier_note(actions: List[Any]) -> str:
    """按官方实际给出的档位生成说明，并引用**真实按钮 label**（避免指代卡上不存在的按钮）。"""
    present: Dict[str, str] = {}
    for item in list(actions or []):
        try:
            label, choice = str(item[0]), str(item[1])
        except Exception:
            continue
        present[choice] = label
    tips: List[str] = []
    if "session" in present:
        tips.append("「%s」= 网关重启前不再询问同类命令" % present["session"])
    if "always" in present:
        tips.append("「%s」= 写入 command_allowlist 白名单" % present["always"])
    if "once" in present:
        tips.append("「%s」= 只放行这一次" % present["once"])
    return "；".join(tips) + "。" if tips else ""


def build_exec_approval_card(prompt_text: str, actions: List[Any], approval_id: Any) -> Dict[str, Any]:
    """执行审批卡（v2 美化版）：**一次 / 本会话 / 永久 / 拒绝**（按官方给的档位自适应）。

    2026-10-04 用户要求「发一个权限版本看看」；v2 依据移动端渲染反馈重排：
    ① 去掉无信息量的指标格 ② 顶部红色警示横幅（一键扫读）③ 详情区收紧。
    动作键名与官方逐字一致（``approve_once``/``approve_session``/``approve_always``/``deny``
    + ``approval_id``），点击仍走 ``resolve_gateway_approval``；官方给几档就渲染几档。
    """
    body = _clean_md(prompt_text)[:900].strip() or "—"
    el: List[Dict[str, Any]] = [
        {"tag": "markdown", "content": "<font color='red'>⚠️ 危险操作待确认 —— 确认前不会执行</font>",
         "text_size": "notation"},
        _panel_element("📄 命令与拦截原因", body, expanded=True),
    ]
    _tier_note = _approval_tier_note(actions)
    if _tier_note:
        el.append(_note(_tier_note))
    el.append({"tag": "hr"})
    btns: List[Dict[str, Any]] = []
    for label, choice, style in list(actions or []):
        kind = "primary_filled" if str(style or "") == "primary" else "default"
        key = _EA_ACTION_KEYS.get(str(choice), str(choice))
        btns.append(_btn(str(label), {"hermes_action": key, "approval_id": approval_id}, kind))
    if not btns:      # 官方没给动作：退回一句说明，绝不发空按钮卡
        btns = [_btn("❌ 拒绝", {"hermes_action": "deny", "approval_id": approval_id}, "default")]
    for i in range(0, len(btns), 2):
        el += _rows(btns[i:i + 2], per_row=2)
    return _card("🔐 命令待批准", "indigo", el,
                 subtitle="由安全策略拦下")


def build_confirm_card(title: str, message: str, confirm_id: str) -> Dict[str, Any]:
    """斜杠命令确认卡（插件视觉体系重做版）。

    2026-10-04 用户要求美化：官方那版是「橙色卡 + 一大段给纯文本平台写的说明 + 三个朴素按钮」。
    重做后：动作/权限两格 + 说明折叠 + 两排按钮。
    **动作键名 (``hermes_action``/``confirm_id``) 与官方逐字一致**，点击仍走
    ``tools.slash_confirm.resolve`` —— 解析链路零改动；发送或构建失败时整体回退官方原样。
    """
    el: List[Dict[str, Any]] = [
        _metric_row(_usage_cell("⚡ 动作", (title or "—")[:16], "待执行命令", accent=True, tone=_DOM_ENTRY),
                    _usage_cell("🔐 权限", "本次询问", "待你确认", tone=_DOM_ENTRY)),
        _panel_element("📄 它会做什么", (_lean_confirm_text(message) or "—")[:900], expanded=True),
        _note("「🔒 永久批准」= 写入配置文件：今后 /new、/reset 这类命令在所有会话都不再询问；「❌ 取消」什么都不做。"),
        {"tag": "hr"},
    ]
    el += _rows([
        _btn("✅ 仅批准一次", {"hermes_action": "slash_once", "confirm_id": confirm_id}, "primary_filled"),
    ], per_row=1)
    el += _rows([
        _btn("🔒 永久批准", {"hermes_action": "slash_always", "confirm_id": confirm_id}),
        _btn("❌ 取消", {"hermes_action": "slash_cancel", "confirm_id": confirm_id}),
    ], per_row=2)
    return _card("⚠️ 需要确认 · " + (title or ""), "indigo", el,
                 subtitle="选一种批准方式 · 确认前命令不会执行")


def _fallback_confirm_card(title: str, message: str, confirm_id: str) -> Dict[str, Any]:
    """确认卡构建失败时的 2.0 兜底卡：结构必须与已处理卡(2.0)同构，避免 1.0→2.0 的 200830。"""
    return _card("⚠️ 需要确认 · " + (title or ""), "indigo",
                 [_md(_lean_confirm_text(message) or "—"), {"tag": "hr"}]
                 + _rows([_btn("✅ 仅批准一次",
                               {"hermes_action": "slash_once", "confirm_id": confirm_id}, "primary_filled")], per_row=1)
                 + _rows([_btn("🔒 永久批准", {"hermes_action": "slash_always", "confirm_id": confirm_id}),
                          _btn("❌ 取消", {"hermes_action": "slash_cancel", "confirm_id": confirm_id})], per_row=2))


def _fallback_exec_card(prompt: Any, approval_id: Any) -> Dict[str, Any]:
    """审批卡构建失败时的 2.0 兜底卡（动作键名与官方逐字一致）。"""
    return _card("🔐 命令待批准", "indigo",
                 [_md((getattr(prompt, "text", "") or "—")[:900]), {"tag": "hr"},
                  _btn("❌ 拒绝", {"hermes_action": "deny", "approval_id": approval_id}, "default")])


def _lean_confirm_text(text: str, action_count: int = 3) -> str:
    """把斜杠确认卡的卡面精简成「标题 + 说明 + 按钮」。

    官方给斜杠确认（/new、/reload-mcp、切换昂贵模型）的 message 是**给纯文本平台写的**：
    里面既把三个选项列了一遍，又写着「回复 /approve、/always 或 /cancel」。飞书把它渲染成
    带按钮的卡片后，卡面就成了「说明 + 与按钮重复的选项清单 + 一行让人回斜杠的提示」。
    这里在**渲染前**去掉后两段：只动卡面，网关的纯文本兜底路径拿到的仍是原文。
    """
    if not text:
        return text
    lines = text.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    # 1) 结尾的斜体文本兜底提示（各语言都写成 _…_）
    if lines and re.fullmatch(r"_.*_", lines[-1].strip()):
        lines.pop()
        while lines and not lines[-1].strip():
            lines.pop()
    # 2) 与按钮一一对应的选项清单（尾部连续 bullet 行 + 其引导行）
    i = len(lines) - 1
    bullets = 0
    while i >= 0 and _CONFIRM_BULLET_RE.match(lines[i]):
        bullets += 1
        i -= 1
    if bullets >= 2 and bullets == action_count:
        if i >= 0 and lines[i].strip().endswith((":", "：")):
            i -= 1
        lines = lines[:i + 1]
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


def _decode_option_value(action: Any) -> None:
    """⑩ select_static/overflow 归一化：飞书把所选值放在 ``action.option``（JSON 字符串，action.value=None）。

    命中插件动作（hermes_menu_*）时把解码结果写回 ``action.value`` —— 下游两个回调入口
    都按普通按钮值处理，无需感知控件类型。任何异常只记日志，绝不影响官方路径。
    """
    try:
        if action is None:
            return
        if isinstance(action, dict):
            # 2c：原始帧路径（dispatcher）拿到的是 dict 形态的 action —— 同样归一化。
            _dv = action.get("value")
            if isinstance(_dv, dict) and _dv:
                return
            _dopt = action.get("option")
            if isinstance(_dopt, str) and _dopt.strip().startswith("{"):
                _ddec = json.loads(_dopt)
                if isinstance(_ddec, dict) and _is_our_value(_ddec):
                    action["value"] = _ddec
            return
        _val = getattr(action, "value", None)
        if isinstance(_val, dict) and _val:
            return
        _opt = getattr(action, "option", None)
        if isinstance(_opt, str) and _opt.strip().startswith("{"):
            _decoded = json.loads(_opt)
            if isinstance(_decoded, dict) and _is_our_value(_decoded):
                action.value = _decoded
    except Exception:
        logger.warning("[FeishuMenuBridge] 选项回调解码失败", exc_info=True)


def _patch_send_final() -> bool:
    """抑制「菜单点击注入命令」的聊天回执（2026-10-04 审计性能项 O2）。

    链路：卡片点击 → _inject（metadata 带 feishu_menu_bridge 标记）→ 网关执行命令 →
    回执文本经 BasePlatformAdapter.send_final_ledgered 落聊天。带标记的事件跳过发送：
    toast + 卡面已即时反馈，不需要「命令回显」；ledger 不留行（按成功处理，不是失败）。
    只认标记 —— 用户手打的消息绝不受影响；任何异常立即回退官方原实现。
    """
    try:
        from gateway.platforms.base import BasePlatformAdapter, SendResult
    except Exception:
        return False
    cur = getattr(BasePlatformAdapter, "send_final_ledgered", None)
    if cur is None:
        return False
    if _mk(cur, _MARKER_SENDFINAL) >= _CODE_V:
        return True   # 已装（幂等，版本门控）
    # 2026-10-07 审计修复（#4）：幂等门看的是**当前**属性（标记在包装上），
    # 但取原始实现必须剥链，否则升版后旧回执抑制逻辑先执行、新版被冻结（与 #3 同因）。
    orig = _orig_of(cur)

    async def _patched_sfl(self, event, session_key, text_content, metadata,
                           *, reply_to=None, is_ephemeral_response=False):
        try:
            if (getattr(event, "metadata", None) or {}).get("feishu_menu_bridge"):
                logger.info("[FeishuMenuBridge] 抑制菜单点击命令回执（%d 字）", len(text_content or ""))
                return SendResult(success=True), self
        except Exception:
            logger.debug("[FeishuMenuBridge] 回执抑制判断异常，按原样发送", exc_info=True)
        return await orig(self, event, session_key, text_content, metadata,
                          reply_to=reply_to, is_ephemeral_response=is_ephemeral_response)

    _patched_sfl._fmb_reply_silenced = True                 # 遗留兼容，保留
    _patched_sfl._fmb_sendfinal_v = _Guard(_CODE_V)         # 新：数值版本位
    _patched_sfl._hermes_orig = orig
    BasePlatformAdapter.send_final_ledgered = _patched_sfl
    logger.info("[FeishuMenuBridge] 命令回执抑制已装到 BasePlatformAdapter（仅拦我们注入的事件）")
    return True


def _patch_tool_progress_gate() -> bool:
    """PT 静音窗：签到进行期间把飞书工具进度整体关掉（display_config 层，仅 feishu）。

    run_turn.py 每轮在函数内 ``from gateway.display_config import resolve_tool_progress``，
    因此包住这个模块级函数即可即时生效、且无需重启；非签到时段行为与原来完全一致。
    """
    try:
        from gateway import display_config as _dc
        if _mk(_dc.resolve_tool_progress, _MARKER_PTGATE) >= _CODE_V:
            return True
        _orig_rp = _dc.resolve_tool_progress

        def _gated(user_config, platform_key, env_mode=None):
            try:
                if platform_key == "feishu" and _pt_quiet_active():
                    return ("off", True)
            except Exception:
                pass
            return _orig_rp(user_config, platform_key, env_mode)

        _gated._fmb_pt_gate = True                          # 遗留兼容，保留
        _gated._fmb_ptgate_v = _Guard(_CODE_V)              # 新：数值版本位
        _gated._hermes_orig = _orig_rp
        _dc.resolve_tool_progress = _gated
        logger.info("[FeishuMenuBridge] PT 静音窗补丁已装（签到期间工具进度静音）")
        return True
    except Exception:
        logger.warning("[FeishuMenuBridge] PT 静音窗补丁安装失败", exc_info=True)
        return False


# ── 已处理卡（点击确认/审批之后原地替换的那张）─────────────────────────────
# 2026-10-05 用户反馈「确认会话取消后这个弹出太丑了，之前不是改成和其他卡片同样风格了吗」：
# 原来那张是整卡红标题 + 卡面直接印一串 ou_ 开头的 open_id，跟面板/系统那套（indigo 标题 +
# 2 格指标 + 灰阶注脚）明显不是一家人。现在统一到同一套构件，红色只做「未执行」标签的文字级强调。

#: confirm_id → 确认卡标题（"/new"、"/reload-mcp" 这类）。发卡时记下，点击后用来在已处理卡里
#: 说明到底确认的是哪条命令；上限 200 条，FIFO 淘汰（confirm_id 是自增序号，不会重号）。
_CONFIRM_TITLES: Dict[str, str] = {}
_CONFIRM_TITLES_MAX = 200
#: 点击处理期间临时置位的标题 —— _build_resolved_* 只收到 (choice, user_name)，拿不到 confirm_id，
#: 只能在同步调用链里借位（_handle_slash_confirm_card_action → 同一线程内构建替换卡）。
_CUR_CONFIRM_TITLE = ""

#: user_name 取不到真名时官方会回退成 open_id/union_id —— 这种就别往卡面上印。
_ID_LIKE_RE = re.compile(r"^(ou_|on_|oc_|u_)[0-9a-zA-Z]{6,}$")

#: choice → (图标, 标题, 结果词, 结果副标, 注脚)
_RESOLVED_TEXT: Dict[str, Dict[str, Tuple[str, str, str, str, str]]] = {
    "slash": {
        "once":   ("✅", "已批准（仅一次）", "已执行", "已放行", "命令已放行执行。"),
        "always": ("✅", "已永久批准", "已执行", "已放行", "命令已放行，今后不再询问。"),
        "cancel": ("❌", "已取消", "未执行", "会话保持不变", "命令没有执行，当前对话保持原样。"),
    },
    "approval": {
        "once":    ("✅", "已批准（仅一次）", "已执行", "已放行", "该命令已放行。"),
        "session": ("✅", "已批准（本会话）", "已执行", "已放行", "该命令在本会话内放行。"),
        "always":  ("✅", "已永久批准", "已执行", "已放行", "该命令已放行，并加入永久允许列表。"),
        "deny":    ("❌", "已拒绝", "未执行", "命令未运行", "该命令没有执行。"),
    },
}


def _remember_confirm_title(confirm_id: Any, title: Any) -> None:
    cid = str(confirm_id or "")
    if not cid:
        return
    _CONFIRM_TITLES[cid] = str(title or "")
    while len(_CONFIRM_TITLES) > _CONFIRM_TITLES_MAX:
        _CONFIRM_TITLES.pop(next(iter(_CONFIRM_TITLES)), None)


def _resolved_state_card(*, kind: str, choice: str, user_name: Any) -> Dict[str, Any]:
    """已处理卡：与面板/系统同一套构件（indigo 标题 + 2 格指标 + 灰阶注脚 + 状态标签）。"""
    icon, label, state, sub, note = _RESOLVED_TEXT.get(kind, {}).get(
        str(choice), ("✅", "已处理", "已处理", "", "已处理。"))
    title = str(_CUR_CONFIRM_TITLE or "").strip() if kind == "slash" else ""
    name = str(user_name or "")
    who = "" if (not name or _ID_LIKE_RE.match(name)) else (" · " + name)
    return _card(
        f"{icon} {label}", _DOM_ENTRY,
        [_metric_row(
            _usage_cell("⚡ 动作" if kind == "slash" else "🔐 授权",
                        title or ("斜杠命令" if kind == "slash" else label),
                        "斜杠命令" if kind == "slash" else "命令审批"),
            _usage_cell("📄 结果", state, sub)),
         _note(note + who)],
        subtitle=("确认已处理 · %s" if kind == "slash" else "授权已处理 · %s") % _now_hm(),
        tags=[("red" if state == "未执行" else "neutral", state)],
    )


def _patch_resolved_cards(cls: Any) -> bool:
    """把官方两张「已处理」卡换成 2.0 同构版（2026-10-04：修复 200830）。

    根因：本插件把「斜杠确认卡 / 执行审批卡」重做成了 JSON 2.0 结构；点击后官方用
    `_build_resolved_*` 返回 1.0 结构的替换卡 —— 飞书客户端拒绝「2.0→1.0」并弹
    「出错啦 code: 200830」。官方 update-prompt 卡不在此列（其前置卡是本插件未动的
    官方 1.0 卡，保持原配不动）。
    """
    try:
        changed = False
        # ① 斜杠确认（classmethod）
        cur = cls.__dict__.get("_build_resolved_slash_confirm_card") or getattr(
            cls, "_build_resolved_slash_confirm_card", None)
        # classmethod/staticmethod 描述符的真正函数在 __func__ 上，标记也挂在它身上 —— 否则幂等判断会漏。
        if cur is not None and _mk(getattr(cur, "__func__", cur), _MARKER_RES2) < _CODE_V:
            _orig = getattr(cls, "_build_resolved_slash_confirm_card")

            def _resolved_slash(_cls, *, choice, user_name, _impl=_orig):
                try:
                    return _resolved_state_card(kind="slash", choice=choice, user_name=user_name)
                except Exception:
                    return _impl(choice=choice, user_name=user_name)

            _resolved_slash._fmb_res2 = True                # 遗留兼容，保留
            _resolved_slash._fmb_res2_v = _Guard(_CODE_V)   # 新：数值版本位
            cls._build_resolved_slash_confirm_card = classmethod(_resolved_slash)
            changed = True
        # ② 执行审批（staticmethod）
        cur2 = cls.__dict__.get("_build_resolved_approval_card") or getattr(
            cls, "_build_resolved_approval_card", None)
        if cur2 is not None and _mk(getattr(cur2, "__func__", cur2), _MARKER_RES2) < _CODE_V:
            _orig2 = getattr(cls, "_build_resolved_approval_card")

            def _resolved_approval(*, choice, user_name, _impl=_orig2):
                try:
                    return _resolved_state_card(kind="approval", choice=choice, user_name=user_name)
                except Exception:
                    return _impl(choice=choice, user_name=user_name)

            _resolved_approval._fmb_res2 = True             # 遗留兼容，保留
            _resolved_approval._fmb_res2_v = _Guard(_CODE_V)  # 新：数值版本位
            cls._build_resolved_approval_card = staticmethod(_resolved_approval)
            changed = True
        # ③ 点击入口借位标题：_build_resolved_* 只收 (choice, user_name)，命令名得从这里递进去。
        #    同步调用链（handler 里当场构建替换卡），所以一个模块级变量就够，用完即清。
        curh = cls.__dict__.get("_handle_slash_confirm_card_action") or getattr(
            cls, "_handle_slash_confirm_card_action", None)
        if curh is not None and _mk(getattr(curh, "__func__", curh), _MARKER_SLASHH) < _CODE_V:
            _orig_h = _orig_of(getattr(cls, "_handle_slash_confirm_card_action"))

            def _patched_slash_handler(self, *, event, action_value, loop, _impl=_orig_h):
                global _CUR_CONFIRM_TITLE
                try:
                    cid = str((action_value or {}).get("confirm_id") or "")
                    state = (getattr(self, "_slash_confirm_state", None) or {}).get(cid) or {}
                    _CUR_CONFIRM_TITLE = str(state.get("title") or "")
                except Exception:
                    _CUR_CONFIRM_TITLE = ""
                try:
                    return _impl(self, event=event, action_value=action_value, loop=loop)
                finally:
                    _CUR_CONFIRM_TITLE = ""

            _patched_slash_handler.__name__ = "_handle_slash_confirm_card_action"
            _patched_slash_handler._hermes_orig = _orig_h
            setattr(_patched_slash_handler, _MARKER_SLASHH, _Guard(_CODE_V))
            cls._handle_slash_confirm_card_action = _patched_slash_handler
            changed = True
        if changed:
            logger.info("[FeishuMenuBridge] 已处理卡补丁已装（2.0 同构修 200830 + 并入插件视觉体系）")
        return True
    except Exception:
        logger.warning("[FeishuMenuBridge] 已处理卡补丁失败", exc_info=True)
        return False


def _patch_adapter_class(cls: Any) -> bool:
    """对指定适配器类装卡片回调补丁（幂等）。"""
    if _mk(cls, _MARKER) >= _CODE_V:
        return True   # 版本守卫前置：本类已装到位，不再重复跑三个补丁
    try:
        _patch_send_final()   # 回执抑制（BasePlatformAdapter 层；自带幂等守卫）
    except Exception:
        logger.warning("[FeishuMenuBridge] 回执抑制安装失败", exc_info=True)
    try:
        _patch_tool_progress_gate()   # PT 静音窗（签到期间工具进度静音；幂等）
    except Exception:
        logger.warning("[FeishuMenuBridge] PT 静音窗安装失败", exc_info=True)
    try:
        _patch_resolved_cards(cls)   # 已处理卡 2.0 同构（修 200830）
    except Exception:
        logger.debug("[FeishuMenuBridge] 已处理卡补丁安装失败", exc_info=True)
    if not hasattr(cls, "_on_card_action_trigger"):
        return False
    orig = _orig_of(cls._on_card_action_trigger)

    def _patched_trigger(self, data):
        _decode_option_value(getattr(getattr(data, "event", None), "action", None))
        ev = getattr(data, "event", None)
        action = getattr(ev, "action", None)
        value = getattr(action, "value", {}) or {}
        if _is_our_value(value):
            try:
                return _handle_card_click(self, ev, value)
            except Exception:
                logger.warning("[FeishuMenuBridge] trigger wrapper error", exc_info=True)
                return _ack()  # 是我方卡片：绝不落回官方路径（官方拿卡片 token 当 message_id）
        return orig(self, data)

    _patched_trigger.__name__ = "_on_card_action_trigger"
    _patched_trigger._hermes_orig = orig
    cls._on_card_action_trigger = _patched_trigger

    # 兜底层：已连接的分发器注册的是**旧绑定方法**，类补丁改不到它；而 _handle_card_action_event
    # 是运行期属性查找（self._handle_card_action_event(data)）→ 这里补丁对当前连接立即生效。
    # 代价：拿不到同步响应（不能原地更新卡片），所以只做副作用：发卡/注入命令/撤回。
    try:
        orig_evt = _orig_of(getattr(cls, "_handle_card_action_event"))
    except AttributeError:
        orig_evt = None

    async def _patched_event(self, data):
        _decode_option_value(getattr(getattr(data, "event", None), "action", None))
        ev = getattr(data, "event", None)
        action = getattr(ev, "action", None)
        value = getattr(action, "value", {}) or {}
        if _is_our_value(value):
            try:
                _resp = _handle_card_click(self, ev, value)
                return _resp if _resp is not None else _ack()
            except Exception:
                logger.warning("[FeishuMenuBridge] card action intercept error", exc_info=True)
            return _ack()  # 是我方卡片：绝不落回官方路径
        if orig_evt is None:
            return None
        return await orig_evt(self, data)

    _patched_event.__name__ = "_handle_card_action_event"
    cls._handle_card_action_event = _patched_event

    # 斜杠确认卡（/new、/reload-mcp、切换昂贵模型）：卡面整卡重做为插件视觉体系。
    # 动作键名与原版逐字一致（hermes_action/confirm_id），点击解析走官方 tools.slash_confirm.resolve；
    # 构建或发送异常时回退官方原样 —— 功能永远兜得住。
    orig_confirm = getattr(cls, "send_slash_confirm", None)
    if orig_confirm is not None:
        orig_confirm = _orig_of(orig_confirm)

        async def _patched_confirm(self, *args, **kwargs):
            def _note_title(res):
                """发卡成功后把标题记进状态：点击时用来在已处理卡里说明确认的是哪条命令。"""
                try:
                    if getattr(res, "success", False):
                        cid = kw.get("confirm_id")
                        _remember_confirm_title(cid, kw.get("title"))
                        st = getattr(self, "_slash_confirm_state", None)
                        if cid is not None and isinstance(st, dict) and isinstance(st.get(cid), dict):
                            st[cid]["title"] = str(kw.get("title") or "")
                except NameError:      # kw 没建起来（上面就抛了）→ 什么都不记
                    pass
                except Exception:
                    logger.debug("[FeishuMenuBridge] 记录确认卡标题失败", exc_info=True)
                return res

            try:
                names = ("chat_id", "title", "message", "session_key", "confirm_id", "metadata")
                kw = dict(zip(names, args))
                kw.update({k: v for k, v in kwargs.items() if k in names})
                card = build_confirm_card(str(kw.get("title") or ""), str(kw.get("message") or ""),
                                          str(kw.get("confirm_id") or ""))
                return _note_title(await self._send_interactive_card(
                    kw.get("chat_id"), card, kw.get("metadata"), "send_slash_confirm failed",
                    state_map=self._slash_confirm_state, state_id=kw.get("confirm_id"),
                    session_key=kw.get("session_key")))
            except Exception:
                logger.warning("[FeishuMenuBridge] 确认卡重做失败，改用 2.0 兜底卡"
                               "（保证与已处理卡同构，避免 1.0→2.0 的 200830）", exc_info=True)
                return _note_title(await self._send_interactive_card(
                    kw.get("chat_id"),
                    _fallback_confirm_card(str(kw.get("title") or ""), str(kw.get("message") or ""),
                                           str(kw.get("confirm_id") or "")),
                    kw.get("metadata"), "send_slash_confirm fallback failed",
                    state_map=self._slash_confirm_state, state_id=kw.get("confirm_id"),
                    session_key=kw.get("session_key")))

        _patched_confirm.__name__ = "send_slash_confirm"
        _patched_confirm._hermes_orig = orig_confirm
        cls.send_slash_confirm = _patched_confirm

    # 执行审批卡（四档权限）：同样整卡重做；动作键名/approval_id 与官方逐字一致，
    # 点击仍走 resolve_gateway_approval；任何异常回退官方原样。
    orig_exec = getattr(cls, "_send_exec_approval_prompt", None)
    if orig_exec is not None:
        orig_exec = _orig_of(orig_exec)

        def _fill_approval_id(card: Dict[str, Any], aid: Any) -> Dict[str, Any]:
            """先构建后回填：把卡 JSON 里占位的 None 换成真实 approval_id（按钮 payload）。"""
            s = json.dumps(card, ensure_ascii=False)
            s2 = s.replace('"approval_id": null', '"approval_id": %s' % json.dumps(aid))
            if s2 == s:
                logger.warning("[FeishuMenuBridge] 审批卡回填 id 未命中（字段名变化？）")
            return json.loads(s2)

        async def _patched_exec(self, prompt):
            # 2026-10-05 修（X6-D27 re-base：X5 改为 2.0 兜底卡后适配）：构建阶段不取号，
            # 确定要发卡时才 next() 并把占位 id 回填进卡；发送失败先清空洞再走兜底卡。
            try:
                card = build_exec_approval_card(getattr(prompt, "text", "") or "",
                                                getattr(prompt, "actions", None), None)
            except Exception:
                logger.warning("[FeishuMenuBridge] 执行审批卡构建失败，改用 2.0 兜底卡", exc_info=True)
                approval_id = next(self._approval_counter)
                return await self._send_interactive_card(
                    prompt.chat_id, _fallback_exec_card(prompt, approval_id),
                    getattr(prompt, "metadata", None), "send_exec_approval fallback failed",
                    state_map=self._approval_state, state_id=approval_id,
                    session_key=getattr(prompt, "session_key", ""))
            approval_id = next(self._approval_counter)
            try:
                return await self._send_interactive_card(
                    prompt.chat_id, _fill_approval_id(card, approval_id),
                    getattr(prompt, "metadata", None),
                    "send_exec_approval failed",
                    state_map=self._approval_state, state_id=approval_id,
                    session_key=getattr(prompt, "session_key", ""))
            except Exception:
                try:
                    self._approval_state.pop(approval_id, None)   # 防「已注册未交付」的空洞
                except Exception:
                    pass
                logger.warning("[FeishuMenuBridge] 执行审批卡发送失败，改用 2.0 兜底卡", exc_info=True)
                return await self._send_interactive_card(
                    prompt.chat_id, _fallback_exec_card(prompt, approval_id),
                    getattr(prompt, "metadata", None), "send_exec_approval fallback failed",
                    state_map=self._approval_state, state_id=approval_id,
                    session_key=getattr(prompt, "session_key", ""))


        _patched_exec.__name__ = "_send_exec_approval_prompt"
        _patched_exec._hermes_orig = orig_exec
        cls._send_exec_approval_prompt = _patched_exec

    setattr(cls, _MARKER, _Guard(_CODE_V))
    logger.info("[FeishuMenuBridge] adapter hook installed on %s", cls)
    return True


def _install_adapter_hook() -> bool:
    for name, m in list(sys.modules.items()):
        if isinstance(name, str) and name.endswith("feishu.adapter") and hasattr(m, "FeishuAdapter"):
            return _patch_adapter_class(m.FeishuAdapter)
    return False


def _adapter_from_handler(handler: Any) -> Any:
    """从分发器上取回它绑定的适配器（注册卡片回调时存的是适配器的绑定方法）。"""
    try:
        pmap = getattr(handler, "_callback_processor_map", None) or {}
        proc = pmap.get("p2.card.action.trigger")
        f = getattr(proc, "f", None)
        ad = getattr(f, "_hermes_adapter", None) or getattr(f, "__self__", None)
        if ad is not None:
            return ad
        # 处理器绑定拿不到（包装函数/映射键不同）→ 用钩子确认过的线上适配器（必须还活着）
        if _LIVE_ADAPTER is not None and _adapter_usable(_LIVE_ADAPTER):
            return _LIVE_ADAPTER
        # 兜底：从包装函数的闭包里找适配器（旧版包装器没挂引用）
        for cell in getattr(f, "__closure__", None) or ():
            try:
                v = cell.cell_contents
            except Exception:
                continue
            if hasattr(v, "_build_event_handler") and hasattr(v, "_event_handler"):
                return v
        return None
    except Exception:
        return None


def _intercept_card_action(handler: Any, payload: Any) -> Any:
    """解析原始 payload；是我方卡片按钮则执行副作用并**返回飞书同步响应对象**（由调用方透传短路）；
    不是我方按钮则返回 None（调用方落回 orig）。返回 None = 未命中；返回对象 = 已处理。"""
    if isinstance(payload, (bytes, bytearray)):
        raw = bytes(payload).decode("utf-8", "ignore")
    else:
        raw = str(payload)
    if "hermes_menu_" not in raw:  # 快速过滤：绝大多数事件不是我们的按钮
        return None
    data = json.loads(raw)
    if (data.get("header") or {}).get("event_type") != "card.action.trigger":
        return None
    ev = data.get("event") or {}
    _decode_option_value(ev.get("action") or {})   # 2c：原始帧路径也接选项解码（此前只在 SDK 入口有）
    value = (ev.get("action") or {}).get("value") or {}
    if not _is_our_value(value):
        return None
    adapter = _adapter_from_handler(handler)
    if adapter is None:
        live = [a for a in _live_adapters() if _adapter_usable(a)]
        adapter = live[0] if live else None
    if adapter is None:
        _count_drop("no_adapter", "[FeishuMenuBridge] 卡片点击被丢弃：拿不到可用适配器")
        # 2026-10-07 审计修复（#8）：这是我方卡片的点击，绝不能返回 None 落回官方路径 ——
        # 官方路径会把卡片 token 当 message_id 处理（报错/发错）。给用户一条明确提示。
        return _not_delivered()
    ctx = ev.get("context") or {}
    ope = ev.get("operator") or {}
    logger.debug("[FeishuMenuBridge] card click intercepted at dispatcher: %s", value)
    _resp = _handle_card_click(adapter, _ns(
        context=_ns(open_chat_id=ctx.get("open_chat_id", "") or "",
                    open_message_id=ctx.get("open_message_id", "") or "",
                    chat_id=ctx.get("open_chat_id", "") or ""),
        operator=_ns(open_id=ope.get("open_id", "") or "")), value)
    return _resp if _resp is not None else _ack()


def _orig_of(fn: Any) -> Any:
    """沿我们自己打的包装链找到 SDK 原始实现（防止补丁层层嵌套直到递归爆栈）。"""
    seen = 0
    while getattr(fn, "_hermes_orig", None) is not None and seen < 64:
        fn = fn._hermes_orig
        seen += 1
    return fn


def _patch_dispatcher_class(cls: Any) -> bool:
    """在指定分发器类上装 `_do_without_validation` 拦截（幂等）。"""
    if _mk(cls, _MARKER_DO) >= _CODE_V:
        return True
    if not hasattr(cls, "_do_without_validation"):
        return False
    orig = _orig_of(cls._do_without_validation)

    def _patched_do(self, payload):
        # 2026-10-04 洁癖档批3（O5）：先按事件类型快速排除——非卡片回调帧不做全量序列化，
        # 大 payload 时省掉每次几毫秒的 json.dumps。
        try:
            _h = getattr(payload, "header", None)
            if _h is None and isinstance(payload, dict):
                _h = payload.get("header")
            _et = str(getattr(_h, "event_type", "")
                      or (_h.get("event_type") if isinstance(_h, dict) else "") or "")
        except Exception:
            _et = ""
        if _et and _et != "card.action.trigger":
            return orig(self, payload)
        try:
            mine = "hermes_menu_" in json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            mine = False
        try:
            _resp = _intercept_card_action(self, payload)
            if _resp is not None:
                return _resp
        except Exception:
            logger.warning("[FeishuMenuBridge] dispatcher intercept error", exc_info=True)
            if mine:
                # 我方卡片：绝不落回官方路径（官方会把卡片 token 当 message_id 处理）——只回执。
                return _ack()
        return orig(self, payload)

    _patched_do.__name__ = "_do_without_validation"
    _patched_do._hermes_orig = orig  # 供下次安装收敛到原始实现
    cls._do_without_validation = _patched_do
    setattr(cls, _MARKER_DO, _Guard(_CODE_V))
    logger.info("[FeishuMenuBridge] dispatcher hook installed on %s (v%s)", cls, _CODE_V)
    return True


_MARKER_WS = "_hermes_menu_bridge_ws_frame_v"


def _patch_ws_class(cls: Any) -> bool:
    """在 SDK 的 ws 数据帧入口加观测：确认飞书到底有没有把卡片回调帧送过来。"""
    if _mk(cls, _MARKER_WS) >= _CODE_V:
        return True
    if not hasattr(cls, "_handle_data_frame"):
        return False
    orig = _orig_of(cls._handle_data_frame)

    async def _patched_frame(self, frame):
        try:
            hs = getattr(frame, "headers", None) or []
            mtype = ""
            for h in hs:
                if getattr(h, "key", "") == "type":
                    mtype = getattr(h, "value", "")
                    break
            pl = getattr(frame, "payload", b"") or b""
            raw = bytes(pl)
            etype = ""
            value_txt = ""
            obj = None
            try:
                obj = json.loads(raw.decode("utf-8", "ignore"))
                etype = str((obj.get("header") or {}).get("event_type") or "")
                val = (((obj.get("event") or {}).get("action") or {}).get("value")) or {}
                if val:
                    value_txt = json.dumps(val, ensure_ascii=False)[:160]
            except Exception:
                pass
            if b"hermes_menu_" in raw:
                logger.debug("[FeishuMenuBridge] WS frame type=%s event_type=%s 我方按钮载荷 value=%s",
                             mtype, etype, value_txt)
            else:
                logger.debug("[FeishuMenuBridge] WS frame type=%s event_type=%s %d 字节", mtype, etype, len(raw))
            # 菜单项最上游改写：文本消息若命中菜单名，就地把 content 换成命令，
            # 让它以「命令」身份走快通道（命令不进批处理、不受每会话锁影响，忙时也通）。
            if etype == "im.message.receive_v1" and isinstance(obj, dict):
                try:
                    _msg = (obj.get("event") or {}).get("message") or {}
                    _content = _msg.get("content")
                    _c = json.loads(_content) if isinstance(_content, str) and _content else None
                    _t = _c.get("text") if isinstance(_c, dict) else None
                    if isinstance(_t, str):
                        _t2 = _t.strip()
                        if _t2 and not _t2.startswith("/"):
                            _key = _resolve_menu_key(_t2)
                            if _key in COMMANDS:
                                _c["text"] = COMMANDS[_key]
                                _msg["content"] = json.dumps(_c, ensure_ascii=False)
                                frame.payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                                logger.debug(
                                    "[FeishuMenuBridge] 帧层改写菜单项 %r → %r（走命令通道，忙时也通）",
                                    _t2, COMMANDS[_key],
                                )
                            # 注：_key in CARD_BUILDERS 的情况「不走这里」——开卡统一交给批处理钩子
                            # _patch_batch_class 负责（它会 return None 阻止原文继续派发）。
                            # 帧层再发一张就会变成「点一次菜单蹦出两张卡」（2026-10-04 实测确认），
                            # 所以帧层只做命令改写，这里不写分支（旧的空 elif 已删，避免误导）。
                except Exception:
                    logger.warning("[FeishuMenuBridge] 帧层改写失败，按原文放行", exc_info=True)
        except Exception:
            logger.warning("[FeishuMenuBridge] ws frame observe failed", exc_info=True)
        return await orig(self, frame)

    _patched_frame.__name__ = "_handle_data_frame"
    _patched_frame._hermes_orig = orig
    cls._handle_data_frame = _patched_frame
    setattr(cls, _MARKER_WS, _Guard(_CODE_V))
    logger.info("[FeishuMenuBridge] ws frame hook installed on %s", cls)
    return True


def _toast(text: str, kind: str = "success") -> Any:
    """点击回执只弹一条提示，不替换用户点的那张卡（替换会把整个面板卡毁掉）。"""
    try:
        from lark_oapi.event.callback.model.p2_card_action_trigger import (
            CallBackToast, P2CardActionTriggerResponse)
        r = P2CardActionTriggerResponse()
        t = CallBackToast()
        t.type = kind
        t.content = text
        r.toast = t
        return r
    except Exception:
        return _ack()


def _ack() -> Any:
    """卡片回调的同步回执。用官方响应对象，裸 dict 可能被判为「响应体格式错误」。"""
    try:
        from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
        return P2CardActionTriggerResponse()
    except Exception:
        return {}


def _install_dispatcher_hook() -> bool:
    """对 sys.modules 里的分发器类装拦截；失败原因写日志（导入在某些加载时机可能拿不到）。"""
    ok = False
    try:
        from lark_oapi.event.dispatcher_handler import EventDispatcherHandler as _EDH
        ok = _patch_dispatcher_class(_EDH)
    except Exception:
        logger.warning("[FeishuMenuBridge] dispatcher class import failed", exc_info=True)
    try:
        from lark_oapi.ws.client import Client as _WS
        ok = _patch_ws_class(_WS) and ok
    except Exception:
        logger.warning("[FeishuMenuBridge] ws client class import failed", exc_info=True)
    return ok


_WARNED_ONCE: set = set()


def _warn_once(key: Any, msg: str, *args: Any) -> None:
    """一次性告警（键=原因×类名，有限枚举）。

    _try_install 失败时是 0.5s/次的快循环 —— 任何新告警不设闸门会淹没日志。
    """
    if key in _WARNED_ONCE:
        logger.debug(msg, *args)
        return
    _WARNED_ONCE.add(key)
    logger.warning(msg, *args)


def _verify_live(cls, attr: str, wrapper: Any, marker: str) -> bool:
    """安装后回读断言：属性确实是刚挂的包装，且标记回读 >= _CODE_V。

    返回 True = 「验证过」（不再是旧的「语句执行过」）；失败只留一次性告警、不抛。
    """
    try:
        attached = cls.__dict__.get(attr) is wrapper or getattr(cls, attr, None) is wrapper
    except Exception:
        attached = False
    ok = bool(attached) and _mk(cls, marker) >= _CODE_V
    if not ok:
        _warn_once(("verify-" + marker, cls.__name__),
                   "[FeishuMenuBridge] install self-check FAILED: %s.%s attached=%s marker=%s",
                   cls.__name__, attr, attached, _mk(cls, marker))
    return ok


_MARKER_BUSY = "_hermes_menu_bridge_busy_v"


def _install_busy_hook() -> bool:
    """给「忙线」入口打补丁：会话忙时也要能认菜单名。

    飞书文本在忙时走 ``_hm_handle_running_session_message``（不进 pre_gateway_dispatch），
    所以钩子看不到 ⏹停止 / 📊面板。这里包装那个方法：命中菜单名 → 当命令执行 / 发卡片，
    并吞掉这条消息；其余情况原样放行。
    """
    done = False
    found = False
    for mod in list(sys.modules.values()):
        cls = getattr(mod, "GatewayRunner", None) if mod is not None else None
        if isinstance(cls, type) and "_hm_handle_running_session_message" in dir(cls):
            found = True
            done = _patch_busy_class(cls) or done
    if not found:
        _warn_once(("busy-noowner",),
                   "[FeishuMenuBridge] busy hook: 未找到 GatewayRunner（等类出现）")
    return done


def _patch_busy_class(cls) -> bool:
    if not isinstance(cls, type):
        return False
    if _mk(cls, _MARKER_BUSY) >= _CODE_V:
        # 2026-10-04 审计修复：已装返回 True（与 adapter/dispatcher/ws 三个兄弟一致）。
        # 返回 False 会让 _install_busy_hook 的 done 稳态恒假 → watcher 永不降频。
        return True
    orig = cls.__dict__.get("_hm_handle_running_session_message")
    if orig is None:
        for base in cls.__mro__:
            if "_hm_handle_running_session_message" in base.__dict__:
                orig = base.__dict__["_hm_handle_running_session_message"]
                break
    if orig is None:
        _warn_once(("busy-nomethod", cls.__name__),
                   "[FeishuMenuBridge] busy hook: %s 缺目标方法 _hm_handle_running_session_message，跳过",
                   cls.__name__)
        return False
    if getattr(orig, "_hermes_menu_bridge_busy", False):
        # 2026-10-07 审计修复（#2）：旧版包装在升版后换不掉 —— 原来直接 return False，
        # 于是热重载 / 升 _CODE_V 全都无效，必须重启网关。现在包装登记了 _hermes_orig，
        # 可以沿链剥回 SDK 原实现，用新逻辑重装一层。
        _stale = _orig_of(orig)
        if _stale is None or getattr(_stale, "_hermes_menu_bridge_busy", False):
            _warn_once(("busy-stale", cls.__name__),
                       "[FeishuMenuBridge] busy hook: %s 旧版包装无法剥链（标记=%s），保持现状",
                       cls.__name__, _mk(cls, _MARKER_BUSY))
            return False
        orig = _stale

    async def _busy_menu_wrapper(self, event, source, _quick_key):
        try:
            plat = getattr(getattr(source, "platform", None), "value", None)
            text = str(getattr(event, "text", "") or "").strip()
            if plat == "feishu" and text and not text.startswith("/"):
                key = _resolve_menu_key(text) or text
                chat_id = str(getattr(source, "chat_id", "") or "")
                if chat_id and (key in COMMANDS or key in CARD_BUILDERS):
                    adapter = _feishu_adapter(self, source)
                    if adapter is not None:
                        if key in COMMANDS:
                            logger.info("[FeishuMenuBridge] 忙线拦截 %r → %r（就地改写成命令）",
                                           text, COMMANDS[key])
                            try:
                                event.text = COMMANDS[key]
                            except Exception:
                                logger.debug("[FeishuMenuBridge] busy hook: 改写成命令失败，按原文放行",
                                             exc_info=True)
                            # D6：不在此处调 orig —— 统一由函数末尾调用一次，异常时不再二次调用
                        else:
                            # F01/#5（2026-10-07 审计修复）：与钩子、批处理两处统一闸门 ——
                            # 发卡并吞掉消息之前复用网关授权判断（fail-closed）；
                            # 未授权就放行原文，交回网关照常处理。
                            if not _sender_authorized(self, source):
                                logger.info("[FeishuMenuBridge] 未授权来源，忙线不发卡（放行原文）")
                                return await orig(self, event, source, _quick_key)
                            card = await asyncio.to_thread(build_card, key, chat_id)
                            if card is not None:
                                logger.info("[FeishuMenuBridge] 忙线拦截 %r → 直接发卡", text)
                                _res = await _send_card(adapter, chat_id, card)
                                if _send_ok(_res):
                                    return None
                                # D7：投递失败不再静默吞消息，放行原文
                                logger.warning("[FeishuMenuBridge] 忙线开卡 %r 未投递；按原文放行", key)
        except Exception:
            logger.warning("[FeishuMenuBridge] 忙线拦截失败，放行原逻辑", exc_info=True)
        return await orig(self, event, source, _quick_key)

    _busy_menu_wrapper._hermes_menu_bridge_busy = True
    _busy_menu_wrapper._hermes_orig = orig   # 2026-10-07（#2）：登记链尾，升版后可剥链重装
    cls._hm_handle_running_session_message = _busy_menu_wrapper
    try:
        setattr(cls, _MARKER_BUSY, _Guard(_CODE_V))
    except Exception:
        _warn_once(("busy-marker", cls.__name__),
                   "[FeishuMenuBridge] busy hook: 标记写入失败 %s（下轮重试，健康检查会标红）",
                   cls.__name__)
    if not _verify_live(cls, "_hm_handle_running_session_message", _busy_menu_wrapper, _MARKER_BUSY):
        return False      # 成功日志只在回读通过后打（True 的语义 = 验证过，而非执行过）
    logger.info("[FeishuMenuBridge] busy hook installed on %s (v%d)", cls.__name__, _CODE_V)
    return True


_MARKER_BATCH = "_hermes_menu_bridge_batch_v"


def _install_batch_hook() -> bool:
    """在「进批处理之前」把菜单项改写成命令 / 直接开卡。

    飞书适配器 ``_dispatch_inbound_event`` 只把「命令」放行直通，纯文本一律进批处理
    （静默期 + 每会话锁），会话忙时就被正在跑的回合挡在锁后面 —— 这正是「闲时灵、忙时失灵」
    的真根因。这里抢在它前面改写，让菜单项以命令身份走快通道。
    """
    for name, m in list(sys.modules.items()):
        if isinstance(name, str) and name.endswith("feishu.adapter") and hasattr(m, "FeishuAdapter"):
            return _patch_batch_class(m.FeishuAdapter)
    _warn_once(("batch-nomod",),
               "[FeishuMenuBridge] batch hook: 未找到 feishu.adapter 模块（等模块出现）")
    return False


def _patch_batch_class(cls) -> bool:
    if not isinstance(cls, type):
        return False
    if _mk(cls, _MARKER_BATCH) >= _CODE_V:
        # 2026-10-04 审计修复：同 _patch_busy_class —— 已装返回 True。
        return True
    orig = cls.__dict__.get("_dispatch_inbound_event")
    if orig is None:
        for base in cls.__mro__:
            if "_dispatch_inbound_event" in base.__dict__:
                orig = base.__dict__["_dispatch_inbound_event"]
                break
    if orig is None:
        _warn_once(("batch-nomethod", cls.__name__),
                   "[FeishuMenuBridge] batch hook: %s 缺目标方法 _dispatch_inbound_event，跳过",
                   cls.__name__)
        return False
    if getattr(orig, "_hermes_menu_bridge_batch", False):
        # 2026-10-07 审计修复（#2）：同 _patch_busy_class —— 剥链后用新逻辑重装，
        # 不再需要重启网关。
        _stale = _orig_of(orig)
        if _stale is None or getattr(_stale, "_hermes_menu_bridge_batch", False):
            _warn_once(("batch-stale", cls.__name__),
                       "[FeishuMenuBridge] batch hook: %s 旧版包装无法剥链（标记=%s），保持现状",
                       cls.__name__, _mk(cls, _MARKER_BATCH))
            return False
        orig = _stale

    async def _batch_rewrite(self, event):
        try:
            text = str(getattr(event, "text", "") or "").strip()
            if text and not text.startswith("/"):
                key = _resolve_menu_key(text) or text
                if key in COMMANDS:
                    try:
                        event.text = COMMANDS[key]
                    except Exception:
                        logger.debug("[FeishuMenuBridge] batch hook: 改写成命令失败，按原文放行",
                                     exc_info=True)
                    logger.info("[FeishuMenuBridge] 菜单项改写成命令 %r → %r（跳过批处理）",
                                   text, COMMANDS[key])
                elif key in CARD_BUILDERS:
                    # F01（审计修复）：适配器批处理同样跑在网关鉴权之前。
                    # 发卡前复用网关授权判断（适配器持有 gateway_runner）；未授权不发卡、放行原文。
                    if not _sender_authorized(getattr(self, "gateway_runner", None),
                                              getattr(event, "source", None)):
                        logger.info("[FeishuMenuBridge] 未授权来源，批处理不发卡（交回网关）")
                        return await orig(self, event)
                    chat_id = str(getattr(getattr(event, "source", None), "chat_id", "") or "")
                    if chat_id:
                        try:
                            await asyncio.to_thread(_ensure_card_routing, self)
                        except Exception:
                            pass
                        card = await asyncio.to_thread(build_card, key, chat_id)
                        if card is not None:
                            _res = await _send_card(self, chat_id, card)
                            if _send_ok(_res):
                                logger.info("[FeishuMenuBridge] 菜单项直接开卡 %r（跳过批处理）", text)
                                return None
                            # 2026-10-04 审计修复：发卡失败（含 API 错误码型、不抛异常的那种）
                            # 不再静默吞消息 —— 放行原文，让它照常进 agent。
                            logger.warning("[FeishuMenuBridge] 菜单项开卡 %r 未投递；按原文放行", key)
                    else:
                        logger.warning("[FeishuMenuBridge] 菜单项 %r build_card 返回空；按原文放行", key)
        except Exception:
            logger.warning("[FeishuMenuBridge] 入站改写失败，按原文放行", exc_info=True)
        return await orig(self, event)

    _batch_rewrite._hermes_menu_bridge_batch = True
    _batch_rewrite._hermes_orig = orig   # 2026-10-07（#2）：登记链尾，升版后可剥链重装
    cls._dispatch_inbound_event = _batch_rewrite
    try:
        setattr(cls, _MARKER_BATCH, _Guard(_CODE_V))
    except Exception:
        _warn_once(("batch-marker", cls.__name__),
                   "[FeishuMenuBridge] batch hook: 标记写入失败 %s（下轮重试，健康检查会标红）",
                   cls.__name__)
    if not _verify_live(cls, "_dispatch_inbound_event", _batch_rewrite, _MARKER_BATCH):
        return False      # 成功日志只在回读通过后打（True = 验证过）
    # 出站卡化包装也在这一刻装上：这时刻正好是「类出现」，不用等有人发消息。
    try:
        _ensure_send_cardify(cls)
    except Exception:
        logger.warning("[FeishuMenuBridge] send cardify 安装失败", exc_info=True)
    logger.info("[FeishuMenuBridge] batch hook installed on %s (v%d)", cls.__name__, _CODE_V)
    return True


def _try_install() -> bool:
    if not _INSTALL_LOCK.acquire(blocking=False):
        logger.debug("[FeishuMenuBridge] install skipped: lock busy")
        return True  # 已有线程在装：本轮跳过，避免重复包装
    try:
        return _try_install_locked()
    finally:
        _INSTALL_LOCK.release()


def _try_install_locked() -> bool:
    try:
        a = _install_lark_builder_hook()
    except Exception:
        logger.warning("[FeishuMenuBridge] lark builder hook FAILED", exc_info=True)
        a = False
    try:
        b = _install_adapter_hook()
    except Exception:
        logger.warning("[FeishuMenuBridge] adapter hook FAILED", exc_info=True)
        b = False
    try:
        c = _install_dispatcher_hook()
    except Exception:
        logger.warning("[FeishuMenuBridge] dispatcher hook FAILED", exc_info=True)
        c = False
    try:
        d = _install_busy_hook()
    except Exception:
        logger.warning("[FeishuMenuBridge] busy hook FAILED", exc_info=True)
        d = False
    try:
        e = _install_batch_hook()
    except Exception:
        logger.warning("[FeishuMenuBridge] batch hook FAILED", exc_info=True)
        e = False
    # 注：False 不代表失败 —— 也可能是「已在当前版本/目标类暂时不在场」。
    # 真正的问题由各安装器自己的一次性告警覆盖（busy-nomethod/busy-stale/…），
    # 以及 _patch_health() 的巡检（它用「标记 >= _CODE_V 且挂着本文件的包装」判定，无歧义）。
    return bool(a and b and c and d and e)


def _diagnose(tag: str = "") -> None:
    """把网关进程里的真实情况打进日志：适配器类是否被补丁、分发器版本、gc 是否能找到实例。"""
    try:
        mods = [n for n, m in list(sys.modules.items())
                if isinstance(n, str) and n.endswith("feishu.adapter") and hasattr(m, "FeishuAdapter")]
        ads = _live_adapters()
        info = []
        for a in ads:
            cls = type(a)
            h = getattr(a, "_event_handler", None)
            ws = getattr(a, "_ws_client", None)
            wh = getattr(ws, "_event_handler", None) if ws is not None else None
            pmap = getattr(h, "_callback_processor_map", None) or {}
            evmap = getattr(h, "_processorMap", None) or getattr(h, "_processor_map", None) or {}
            info.append({
                "callbacks": sorted(k for k in pmap.keys()),
                "events": len(evmap),
                "cls_marker": _mk(cls, _MARKER),
                "h_cls_marker": _mk(type(h), _MARKER_DO),
                "ws_same_handler": wh is h,
                "ws_h_marker": _mk(type(wh), _MARKER_DO) if wh is not None else None,
                "handler_v": _mk(h, _MARKER_VER),
                "same_cls": cls is next((getattr(sys.modules[n], "FeishuAdapter") for n in mods), None),
                "ws_connected": bool(getattr(a, "_ws_client", None) is not None),
            })
        logger.debug("[FeishuMenuBridge] diag%s modules=%s adapters=%d %s", tag, mods, len(ads), info)
    except Exception:
        logger.warning("[FeishuMenuBridge] diag failed", exc_info=True)


_HEALTHCHECK = Path(_HOME_DIR + "/cache/scratch/menu_bridge_healthcheck.json")
_ALLNONE_N = 0   # 连续「全部族都看不到目标类」的巡检次数（半死窗口自愈用，2026-10-04 审计加入）
_SEEN_ANY_OK = False  # 本进程是否出现过「健康」巡检（2026-10-07 复审：非网关进程里目标类
                      # 天然不可见，若只按「全 None」计数，Dashboard 会每 25 分钟空跑一次自愈）


def _patch_health(tag: str = "") -> Dict[str, Any]:
    """巡检关键补丁族：标记版本 >= _CODE_V，且目标属性上确实挂着本文件定义的包装。

    纯只读（不装、不改、不抛）；目标不在场记 None（热重载瞬态容错，不算不健康）。
    返回 {"healthy": bool, "families": {...}, "tag": str}。
    """
    fam: Dict[str, Any] = {"batch": None, "busy": None, "routing": None,
                           "cardify": None, "resolved2": None, "sendfinal": None,
                           "ptgate": None}

    # 1) 批处理改写（FeishuAdapter._dispatch_inbound_event）
    for name, m in list(sys.modules.items()):
        if isinstance(name, str) and name.endswith("feishu.adapter") and hasattr(m, "FeishuAdapter"):
            cls = getattr(m, "FeishuAdapter")
            fn = cls.__dict__.get("_dispatch_inbound_event")
            if fn is None:
                fn = getattr(cls, "_dispatch_inbound_event", None)
            fam["batch"] = bool(getattr(fn, "_hermes_menu_bridge_batch", False)
                                and _mk(cls, _MARKER_BATCH) >= _CODE_V)
            break

    # 2) 忙线拦截（GatewayRunner._hm_handle_running_session_message）
    for mod in list(sys.modules.values()):
        cls = getattr(mod, "GatewayRunner", None) if mod is not None else None
        if isinstance(cls, type) and "_hm_handle_running_session_message" in dir(cls):
            fn = cls.__dict__.get("_hm_handle_running_session_message")
            if fn is None:
                fn = getattr(cls, "_hm_handle_running_session_message", None)
            fam["busy"] = bool(getattr(fn, "_hermes_menu_bridge_busy", False)
                               and _mk(cls, _MARKER_BUSY) >= _CODE_V)
            break

    # 3) 活适配器上的卡片回调路由（鸭子类型，不依赖类补丁）
    try:
        ads = _live_adapters()
    except Exception:
        ads = []
    if ads:
        fam["routing"] = all(_handler_has_im(getattr(a, "_event_handler", None)) for a in ads)

    # 4) 出站卡化 + 已处理卡同构（FeishuAdapter 上，批3 新增覆盖）
    for _name, _m in list(sys.modules.items()):
        if isinstance(_name, str) and _name.endswith("feishu.adapter") and hasattr(_m, "FeishuAdapter"):
            _cls = getattr(_m, "FeishuAdapter")
            _fn = getattr(_cls, "_feishu_send_with_retry", None)
            fam["cardify"] = bool(getattr(_fn, "_fmb_cardify_wrapped", False)
                                  and _mk(_cls, "_fmb_send_cardify") >= _CODE_V)
            _r1 = getattr(_cls, "_build_resolved_slash_confirm_card", None)
            _r2 = getattr(_cls, "_build_resolved_approval_card", None)
            fam["resolved2"] = bool(
                _mk(getattr(_r1, "__func__", _r1), _MARKER_RES2) >= _CODE_V
                and _mk(getattr(_r2, "__func__", _r2), _MARKER_RES2) >= _CODE_V)
            break

    # 5) 回执抑制（BasePlatformAdapter.send_final_ledgered 上，批3 新增覆盖）
    try:
        from gateway.platforms.base import BasePlatformAdapter as _BPA
        fam["sendfinal"] = bool(_mk(_BPA.send_final_ledgered, _MARKER_SENDFINAL) >= _CODE_V)
    except Exception:
        pass

    # 6) PT 静音窗门（gateway.display_config.resolve_tool_progress 上）
    try:
        from gateway import display_config as _dc2
        fam["ptgate"] = bool(_mk(_dc2.resolve_tool_progress, _MARKER_PTGATE) >= _CODE_V)
    except Exception:
        pass

    present = {k: v for k, v in fam.items() if v is not None}
    healthy = bool(present) and all(bool(v) for v in present.values())
    return {"healthy": healthy, "families": fam, "tag": tag}


def _health_tick(periodic: bool = False) -> None:
    """每 tick 查一次触发文件（很便宜）；periodic=True 时（随 5 分钟诊断）做全量巡检。"""
    try:
        if _HEALTHCHECK.exists():
            _HEALTHCHECK.unlink(missing_ok=True)
            logger.warning("[FeishuMenuBridge] health(file)：%s", _patch_health(" file"))
            return
        if not periodic:
            return
        res = _patch_health(" periodic")
        if res["healthy"]:
            globals()["_SEEN_ANY_OK"] = True
            globals()["_ALLNONE_N"] = 0
            logger.debug("[FeishuMenuBridge] health: %s", res)
        else:
            bad = tuple(sorted(k for k, v in res["families"].items() if v is not True))
            _warn_once(("health", bad), "[FeishuMenuBridge] health UNHEALTHY: %s", res)
            # 2026-10-04 审计修复：目标类连续全不可见（半死窗口，实测曾持续 18+ 分钟）——
            # 到阈值就强制全量重装，不再干等热重载/重启。
            # 2026-10-07 审计修复（#16）：原判据「fam 里全部是 None」在真网关里**不可达**
            # —— sendfinal/ptgate 依赖的模块必然已加载，恒非 None，所以自愈是死代码。
            # 改成只看「靠模块/类发现」的那几族：它们同时为 None 才是真的半死窗口。
            fams = res.get("families") or {}
            _discover = ("batch", "busy", "routing", "cardify", "resolved2")
            # 2026-10-07 复审：必须「本进程曾经健康过」——否则在 Dashboard / 一次性 CLI 进程里
            # 目标类天然不可见，会误判成半死窗口并在错误进程里空跑重装。
            if fams and globals().get("_SEEN_ANY_OK") and all(fams.get(k) is None for k in _discover):
                globals()["_ALLNONE_N"] = int(globals().get("_ALLNONE_N", 0)) + 1
                if globals()["_ALLNONE_N"] >= 5:
                    logger.warning("[FeishuMenuBridge] 目标类连续 %d 次全不可见，强制全量重装补丁",
                                   globals()["_ALLNONE_N"])
                    try:
                        _try_install()
                        globals()["_ALLNONE_N"] = 0
                    except Exception:
                        logger.debug("[FeishuMenuBridge] 强制重装失败", exc_info=True)
    except Exception:
        logger.debug("[FeishuMenuBridge] health tick 异常", exc_info=True)


_SELFTEST = Path(_HOME_DIR + "/cache/scratch/menu_bridge_selftest.json")


def _self_test_tick() -> None:
    """自测：把合成的一次卡片点击喂给拦截层，端到端验证（不依赖真人点击）。"""
    try:
        if not _SELFTEST.exists():
            return
        spec = json.loads(_SELFTEST.read_text(encoding="utf-8"))
        _SELFTEST.unlink(missing_ok=True)
        ads = _live_adapters()
        if not ads:
            logger.warning("[FeishuMenuBridge] selftest: 没有找到线上适配器")
            return
        ad = ads[0]
        h = getattr(ad, "_event_handler", None)
        payload = json.dumps({
            "schema": "2.0",
            "header": {"event_type": "card.action.trigger", "event_id": "selftest"},
            "event": {
                "operator": {"open_id": spec.get("open_id", "")},
                "action": {"tag": "button", "value": spec.get("value", {})},
                "context": {"open_chat_id": spec.get("chat_id", ""),
                            "open_message_id": spec.get("message_id", "")},
            },
        }).encode()
        handled = _intercept_card_action(h, payload)
        logger.warning("[FeishuMenuBridge] selftest 结果: handled=%s value=%s", handled, spec.get("value"))
    except Exception:
        logger.warning("[FeishuMenuBridge] selftest 失败", exc_info=True)


def _handler_has_im(h: Any) -> bool:
    """SDK 有两张表：事件在 _processorMap（驼峰），卡片回调在 _callback_processor_map。"""
    if h is None:
        return False
    for attr in ("_processorMap", "_processor_map", "_callback_processor_map"):
        m = getattr(h, attr, None)
        if isinstance(m, dict) and any("im.message.receive" in str(k) for k in m):
            return True
    return False


_HEAL_TS = 0.0
# 停止标志：退化路径（keeper.py 缺失）与「请上一代退出」用；正常路径由 keeper 管线程。
_STOP = False
# 已退役标志：置位后本代不再干活（双保险，防"该退的还在跑"）。
_RETIRED = False
# _watch_once 的本轮节流状态（每代重置；等价于原来每次重载新建线程时的局部变量）
_W_FAST_UNTIL = time.time() + 300.0
_W_LAST_ROUTE = 0.0
_W_LAST_DIAG = 0.0


def _heal_handler() -> None:
    """活分发器缺消息处理器时重建并换上去（否则消息事件被静默丢弃，表现为「飞书没反应」）。"""
    try:
        for ad in _live_adapters():
            h = getattr(ad, "_event_handler", None)
            if _handler_has_im(h):
                continue
            build = getattr(ad, "_build_event_handler", None)
            if not callable(build):
                continue
            try:
                new_h = build()
            except Exception as e:
                logger.warning("[FeishuMenuBridge] handler 重建失败: %s: %s", type(e).__name__, e)
                continue
            if not _handler_has_im(new_h):
                logger.warning("[FeishuMenuBridge] 重建后仍缺消息处理器，放弃本次重建")
                with _STATE_LOCK:
                    global _HEAL_TS
                    _HEAL_TS = 0.0  # 允许下一轮立即重试
                continue
            with _STATE_LOCK:
                ad._event_handler = new_h
                ws = getattr(ad, "_ws_client", None)
                if ws is not None and hasattr(ws, "_event_handler"):
                    ws._event_handler = new_h
            logger.warning("[FeishuMenuBridge] handler 已重建并换上")
    except Exception:
        logger.warning("[FeishuMenuBridge] heal handler 失败", exc_info=True)


def _sleep_interruptible(seconds: float) -> None:
    """分片睡眠（退化路径用）：让 _STOP 能在 1 秒内生效。"""
    deadline = time.time() + seconds
    while True:
        if _STOP:
            return
        remain = deadline - time.time()
        if remain <= 0:
            return
        time.sleep(min(0.5, remain))


def _watch_once() -> float:
    """守护线程的**一轮**工作（返回本轮之后应休眠的秒数）。

    由 keeper 的 watch_loop 每轮调用 → 因此**永远执行最新一代的代码**；本模块被
    替换时 keeper 会自我让位，旧代不会再被调用（不再需要注入 SystemExit 退役）。
    """
    global _HEAL_TS, _W_LAST_ROUTE, _W_LAST_DIAG
    if _RETIRED:
        return 10.0
    try:
        now = time.time()  # 必须先取时间：下面几处都要用
        _self_test_tick()
        _health_tick()                 # 只查触发文件（很便宜）；全量巡检在 5 分钟诊断处
        _sweep_stale_live_adapter()
        with _STATE_LOCK:
            due = (now - _HEAL_TS) > 30.0  # 自愈节流：别反复重建分发器
            if due:
                _HEAL_TS = now
        if due:
            _heal_handler()
        ok = _try_install()
        # 注意：即使 ok 为假（例如 SDK 类导入拿不到）也要继续走鸭子类型的活对象补丁
        if now - _W_LAST_ROUTE > 5.0:
            _W_LAST_ROUTE = now
            for _a in _live_adapters():
                _ensure_card_routing(_a)
        if now - _W_LAST_DIAG > 300.0:
            _W_LAST_DIAG = now
            _diagnose(" watch=%s" % _watcher_diag())
            _health_tick(periodic=True)   # 每 5 分钟顺手做一次补丁健康巡检
        return 0.5 if (not ok or now < _W_FAST_UNTIL) else 10.0
    except Exception:
        logger.debug("[FeishuMenuBridge] watcher 单轮异常", exc_info=True)
        return 2.0


def _watcher_diag() -> str:
    """诊断串：主 watcher 存活 / 看门狗存活 / 看门狗拉起次数 / watcher 退出原因。"""
    k = _keeper_module()
    if k is None:
        return "%d(fallback)" % sum(1 for t in threading.enumerate() if t.name == "feishu-menu-bridge")
    st = k.status()
    return "%d+%d wd_rescues=%d%s" % (
        int(bool(st["watcher"])), int(bool(st["watchdog"])), st["rescues"],
        "" if not st["exit_reason"] else " exit=" + str(st["exit_reason"]),
    )


def _watch() -> None:
    """退化路径（keeper.py 缺失时）：插件自带守护线程，仍认 _STOP、仍不注入异常。"""
    while not _STOP:
        _sleep_interruptible(_watch_once())


def _retire_legacy_threads() -> None:
    """请「keeper 之前的老式 _watch 线程」退出。

    keeper 出现后，新一代线程的 target 在 keeper 模块里（``watch_loop``），**不会**被这里
    匹配到 —— 所以正常情况下本函数找不到任何线程、什么都不做（一次性迁移路径）。

    老式线程认 ``_STOP``（分片睡眠里看到就退出，≤0.5s）→ **只置标志，不注入异常**；
    只有「更旧的、不认标志的版本」才会在宽限 2.5 秒后由异步 reaper 兜底注入 SystemExit。
    注入**绝不放在 register() 里等待**（插件加载有 10 秒硬超时）。
    """
    me = threading.current_thread()
    legacy: List[Any] = []
    for t in threading.enumerate():
        if t is me or not t.is_alive():
            continue
        tgt = getattr(t, "_target", None)
        if tgt is None or tgt is _watch:
            continue
        if getattr(tgt, "__module__", "") != __name__ or "_watch" not in getattr(tgt, "__qualname__", ""):
            continue
        g = getattr(tgt, "__globals__", None)
        if isinstance(g, dict):
            g["_STOP"] = True      # 老式 _watch 在分片睡眠里看到就会自己退出
            g["_RETIRED"] = True   # 双保险：本代不再干活
        legacy.append(t)
    if not legacy:
        return
    logger.warning("[FeishuMenuBridge] 已请 %d 个上一代守护线程退出（置标志，不注入）", len(legacy))
    threading.Thread(target=_legacy_reaper, args=(legacy,), name="fmb-legacy-reaper", daemon=True).start()


def _legacy_reaper(threads: List[Any]) -> None:
    """宽限 2.5 秒后仍存活的老式线程 → 兜底注入 SystemExit（异步，不占加载时间）。"""
    deadline = time.time() + 2.5
    alive = list(threads)
    while alive and time.time() < deadline:
        alive = [t for t in alive if t.is_alive()]
        if alive:
            time.sleep(0.05)
    if not alive:
        return
    for t in alive:
        try:
            res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_long(t.ident), ctypes.py_object(SystemExit))
            if res == 1:
                logger.info("[FeishuMenuBridge] 更旧版线程不认标志，已兜底注入退出: %s", t.name)
            elif res > 1:
                # 误伤多个线程：立刻撤销。2026-10-04 修：撤销必须传 NULL——
                # ctypes.py_object(None) 传的是「指向 None 的 PyObject*」而非 NULL，
                # 无法清除 pending exc（探针实测：撤销线程随后死于
                # SystemError: _PyErr_SetObject: exception None is not a BaseException subclass）；
                # c_void_p(0) 才是 NULL，探针验证线程存活。
                ctypes.pythonapi.PyThreadState_SetAsyncExc(
                    ctypes.c_long(t.ident), ctypes.c_void_p(0))
                logger.error("[FeishuMenuBridge] 注入异常误伤 %d 个线程，已撤销", res)
        except Exception:
            logger.debug("[FeishuMenuBridge] 兜底注入失败: %s", t.name, exc_info=True)


# 兼容旧名（文档/脚本里可能引用）
_retire_zombies = _retire_legacy_threads


def _boot_keeper(ctx) -> None:
    """把守护线程交给 keeper：交班 + 注册代际感知的卸载钩子。

    正常收尾用官方 ``ctx.on_unload``（卸载/禁用/强制重载都会跑）；keeper 的自我让位检查
    是双保险 —— 即使钩子没跑到，线程也不会变成僵尸，更不会被注入异常。
    """
    k = _keeper_module()
    if k is None:
        # 退化路径：插件自带线程（仍不注入异常、仍认 _STOP）
        try:
            threading.Thread(target=_watch, name="feishu-menu-bridge", daemon=True).start()
        except Exception:
            logger.warning("[FeishuMenuBridge] 退化守护线程启动失败", exc_info=True)
        return
    token = k.boot(sys.modules[__name__])
    try:
        ctx.on_unload(lambda: k.request_stop(token))
    except Exception:
        logger.debug("[FeishuMenuBridge] on_unload 注册失败（keeper 自我让位仍会兜住）", exc_info=True)


def register(ctx) -> None:
    try:
        # SDK 会在 INFO 级把带 access_key/ticket 的 wss URL 打进日志 → 调高级别，防凭据落盘
        logging.getLogger("Lark").setLevel(logging.WARNING)
    except Exception:
        pass
    try:
        _try_install()
    except Exception:
        logger.warning("[FeishuMenuBridge] initial install failed", exc_info=True)
    try:
        ctx.register_hook("pre_gateway_dispatch", _on_pre_gateway_dispatch)
    except Exception:
        logger.warning("[FeishuMenuBridge] hook registration failed", exc_info=True)
    try:
        _retire_legacy_threads()
    except Exception:
        pass
    # 交班给 keeper：唯一一条 watcher 线程跨代存活，每轮执行最新一代的代码
    try:
        _boot_keeper(ctx)
    except Exception:
        logger.warning("[FeishuMenuBridge] keeper 交班失败", exc_info=True)
    logger.info("[FeishuMenuBridge] registered: %d 命令 / %d 卡片",
                   len(COMMANDS), len(CARD_BUILDERS))
