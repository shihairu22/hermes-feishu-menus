#!/usr/bin/env python3
# -*- coding: utf-8
"""飞书模型选择器插件——离线自测（卡片构建/点击路由/补丁机制/三参回调）。

用法：python3 feishu-model-picker-selftest.py [插件__init__.py路径]
默认从 ~/.hermes/plugins/feishu-model-picker/__init__.py 加载（可用 HERMES_HOME 覆盖）。
"""
import importlib.util
import json
import os
import sys
import time
import types

PLUGIN = (sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")),
    "plugins", "feishu-model-picker", "__init__.py"))
if not os.path.exists(PLUGIN):
    sys.exit("找不到插件文件: %s（可传参或设置 HERMES_HOME）" % PLUGIN)

spec = importlib.util.spec_from_file_location("fmp", PLUGIN)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

providers = [
    {"slug": "custom", "label": "custom",
     "models": ["vendor-a:model-x", "vendor-b:model-y"] + ["m%d" % i for i in range(25)],
     "is_current": True, "total_models": 27},
    {"slug": "gemini", "label": "Google AI Studio",
     "models": ["gemini-flash-latest", "gemini-2.5-flash-lite"] + ["g%d" % i for i in range(13)],
     "is_current": False, "total_models": 15},
]
CUR = "vendor-a:model-x"

# ── 结构兼容助手：1.0（顶层 elements）/ 2.0（body.elements）+ behaviors 里的回调值 ──
def _els(card):
    """卡片元素列表，兼容 1.0 顶层 elements 与 2.0 body.elements。"""
    if isinstance(card.get("elements"), list):
        return card["elements"]
    return (card.get("body") or {}).get("elements") or []


def _find(node, pred):
    if isinstance(node, dict):
        if pred(node):
            return node
        for v in node.values():
            r = _find(v, pred)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node:
            r = _find(v, pred)
            if r is not None:
                return r
    return None


def _pick_value(node):
    """节点上的 hermes_model_pick 回调值（兼容 1.0 的 value 与 2.0 的 behaviors）。"""
    v = node.get("value")
    if isinstance(v, dict) and "hermes_model_pick" in v:
        return v["hermes_model_pick"]
    for b in (node.get("behaviors") or []):
        v = (b or {}).get("value") or {}
        if "hermes_model_pick" in v:
            return v["hermes_model_pick"]
    return None


def _pick_button(card, action=None):
    """首个带 hermes_model_pick 回调的按钮元素（可选按 a 字段过滤）。"""
    def pred(n):
        pv = _pick_value(n) if isinstance(n, dict) else None
        return bool(pv) and (action is None or pv.get("a") == action)
    return _find(card, pred)


# ① 卡片构建
c1 = m._provider_card(1, providers, CUR, "custom")
c2 = m._models_card(1, {"providers": providers, "current_model": CUR,
                        "current_provider": "custom"}, 0, 0)
json.dumps(c1, ensure_ascii=False)
json.dumps(c2, ensure_ascii=False)
a0 = _pick_button(c1, "p")
assert a0 is not None, "provider 卡未找到带 hermes_model_pick 的按钮"
assert _pick_value(a0)["a"] == "p"
assert "✓" in a0["text"]["content"]
assert "第 1/3 页" in _els(c2)[0]["content"]
print("① 卡片构建 OK：provider", len(json.dumps(c1, ensure_ascii=False)), "B / models",
      len(json.dumps(c2, ensure_ascii=False)), "B")

# ② 点击路由（桩适配器）
class StubAdapter:
    _loop = object()
    def _loop_accepts_callbacks(self, loop): return True
    def _card_response(self, card=None): return {"card": card}
    def _is_interactive_operator_authorized(self, o): return True
    def _submit_on_loop(self, loop, coro):
        if hasattr(coro, "close"):
            coro.close()
        return True

sa = StubAdapter()
ev = types.SimpleNamespace(operator=types.SimpleNamespace(open_id="ou_x"))

r = m._handle_click(sa, ev, {"a": "m", "pid": 999, "i": 0, "mi": 0})
assert "过期" in json.dumps(r["card"], ensure_ascii=False)
print("② 过期态 OK")

m._PICKERS[7] = {"chat_id": "c", "message_id": "mid", "providers": providers,
                 "current_model": "x", "current_provider": "custom",
                 "on_model_selected": None, "ts": time.time()}
r2 = m._handle_click(sa, ev, {"a": "p", "pid": 7, "i": 1})
assert "Google AI Studio" in json.dumps(r2["card"], ensure_ascii=False)
r3 = m._handle_click(sa, ev, {"a": "pg", "pid": 7, "i": 1, "pg": 1})
assert "第 2/2 页" in json.dumps(r3["card"], ensure_ascii=False)
r4 = m._handle_click(sa, ev, {"a": "b", "pid": 7})
assert "选择提供方" in json.dumps(r4["card"], ensure_ascii=False)
m._PICKERS[8] = dict(m._PICKERS[7], message_id="")
r6 = m._handle_click(sa, ev, {"a": "m", "pid": 8, "i": 1, "mi": 0})
assert "正在切换" in json.dumps(r6["card"], ensure_ascii=False)
r5 = m._handle_click(sa, ev, {"a": "x", "pid": 7})
assert "取消" in json.dumps(r5["card"], ensure_ascii=False)
print("③ 下钻/翻页/返回/选择/取消 OK")

# ④ 补丁机制（假模块）
class FakeAdapter:
    def _on_card_action_trigger(self, data):
        return "ORIG:" + str(data)

class FakeMod:
    __name__ = "fake.feishu.adapter"
    FeishuAdapter = FakeAdapter

assert m._install(FakeMod) is True
assert getattr(FakeAdapter, "_hermes_feishu_model_picker_installed", False)
assert FakeAdapter()._on_card_action_trigger({"x": 1}) == "ORIG:{'x': 1}"
assert m._install(FakeMod) is True  # 幂等
print("④ 补丁安装 + 普通动作透传 OK")

# ⑤ JSON 全序列化检查
print("⑤ 全部卡片 JSON 序列化 OK")

# ⑥ lark 构建器拦截（注入假 lark 模块）
import sys as _sys

fake_pkg = types.ModuleType("lark_oapi")
fake_ev = types.ModuleType("lark_oapi.event")
fake_dh = types.ModuleType("lark_oapi.event.dispatcher_handler")

class FakeBuilder:
    def __init__(self):
        self.map = {}
    def register_p2_card_action_trigger(self, f):
        assert "p2.card.action.trigger" not in self.map
        self.map["p2.card.action.trigger"] = f
        return self

fake_dh.EventDispatcherHandlerBuilder = FakeBuilder
fake_pkg.event = fake_ev
_sys.modules["lark_oapi"] = fake_pkg
_sys.modules["lark_oapi.event"] = fake_ev
_sys.modules["lark_oapi.event.dispatcher_handler"] = fake_dh

assert m._install_lark_builder_hook() is True

class RealishAdapter(StubAdapter):
    def _on_card_action_trigger(self, data):
        return {"orig": data}

ra = RealishAdapter()
b = FakeBuilder()
b.register_p2_card_action_trigger(ra._on_card_action_trigger)
handler = b.map["p2.card.action.trigger"]

class D:
    pass

d1 = D(); ev1 = D(); act1 = D(); act1.value = {"foo": 1}; ev1.action = act1; d1.event = ev1
r = handler(d1)
assert r == {"orig": d1}, r

m._PICKERS.clear()
act2 = D(); act2.value = {"hermes_model_pick": {"a": "p", "pid": 12345, "i": 0}}
ev2 = D(); ev2.action = act2; ev2.operator = D(); ev2.operator.open_id = "ou_x"
d2 = D(); d2.event = ev2
r2 = handler(d2)
assert "过期" in json.dumps(r2["card"], ensure_ascii=False)
print("⑥ lark 构建器拦截 OK（普通事件透传 / 命中我们的动作）")

# ⑦ 回调三参调用（对齐网关签名 _on_model_selected(chat_id, model_id, provider_slug)）
import asyncio as _aio

calls77 = []

def fake_cb(chat_id, model_id, provider_slug):
    calls77.append((chat_id, model_id, provider_slug))
    return "已切换 OK"

class Stub2:
    _client = None
    async def _feishu_send_with_retry(self, **kw):
        calls77.append(("fallback_sent", kw.get("chat_id")))

m._PICKERS[77] = {"chat_id": "oc_X", "message_id": "", "providers": providers,
                  "current_model": "x", "current_provider": "custom",
                  "on_model_selected": fake_cb, "ts": time.time()}
_aio.run(m._complete_pick(Stub2(), 77, 1, 0))
assert calls77[0] == ("oc_X", "gemini-flash-latest", "gemini"), calls77
print("⑦ 回调三参调用 OK:", calls77[0])

print("== 自测全部通过 ==")
