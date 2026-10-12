#!/usr/bin/env python3
"""查两个「投资型」玩法（只读）：
  A1. 织梦 银行/借贷 —— 存款生息？
  A2. UBits 勋章 —— +5% U币 的回本周期
"""
import os  # 家目录展开（去敏时可移植化）
from camoufox.sync_api import Camoufox

JOBS = [
    ('织梦银行', os.path.expanduser('~/.pt-sessions/zm-session'), [
        ('银行', 'https://zmpt.cc/bank.php'),
        ('借贷', 'https://zmpt.cc/loan.php'),
        ('幸运抽奖', 'https://zmpt.cc/plugin/lucky-draw'),
        ('游戏', 'https://zmpt.cc/game.php'),
    ]),
    ('UBits勋章', os.path.expanduser('~/.pt-sessions/ubits-login-session'), [
        ('勋章商城', 'https://ubits.club/medal.php'),
        ('魔力/加成说明', 'https://ubits.club/mybonus.php'),
    ]),
]

for name, prof, pages in JOBS:
    print('=' * 62)
    print('【%s】' % name, flush=True)
    try:
        with Camoufox(headless=False, os="windows", humanize=True,
                      persistent_context=True, user_data_dir=prof) as browser:
            page = browser.new_page()
            for label, url in pages:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(4500)
                    body = ' '.join(page.evaluate('() => document.body.innerText').split())
                    print()
                    print('  ── %s ──' % label)
                    print('     %s' % page.title()[:70])
                    # 打印除用户栏外的正文（跳过前 200 字的导航栏）
                    print('     %s' % body[200:900])
                except Exception as exc:
                    print()
                    print('  ── %s ── ✗ %s' % (label, str(exc)[:90]))
    except Exception as exc:
        print('  ✗ 浏览器异常: %s' % str(exc)[:100])
