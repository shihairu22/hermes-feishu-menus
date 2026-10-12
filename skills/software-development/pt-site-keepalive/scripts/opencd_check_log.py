#!/usr/bin/env python3
"""OpenCD 签到记录页只读核查（定案「今天签没签」）。

用持久档案打开 plugin_sign-in.php?cmd=show-log，dump 正文 + 最新记录行。
只读：不触发任何签到动作。裁决规则（见 references/opencd.md）：
记录页出现当天日期 = 最硬判据；state=false / 魔力值不变都可能与
「当天已签过」共存 —— 不要因此重复补签。

用法：
  env -u http_proxy -u https_proxy -u all_proxy xvfb-run -a \
      ~/.pt-sessions/venv/bin/python \
      opencd_check_log.py
解释器用 camoufox venv（需要 Camoufox；PIL 不需要）。
"""
import os  # 家目录展开（去敏时可移植化）
import re
import time

from camoufox.sync_api import Camoufox

PROFILE = os.path.expanduser("~/.pt-sessions/opencd-login-session")
URL = "https://www.open.cd/plugin_sign-in.php?cmd=show-log"

with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=PROFILE, locale="zh-CN") as browser:
    page = browser.new_page()
    page.set_default_timeout(60000)
    page.goto(URL, wait_until="domcontentloaded")
    time.sleep(4)
    print(re.sub(r"\s+", " ", page.inner_text("body"))[:2000])
    rows = page.evaluate(
        "() => [...document.querySelectorAll('tr')].map(r => r.innerText.replace(/\\s+/g,' ').trim()).slice(0, 12)"
    )
    print("=== ROWS ===")
    for r in rows:
        print(r[:200])
