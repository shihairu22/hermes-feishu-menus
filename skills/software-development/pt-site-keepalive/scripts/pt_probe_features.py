#!/usr/bin/env python3
"""读取各站「免费收益」页面的真实内容（只读，绝不点击任何按钮）。

目标页：红包 / 转盘 / 任务 / fun.php / 趣味页
用法：python3 pt_probe_features.py <批次>
"""
import os  # 家目录展开（去敏时可移植化）
import json
import sys

from camoufox.sync_api import Camoufox

OUT = os.path.expanduser('~/safeline-research/pt_feature_pages.json')

# (站点, 档案, [(页面名, URL)])
TARGETS = [
    ('UBits', os.path.expanduser('~/.pt-sessions/ubits-login-session'), [
        ('红包', 'https://ubits.club/redpacket.php'),
        ('转盘', 'https://ubits.club/wof.php'),
        ('趣味页', 'https://ubits.club/fun.php'),
        ('勋章', 'https://ubits.club/medal.php'),
    ]),
    ('HDSky', os.path.expanduser('~/.pt-sessions/hdsky-login-session'), [
        ('趣味页', 'https://hdsky.me/fun.php'),
    ]),
    ('PTHOME', os.path.expanduser('~/.pt-sessions/pthome-login-session'), [
        ('趣味页', 'https://www.pthome.net/fun.php'),
        ('认领', 'https://www.pthome.net/claim.php'),
    ]),
    ('大青虫', os.path.expanduser('~/.pt-sessions/bug-login-session'), [
        ('趣味页', 'https://cyanbug.net/fun.php'),
        ('任务', 'https://cyanbug.net/task.php'),
        ('勋章', 'https://cyanbug.net/medal.php'),
    ]),
    ('HDU', os.path.expanduser('~/.pt-sessions/hdu-login-session'), [
        ('趣味页', 'https://pt.hdupt.com/fun.php'),
    ]),
    ('织梦', os.path.expanduser('~/.pt-sessions/zm-session'), [
        ('游戏', 'https://zmpt.cc/game.php'),
        ('幸运抽奖', 'https://zmpt.cc/plugin/lucky-draw'),
        ('任务', 'https://zmpt.cc/task.php'),
    ]),
    ('PigGo', os.path.expanduser('~/.pt-sessions/piggo-login-session'), [
        ('任务', 'https://piggo.me/task.php'),
        ('勋章', 'https://piggo.me/medal.php'),
        ('特殊', 'https://piggo.me/special.php'),
    ]),
]

BATCH = int(sys.argv[1]) if len(sys.argv) > 1 else 1
GROUP = TARGETS[BATCH - 1]
name, prof, pages = GROUP

try:
    out = json.load(open(OUT))
except Exception:
    out = {}

print('=== %s（%d 个页面）===' % (name, len(pages)), flush=True)
res = {}
with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=prof) as browser:
    page = browser.new_page()
    for label, url in pages:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4500)
            body = page.evaluate('() => document.body.innerText')
            body = ' '.join(body.split())
            title = page.title()[:60]
            res[label] = {'url': url, 'title': title, 'text': body[:900]}
            print()
            print('  ── %s ──' % label)
            print('     %s' % title)
            print('     %s' % body[:420])
        except Exception as exc:
            res[label] = {'url': url, 'error': str(exc)[:120]}
            print()
            print('  ── %s ── ✗ %s' % (label, str(exc)[:90]))

out[name] = res
json.dump(out, open(OUT, 'w'), ensure_ascii=False, indent=1)
print()
print('已落盘 %s' % OUT)
