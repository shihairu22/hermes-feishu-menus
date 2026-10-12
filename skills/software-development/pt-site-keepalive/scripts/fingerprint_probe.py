#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""浏览器环境指纹自检 —— 登录/签到被 Cloudflare 挡住时，先跑这个。

为什么要跑：Turnstile 的信任分含浏览器环境层。Playwright 驱动的 Chrome 默认
`navigator.webdriver=true` 且 WebGL 渲染器是 `SwiftShader Device`（虚拟机/无头特征），
在这种环境下换多少种点击方式都过不了。先用本脚本确认环境是否干净，再决定是否值得继续。

用法（必须用装了 camoufox 的解释器）：
    cd /tmp && ~/.pt-sessions/venv/bin/python \
        fingerprint_probe.py

判读标准：
    ✅ 好：webdriver=false，renderer = ANGLE (NVIDIA/Intel/AMD ...) 这类真实 GPU，UA 是真实浏览器
    ❌ 差：webdriver=true，或 renderer 含 SwiftShader / 缺失 / 通用值
"""
import json
import time

PROBE = """() => {
  const out = {ua: navigator.userAgent, webdriver: navigator.webdriver,
               languages: navigator.languages, hardware_concurrency: navigator.hardwareConcurrency};
  try {
    const gl = document.createElement('canvas').getContext('webgl')
            || document.createElement('canvas').getContext('experimental-webgl');
    if (!gl) { out.webgl = false; return out; }
    out.webgl = true;
    out.gl_version = gl.getParameter(gl.VERSION);
    out.gl_vendor = gl.getParameter(gl.VENDOR);
    out.gl_renderer = gl.getParameter(gl.RENDERER);
    const dbg = gl.getExtension('WEBGL_debug_renderer_info');
    if (dbg) {
      out.unmasked_vendor = gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL);
      out.unmasked_renderer = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL);
    } else { out.debug_renderer_info = 'MISSING'; }
    out.extensions = (gl.getSupportedExtensions() || []).length;
  } catch (e) { out.webgl_error = String(e).slice(0, 120); }
  try { out.webgl2 = !!document.createElement('canvas').getContext('webgl2'); } catch (e) {}
  out.audio = typeof AudioContext !== 'undefined' || typeof webkitAudioContext !== 'undefined';
  out.media_devices = !!(navigator.mediaDevices && navigator.mediaDevices.enumerateDevices);
  out.bluetooth = !!navigator.bluetooth;
  return out;
}"""


def verdict(rec):
    """给出直白的好坏判定，方便一眼看懂。"""
    flags = []
    if rec.get("webdriver") is True:
        flags.append("❌ navigator.webdriver=true（自动化标记）")
    r = (rec.get("unmasked_renderer") or rec.get("gl_renderer") or "").lower()
    if "swiftshader" in r:
        flags.append("❌ WebGL 渲染器是 SwiftShader（软件渲染 / 虚拟机特征）")
    elif not r:
        flags.append("❌ WebGL 渲染器缺失")
    if rec.get("media_devices") is False:
        flags.append("⚠️ navigator.mediaDevices 缺失（无摄像头/麦克风环境）")
    ua = rec.get("ua", "")
    if "Headless" in ua:
        flags.append("❌ UA 含 Headless 标识")
    return flags or ["✅ 环境干净"]


results = {}

# --- 1) Playwright 驱动的 Chrome ---
try:
    from playwright.sync_api import sync_playwright

    for label, args in (("Chrome 默认", ["--no-sandbox", "--disable-dev-shm-usage"]),
                        ("Chrome --disable-gpu", ["--no-sandbox", "--disable-dev-shm-usage",
                                                  "--disable-gpu"])):
        try:
            with sync_playwright() as pw:
                b = pw.chromium.launch(channel="chrome", headless=True, args=args)
                p = b.new_page()
                p.goto("about:blank")
                time.sleep(1)
                results[label] = p.evaluate(PROBE)
                b.close()
        except Exception as exc:  # noqa: BLE001
            results[label] = {"error": f"{type(exc).__name__}: {exc}"[:180]}
except Exception as exc:  # noqa: BLE001
    results["Chrome"] = {"error": f"playwright 不可用: {exc}"[:180]}

# --- 2) Camoufox（Firefox 内核，反检测）---
try:
    from camoufox.sync_api import Camoufox

    for label, kw in (("Camoufox headless", {"headless": True}),
                      ("Camoufox headed", {"headless": False})):
        try:
            with Camoufox(os="windows", humanize=True, **kw) as browser:
                p = browser.new_page()
                p.goto("about:blank")
                time.sleep(1)
                results[label] = p.evaluate(PROBE)
        except Exception as exc:  # noqa: BLE001
            results[label] = {"error": f"{type(exc).__name__}: {exc}"[:180]}
except Exception as exc:  # noqa: BLE001
    results["Camoufox"] = {"error": f"camoufox 不可用: {exc}"[:180]}

# --- 汇总 ---
for label, rec in results.items():
    print(f"\n【{label}】")
    if "error" in rec:
        print("  " + rec["error"])
        continue
    print(f"  webdriver = {rec.get('webdriver')}   webgl = {rec.get('webgl')} "
          f"webgl2 = {rec.get('webgl2')}   扩展 = {rec.get('extensions')}")
    print(f"  renderer  = {rec.get('unmasked_renderer') or rec.get('gl_renderer')}")
    print(f"  ua        = {rec.get('ua')}")
    print(f"  mediaDevices = {rec.get('media_devices')}   audio = {rec.get('audio')}")
    for f in verdict(rec):
        print("  " + f)

print("\n" + json.dumps(results, ensure_ascii=False, indent=2))
