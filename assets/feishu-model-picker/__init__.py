"""飞书交互式模型选择器（本地扩展插件）。

给官方 FeishuAdapter 运行期补上：
  * ``send_model_picker`` —— /model 无参数时发送「提供方 → 模型」可点选卡片
    （网关探测适配器类是否实现该方法：实现则用卡片，否则退回文字列表）。
  * 卡片点击路由 —— 在 ``_on_card_action_trigger`` 前挂一层，识别
    ``{"hermes_model_pick": {...}}`` 动作并就地更新卡片（翻页/下钻/切换）。

不修改任何官方文件；守护线程（keeper 单例，跨热重载存活）持续校验补丁，
官方插件惰性加载 / 热重载后自动补装，且热重载即生效（无需重启网关）。
"""
from __future__ import annotations

import inspect
import itertools
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hermes_plugins.feishu_model_picker")

_MARKER = "_hermes_feishu_model_picker_installed"
_MARKER_LARK = "_hermes_feishu_model_picker_lark_hook"
#: 补丁代际戳：粘性标记改为「带代际」的标记 —— 热重载后新代必须能重装自己的 hook
#: （旧实现只认布尔标记，导致改插件后热重载不生效、必须重启网关）。
_STAMP = "_hermes_fmp_stamp"

# ── keeper 接线（跨重载单例守护宿主，见 keeper.py）─────────────────────
# 旧实现：register() 每次新起一条 while True 的 _watch 线程且不认停止标志
# → 每次热重载泄漏一条线程（实测网关上有 13 条），旧模块命名空间永不回收。
# 现改为：线程只有一条、跨代存活、每轮执行最新代代码（详见 keeper.py）。
# keeper 模块名不在 hermes_plugins.<slug> 前缀下 → 不会被 evict。
_KEEPER_NAME = "hermes_plugins._fmp_keeper"
_KEEPER_FILE = Path(__file__).with_name("keeper.py")
_KEEPER_VERSION = 1   # 必须与 keeper.py 里的 KEEPER_VERSION 一致（改 keeper.py 时两边一起加）


#: keeper 对外契约（2026-10-04 审计：把「改 keeper.py 要两边一起改、靠人盯注释」变成机械检查）
_WATCHER_NAME_EXPECTED = "feishu-model-picker"
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
            # 旧 keeper 用**它自己的停止标志**收摊（置标志，不注入异常）
            try:
                old.stop = True
            except Exception:
                pass
            # 搬走共享容器（_PICKERS / _PID …）：同一批对象继续被新代别名过去
            try:
                mod.state.update(getattr(old, "state", {}) or {})
            except Exception:
                pass
            logger.warning("[FeishuModelPicker] keeper 换版 %s → %s（已重载，共享状态已搬移）",
                           getattr(old, "KEEPER_VERSION", "?"), _KEEPER_VERSION)
        return mod
    except Exception:
        logger.warning("[FeishuModelPicker] keeper 加载失败，退化为插件自带线程", exc_info=True)
        sys.modules.pop(_KEEPER_NAME, None)
        return None


def _shared(key: str, factory):
    """取/建跨代共享容器：热重载后仍指向同一对象（否则已发出的卡片会点不动）。"""
    k = _keeper_module()
    if k is None:
        return factory()
    return k.shared(key, factory)


# 缺陷 #12 修复：keeper 缺失时，代际戳不再退化为常量 "fallback"（那会让热重载后新代
# 误判「已装过」而跳过重装 → 改了插件热重载不生效）。改为「文件 mtime + 导入时刻」：
# 模块级只算一次 —— 若放进函数里每次读 mtime 会每次不同，反而更糟。
# 同一进程内反复调用返回同一值（同代稳定）；插件文件被改动 → 重载 → mtime 变化 → 戳变化。
_FILE_MTIME = int(os.path.getmtime(__file__))
_IMPORT_TS = int(time.time())


def _stamp_value() -> str:
    """当前代应写入的补丁代际戳（keeper 缺失时用文件 mtime + 导入时刻，同代稳定）。"""
    k = _keeper_module()
    if k is None:
        return "fallback.m%d.i%d" % (_FILE_MTIME, _IMPORT_TS)
    return "v%d.g%d" % (_KEEPER_VERSION, int(getattr(k, "token", 0) or 0))


_PICKERS: Dict[int, Dict[str, Any]] = _shared("pickers", dict)
_PID = _shared("pid", lambda: itertools.count(1))
_PAGE = 10              # 模型每页数量
_STALE_SECONDS = 3600.0
_TICK_FAST, _TICK_SLOW = 0.5, 10.0


# ── 小工具 ──────────────────────────────────────────────

def _btn(label: str, value: Dict[str, Any], kind: str = "default") -> Dict[str, Any]:
    # 2026-10-04：全套卡转 JSON 2.0 —— 按钮值放进 behaviors（2.0 形态）+ small/fill 与面板卡一致。
    return {
        "tag": "button",
        "type": kind,
        "size": "small",
        "width": "fill",
        "text": {"tag": "plain_text", "content": str(label)[:40]},
        "behaviors": [{"type": "callback", "value": value}],
    }


def _rows(buttons: List[Dict[str, Any]], per_row: int = 3) -> List[Dict[str, Any]]:
    """等宽按钮行（2.0：column_set 等宽列 + 按钮 fill，同排宽度完全一致）。"""
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


def _card(title: str, template: str, markdown: str,
          buttons: Optional[List[Dict[str, Any]]] = None, per_row: int = 3) -> Dict[str, Any]:
    """2026-10-04：1.0 → 2.0（schema/body.elements）；字段结构对齐 menu-bridge 的视觉体系。"""
    elements: List[Dict[str, Any]] = [{"tag": "markdown", "content": markdown, "text_size": "normal"}]
    if buttons:
        elements.extend(_rows(buttons, per_row))
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": title}, "template": template},
        "body": {"direction": "vertical", "padding": "12px 12px 12px 12px", "elements": elements},
    }


def _short(model_id: str, limit: int = 36) -> str:
    s = str(model_id or "")
    if "/" in s:
        s = s.split("/")[-1]
    return s if len(s) <= limit else s[: limit - 3] + "..."


def _purge_stale() -> None:
    now = time.time()
    for pid in [p for p, st in list(_PICKERS.items()) if now - st.get("ts", 0) > _STALE_SECONDS]:
        _PICKERS.pop(pid, None)


def _provider_label(p: Dict[str, Any]) -> str:
    label = str(p.get("label") or p.get("name") or p.get("slug") or "?")
    total = p.get("total_models") or len(p.get("models") or [])
    if total:
        label = f"{label}（{total}）"
    if p.get("is_current"):
        label = "✓ " + label
    return label


# ── 卡片构建 ────────────────────────────────────────────

def _provider_card(pid: int, providers: List[dict], current_model: str, current_provider: str,
                   page: int = 0) -> Dict[str, Any]:
    # 缺陷 #11 修复：提供方不再全部平铺（提供方多时飞书卡片元素超限、发送失败），
    # 改为与 _models_card 一致的 _PAGE 分页；按钮里的 i 仍是**全局**索引（下钻 _models_card 用）。
    pages = max(1, (len(providers) + _PAGE - 1) // _PAGE)
    page = max(0, min(int(page), pages - 1))
    start = page * _PAGE
    buttons = [
        _btn(_provider_label(p), {"hermes_model_pick": {"a": "p", "pid": pid, "i": start + k}})
        for k, p in enumerate(providers[start:start + _PAGE])
    ]
    nav: List[Dict[str, Any]] = []
    if page > 0:
        nav.append(_btn("◀ 上一页", {"hermes_model_pick": {"a": "pp", "pid": pid, "pg": page - 1}}))
    if page < pages - 1:
        nav.append(_btn("下一页 ▶", {"hermes_model_pick": {"a": "pp", "pid": pid, "pg": page + 1}}))
    nav.append(_btn("✗ 取消", {"hermes_model_pick": {"a": "x", "pid": pid}}))
    md = (
        f"**当前**：`{current_model}`（`{current_provider}`）\n"
        f"点击提供方查看模型（第 {page + 1}/{pages} 页）："
    )
    card = _card("🤖 切换模型 · 选择提供方", "blue", md, buttons, per_row=1)
    card["body"]["elements"].extend(_rows(nav, per_row=2))
    return card


def _models_card(pid: int, st: Dict[str, Any], i: int, page: int) -> Dict[str, Any]:
    providers = st.get("providers") or []
    p = providers[i]
    models = [str(m) for m in (p.get("models") or [])]
    pages = max(1, (len(models) + _PAGE - 1) // _PAGE)
    page = max(0, min(int(page), pages - 1))
    chunk = models[page * _PAGE:(page + 1) * _PAGE]
    current = str(st.get("current_model") or "")
    cur_slug = str(st.get("current_provider") or "")
    buttons: List[Dict[str, Any]] = []
    for k, m in enumerate(chunk):
        mi = page * _PAGE + k
        label = _short(m, 44)
        is_cur = (m == current) and (str(p.get("slug") or "") == cur_slug)
        if is_cur:
            label = "✓ " + label
        buttons.append(_btn(
            label, {"hermes_model_pick": {"a": "m", "pid": pid, "i": i, "mi": mi}},
            "primary" if is_cur else "default"))
    nav: List[Dict[str, Any]] = []
    if page > 0:
        nav.append(_btn("◀ 上一页", {"hermes_model_pick": {"a": "pg", "pid": pid, "i": i, "pg": page - 1}}))
    if page < pages - 1:
        nav.append(_btn("下一页 ▶", {"hermes_model_pick": {"a": "pg", "pid": pid, "i": i, "pg": page + 1}}))
    nav.append(_btn("⬆ 返回提供方", {"hermes_model_pick": {"a": "b", "pid": pid}}))
    nav.append(_btn("✗ 取消", {"hermes_model_pick": {"a": "x", "pid": pid}}))
    name = str(p.get("label") or p.get("slug") or "?")
    md = f"「**{name}**」选择模型（第 {page + 1}/{pages} 页）"
    # 2026-10-04：模型名前被 3 列挤成「DeepS...」——改为一行一个（全宽），名字完整可读。
    card = _card(f"🤖 切换模型 · {name}", "blue", md, buttons, per_row=1)
    card["body"]["elements"].extend(_rows(nav, per_row=2))
    return card


# ── 点击处理（同步返回 = 原地更新卡片）───────────────────

def _handle_click(adapter, event, pick: Dict[str, Any]):
    try:
        loop = getattr(adapter, "_loop", None)
        if loop is None or not adapter._loop_accepts_callbacks(loop):
            return adapter._card_response()
        pid = pick.get("pid")
        st = _PICKERS.get(pid)
        if not st:
            return adapter._card_response(_card(
                "⌛ 本卡片已过期", "grey", "请重新发送 `/model` 再选一次。"))
        a = str(pick.get("a") or "")
        logger.info("[FeishuModelPicker] click a=%s pid=%s", a, pid)
        if a == "x":
            _PICKERS.pop(pid, None)
            return adapter._card_response(_card("✖ 已取消", "grey", "没有做任何修改。"))
        if a == "b":
            return adapter._card_response(_provider_card(
                pid, st.get("providers") or [], st.get("current_model") or "",
                st.get("current_provider") or ""))
        if a == "p":
            return adapter._card_response(_models_card(pid, st, int(pick.get("i") or 0), 0))
        if a == "pg":
            return adapter._card_response(_models_card(
                pid, st, int(pick.get("i") or 0), int(pick.get("pg") or 0)))
        if a == "pp":
            return adapter._card_response(_provider_card(
                pid, st.get("providers") or [], st.get("current_model") or "",
                st.get("current_provider") or "", int(pick.get("pg") or 0)))
        if a == "m":
            operator = getattr(event, "operator", None)
            open_id = str(getattr(operator, "open_id", "") or "")
            try:
                authorized = adapter._is_interactive_operator_authorized(open_id)
            except Exception:
                # 2026-10-04 审计修复：鉴权检查异常时按「未授权」处理（fail-closed），
                # 与 menu-bridge 的策略保持一致；异常留警告日志便于排查。
                authorized = False
                logger.warning("[FeishuModelPicker] 鉴权检查异常，按未授权处理 open_id=%s", open_id,
                               exc_info=True)
            if not authorized:
                return adapter._card_response(_card("⛔ 无权限", "red", "此操作仅限授权的操作人。"))
            i = int(pick.get("i") or 0)
            mi = int(pick.get("mi") or 0)
            try:
                model_id = str((st.get("providers") or [])[i]["models"][mi])
            except Exception:
                return adapter._card_response()
            scheduled = adapter._submit_on_loop(loop, _complete_pick(adapter, pid, i, mi))
            if not scheduled:
                return adapter._card_response()
            return adapter._card_response(_card(
                "⏳ 正在切换…", "indigo", f"正在切换到 **{_short(model_id)}**，请稍候…"))
    except Exception:
        logger.warning("[FeishuModelPicker] click handler error", exc_info=True)
        try:
            return adapter._card_response()
        except Exception:
            return None
    return adapter._card_response()


async def _complete_pick(adapter, pid: int, i: int, mi: int) -> None:
    st = _PICKERS.pop(pid, None) or {}
    providers = st.get("providers") or []
    chat_id = str(st.get("chat_id") or "")
    mid = str(st.get("message_id") or "")

    async def _push_card(card: Dict[str, Any], text: str) -> None:
        """把卡片原地 PATCH 回原消息；拿不到 message_id 时退化为文本重发。"""
        if mid and chat_id and getattr(adapter, "_client", None):
            try:
                from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody
                body = PatchMessageRequestBody.builder().content(
                    json.dumps(card, ensure_ascii=False)).build()
                req = PatchMessageRequest.builder().message_id(mid).request_body(body).build()
                resp = await adapter._run_blocking(adapter._client.im.v1.message.patch, req)
                if adapter._response_succeeded(resp):
                    return
            except Exception as exc:  # noqa: BLE001
                logger.warning("[FeishuModelPicker] card update failed: %s", exc)
        if chat_id:
            try:
                await adapter._feishu_send_with_retry(
                    chat_id=chat_id, msg_type="text",
                    payload=json.dumps({"text": ("🤖 " + text)[:4000]}, ensure_ascii=False),
                    reply_to=None, metadata=None)
            except Exception:
                logger.warning("[FeishuModelPicker] fallback send failed", exc_info=True)

    try:
        model_id = str(providers[i]["models"][mi])
        slug = str(providers[i].get("slug") or "")
    except Exception as exc:  # noqa: BLE001
        # 缺陷 #13 修复：索引越界/结构异常不再静默 return（用户卡片会永久停在「⏳ 正在切换…」）。
        # _PICKERS.pop 已把状态弹掉，故先取出局部 mid/chat_id 才能回写；此处不再静默。
        logger.warning("[FeishuModelPicker] complete_pick 选择已失效 pid=%s i=%s mi=%s: %s",
                       pid, i, mi, exc)
        await _push_card(
            _card("❌ 选择已失效", "red", "卡片数据已过期或结构异常，请重新发送 `/model` 再选一次。"),
            "选择已失效，请重新发送 /model 再选一次。")
        return
    ok = False
    text = "选择已失效，未执行切换。"
    cb = st.get("on_model_selected")
    if cb:
        try:
            # 网关回调签名：(_chat_id, model_id, provider_slug)
            result = cb(chat_id, model_id, slug)
            if inspect.isawaitable(result):
                result = await result
            text = str(result) if result else f"已切换到 {model_id}"
            ok = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("[FeishuModelPicker] switch callback failed", exc_info=True)
            text = f"切换失败：{exc}"
    logger.info("[FeishuModelPicker] switch model=%s provider=%s ok=%s", model_id, slug, ok)
    card = _card("✅ 已切换" if ok else "❌ 切换失败", "green" if ok else "red", text)
    # 2026-10-04 修复：原走 SDK 的 message.update（PUT）—— 对 interactive 会报
    # 230001 invalid msg_type（与菜单卡翻页同一坑）；改走 PATCH，与 menu-bridge 一致。
    # 缺陷 #13 修复：PATCH / 文本重发逻辑抽到 _push_card，供上面「索引失败」路径复用。
    await _push_card(card, text)


# ── 补丁安装 ────────────────────────────────────────────

def _install_lark_builder_hook() -> bool:
    """拦截 lark 分发器构建：凭证窗口无关——适配器每次建 handler 都经过这里。

    适配器在连接时调用 ``EventDispatcherHandlerBuilder.register_p2_card_action_trigger``
    注册点击回调；本补丁把它包一层，先识别我们的 ``hermes_model_pick`` 动作。
    由于执行在“构建时刻”而非“连接时刻”语义上，无论我们何时装入都能接住。
    """
    try:
        from lark_oapi.event.dispatcher_handler import EventDispatcherHandlerBuilder
    except Exception:
        return False
    stamp = _stamp_value()
    if (getattr(EventDispatcherHandlerBuilder, _MARKER_LARK, False)
            and getattr(EventDispatcherHandlerBuilder, _STAMP, None) == stamp):
        return True
    # 原始函数只记一次：本插件自己的补丁层绝不叠加（否则每次重载多包一层）
    orig = getattr(EventDispatcherHandlerBuilder, "_fmp_orig_register", None)
    if orig is None:
        cur = EventDispatcherHandlerBuilder.register_p2_card_action_trigger
        if getattr(cur, "_fmp_wrapper", False):
            cur = getattr(cur, "__fmp_orig__", cur)
        orig = cur
        setattr(EventDispatcherHandlerBuilder, "_fmp_orig_register", orig)

    def _patched_register(self, f):
        def _wrapped(data):
            try:
                adapter = getattr(f, "__self__", None)
                event = getattr(data, "event", None)
                action = getattr(event, "action", None)
                value = getattr(action, "value", {}) or {}
                if adapter is not None and isinstance(value, dict):
                    pick = value.get("hermes_model_pick")
                    if isinstance(pick, dict):
                        result = _handle_click(adapter, event, pick)
                        if result is None:
                            try:
                                result = adapter._card_response()
                            except Exception:
                                result = None
                        return result
            except Exception:
                logger.warning("[FeishuModelPicker] lark hook error", exc_info=True)
            return f(data) if callable(f) else None

        _wrapped.__name__ = "hermes_model_picker_card_handler"
        # 2026-10-04 审计修复（联合审计 P1）：向链下游透传适配器引用，
        # 避免下游插件拿不到 __self__ 时把 adapter 解析成 None。
        _wrapped._hermes_adapter = getattr(f, "__self__", None)
        return orig(self, _wrapped)

    _patched_register.__name__ = "register_p2_card_action_trigger"
    _patched_register._fmp_wrapper = True
    _patched_register.__fmp_orig__ = orig
    EventDispatcherHandlerBuilder.register_p2_card_action_trigger = _patched_register
    setattr(EventDispatcherHandlerBuilder, _MARKER_LARK, True)
    setattr(EventDispatcherHandlerBuilder, _STAMP, stamp)
    logger.info("[FeishuModelPicker] lark builder hook installed（代际 %s）", stamp)
    return True


async def send_model_picker(self, chat_id: str, providers: List[dict], current_model: str,
                            current_provider: str, session_key: str, on_model_selected,
                            metadata: Optional[Dict[str, Any]] = None):
    """发送可点选的提供方/模型卡片（替代文字列表）。"""
    from gateway.platforms.base import SendResult
    if not getattr(self, "_client", None):
        return SendResult(success=False, error="Not connected")
    try:
        _purge_stale()
        pid = next(_PID)
        _PICKERS[pid] = {
            "chat_id": chat_id, "message_id": "", "providers": list(providers or []),
            "session_key": session_key, "on_model_selected": on_model_selected,
            "current_model": current_model, "current_provider": current_provider, "ts": time.time(),
        }
        card = _provider_card(pid, list(providers or []), current_model, current_provider, 0)
        response = await self._feishu_send_with_retry(
            chat_id=chat_id, msg_type="interactive",
            payload=json.dumps(card, ensure_ascii=False), reply_to=None, metadata=metadata)
        result = self._finalize_send_result(response, "send model picker failed")
        if result.success:
            _PICKERS[pid]["message_id"] = str(result.message_id or "")
            logger.info("[FeishuModelPicker] sent pid=%s card message_id=%r",
                           pid, _PICKERS[pid]["message_id"])
        else:
            _PICKERS.pop(pid, None)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("[FeishuModelPicker] send failed: %s", exc)
        return SendResult(success=False, error=str(exc))


def _install(fa_mod) -> bool:
    adapter_cls = getattr(fa_mod, "FeishuAdapter", None)
    if adapter_cls is None:
        return False
    stamp = _stamp_value()
    if getattr(adapter_cls, _MARKER, False) and getattr(adapter_cls, _STAMP, None) == stamp:
        return True
    # 原始方法只记一次：本插件自己的补丁层绝不叠加（否则每次重载多包一层）
    orig = getattr(adapter_cls, "_fmp_orig_trigger", None)
    if orig is None:
        cur = adapter_cls._on_card_action_trigger
        if getattr(cur, "_fmp_wrapper", False):
            cur = getattr(cur, "__fmp_orig__", cur)
        orig = cur
        adapter_cls._fmp_orig_trigger = orig

    def _patched_trigger(self, data):
        try:
            event = getattr(data, "event", None)
            action = getattr(event, "action", None)
            value = getattr(action, "value", {}) or {}
            if isinstance(value, dict):
                pick = value.get("hermes_model_pick")
                if isinstance(pick, dict):
                    return _handle_click(self, event, pick)
        except Exception:
            logger.warning("[FeishuModelPicker] trigger wrapper error", exc_info=True)
        return orig(self, data)

    _patched_trigger.__name__ = "_on_card_action_trigger"
    _patched_trigger._fmp_wrapper = True
    _patched_trigger.__fmp_orig__ = orig
    adapter_cls._on_card_action_trigger = _patched_trigger
    adapter_cls.send_model_picker = send_model_picker
    setattr(adapter_cls, _MARKER, True)
    setattr(adapter_cls, _STAMP, stamp)
    logger.info("[FeishuModelPicker] installed into %s（代际 %s）",
                   getattr(fa_mod, "__name__", "?"), stamp)
    return True


def _find_adapter_module():
    for name, mod in list(sys.modules.items()):
        if isinstance(name, str) and name.endswith("feishu.adapter") and hasattr(mod, "FeishuAdapter"):
            return mod
    return None


def _try_install() -> bool:
    lark_ok = _install_lark_builder_hook()
    mod = _find_adapter_module()
    class_ok = _install(mod) if mod is not None else False
    return bool(lark_ok and class_ok)


# ── 守护线程：交班给 keeper（唯一一条、跨代存活、每轮跑最新代代码）──────

# 停止标志：退化路径（keeper.py 缺失）与「请上一代退出」用；正常路径由 keeper 管线程。
_STOP = False
# 已退役标志：置位后本代不再干活（双保险，防"该退的还在跑"）。
_RETIRED = False
# 启动初期快速轮询窗口（每代重置；等价于旧实现里 _watch 的局部变量 fast_until）
_FAST_UNTIL = time.time() + 300.0


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

    由 keeper 的 watch_loop 每轮调用 → 因此**永远执行最新一代的代码**；本模块被替换时
    keeper 会自我让位，旧代不会再被调用（不需要任何异常注入）。
    """
    if _RETIRED:
        return _TICK_SLOW
    try:
        ok = _try_install()
        return _TICK_FAST if (not ok or time.time() < _FAST_UNTIL) else _TICK_SLOW
    except Exception:
        logger.debug("[FeishuModelPicker] watcher 单轮异常", exc_info=True)
        return 2.0


def _watcher_diag() -> str:
    """诊断串：watcher / 看门狗存活 + 看门狗拉起次数 + 退出原因。"""
    k = _keeper_module()
    if k is None:
        return "%d(fallback)" % sum(
            1 for t in threading.enumerate() if t.name == "feishu-model-picker")
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
    """请「keeper 之前的老式 _watch 线程」退出（一次性迁移路径）。

    keeper 出现后，新一代线程的 target 在 keeper 模块里（``watch_loop``），**不会**被这里
    匹配到 —— 正常情况下本函数找不到任何线程、什么都不做。

    旧版 ``_watch`` 是 ``while True`` 且不认任何标志 → 只能靠注入 SystemExit 或重启网关
    收掉。本函数**只置标志、不注入**：注入会被网关的 threading.excepthook 记成
    ``[gateway-crash]``，等于凭空制造假崩溃记录（与本次改造的初衷相悖）。因此这些老线程
    会继续每 10 秒空转一次（它们看到粘性标记后不会重装 hook，无害），但**不再增长**；
    重启网关即彻底清零。
    """
    me = threading.current_thread()
    legacy: List[Any] = []
    for t in threading.enumerate():
        if t is me or not t.is_alive():
            continue
        tgt = getattr(t, "_target", None)
        if tgt is None or tgt is _watch:
            continue
        if getattr(tgt, "__module__", "") != __name__ or "watch" not in getattr(tgt, "__qualname__", ""):
            continue
        g = getattr(tgt, "__globals__", None)
        if isinstance(g, dict):
            g["_STOP"] = True      # 认标志的旧版（本改造之后的老版本）会自己退出
            g["_RETIRED"] = True
        legacy.append(t)
    if legacy:
        logger.warning("[FeishuModelPicker] 发现 %d 个 keeper 之前的老式守护线程："
                       "不认停止标志，只能等网关重启；本次不注入异常以免产生假崩溃记录",
                       len(legacy))


def _boot_keeper(ctx) -> None:
    """把守护线程交给 keeper：交班 + 注册代际感知的卸载钩子。

    正常收尾用官方 ``ctx.on_unload``（卸载/禁用/强制重载都会跑）；keeper 的自我让位检查
    是双保险 —— 即使钩子没跑到，线程也不会变成僵尸，更不会被注入异常。
    """
    k = _keeper_module()
    if k is None:
        # 退化路径：插件自带线程（仍不注入异常、仍认 _STOP）
        try:
            threading.Thread(target=_watch, name="feishu-model-picker", daemon=True).start()
        except Exception:
            logger.warning("[FeishuModelPicker] 退化守护线程启动失败", exc_info=True)
        return
    token = k.boot(sys.modules[__name__])
    try:
        ctx.on_unload(lambda: k.request_stop(token))
    except Exception:
        logger.debug("[FeishuModelPicker] on_unload 注册失败（keeper 自我让位仍会兜住）", exc_info=True)


# ── 插件入口 ────────────────────────────────────────────

def register(ctx) -> None:  # noqa: ARG001  (loader 约定: register(ctx))
    try:
        _retire_legacy_threads()
    except Exception:
        pass
    # 先交班给 keeper（唯一一条 watcher 线程跨代存活，每轮执行最新一代的代码），
    # 再装补丁 —— 这样补丁代际戳与本代 token 一致，不会白装两遍。
    try:
        _boot_keeper(ctx)
    except Exception:
        logger.warning("[FeishuModelPicker] keeper 交班失败", exc_info=True)
    try:
        _try_install()
    except Exception:
        logger.warning("[FeishuModelPicker] initial install failed", exc_info=True)
    logger.info("[FeishuModelPicker] registered; watcher=%s", _watcher_diag())
