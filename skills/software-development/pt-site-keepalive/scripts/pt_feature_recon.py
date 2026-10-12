#!/usr/bin/env python3
"""PT 站「隐藏玩法」侦察 —— 第 1 步：抓取各站首页的完整导航链接。

原理：朱雀的抽卡/技能/竞猜都是导航里的入口。同理，
      把每站的首页链接全抓下来，与标准 NexusPHP 菜单对比，
      多出来的条目就是该站独有的玩法。

用法：python3 pt_feature_recon.py <批次号>
      批次 1 = 前 8 站，批次 2 = 中 8 站，批次 3 = 后 8 站
输出：追加写入 ~/safeline-research/pt_features.json
"""
import json
import os
import re
import sys

from camoufox.sync_api import Camoufox

OUT = os.path.expanduser('~/safeline-research/pt_features.json')

SITES = [
    # (显示名, 浏览器档案, 首页 URL)
    ('M-Team',        os.path.expanduser('~/.pt-sessions/mteam-session'),        'https://kp.m-team.cc/index'),
    ('Audiences',     os.path.expanduser('~/.pt-sessions/audiences-login-session'), 'https://audiences.me/index.php'),
    ('OurBits',       os.path.expanduser('~/.pt-sessions/ourbits-login-session'), 'https://ourbits.club/index.php'),
    ('KEEPFRDS',      os.path.expanduser('~/.pt-sessions/keepfrds-login-session'), 'https://pt.keepfrds.com/index.php'),
    ('HDSky',         os.path.expanduser('~/.pt-sessions/hdsky-login-session'),  'https://hdsky.me/index.php'),
    ('PigGo',         os.path.expanduser('~/.pt-sessions/piggo-login-session'),  'https://piggo.me/index.php'),
    ('CHDBits',       os.path.expanduser('~/.pt-sessions/chdbits-login-session'), 'https://ptchdbits.co/index.php'),
    ('UBits',         os.path.expanduser('~/.pt-sessions/ubits-login-session'),  'https://ubits.club/index.php'),
    ('HDDolby',       os.path.expanduser('~/.pt-sessions/hddolby-login-session'), 'https://www.hddolby.com/index.php'),
    ('TTG',           os.path.expanduser('~/.pt-sessions/ttg-login-session'),    'https://totheglory.im/index.php'),
    ('HDHome',        os.path.expanduser('~/.pt-sessions/hdhome-login-session'), 'https://hdhome.org/index.php'),
    ('OpenCD',        os.path.expanduser('~/.pt-sessions/opencd-login-session'), 'https://www.open.cd/index.php'),
    ('U2',            os.path.expanduser('~/.pt-sessions/u2-login-session'),     'https://u2.dmhy.org/index.php'),
    ('天雪',           os.path.expanduser('~/.pt-sessions/skyey-login-session'),  'https://www.skyey2.com/'),
    ('MonikaDesign',  os.path.expanduser('~/.pt-sessions/monika-login-session'), 'https://monikadesign.uk/'),
    ('PTHOME',        os.path.expanduser('~/.pt-sessions/pthome-login-session'), 'https://www.pthome.net/index.php'),
    ('朱雀',           os.path.expanduser('~/.pt-sessions/zhuque-login-session'), 'https://zhuque.in/index'),
    ('HDFans',        None,                                      'https://hdfans.org/index.php'),
    ('HDU',           os.path.expanduser('~/.pt-sessions/hdu-login-session'),    'https://pt.hdupt.com/index.php'),
    ('PANDA',         None,                                      'https://pandapt.net/index.php'),
    ('SJTU葡萄',       None,                                      'https://pt.sjtu.edu.cn/index.php'),
    ('大青虫',         os.path.expanduser('~/.pt-sessions/bug-login-session'),    'https://cyanbug.net/index.php'),
    ('DiscFan',       os.path.expanduser('~/.pt-sessions/df-login-session'),     'https://discfan.net/index.php'),
    ('冬樱',           None,                                      'https://wintersakura.net/index.php'),
    ('织梦',           os.path.expanduser('~/.pt-sessions/zm-session'),           'https://zmpt.cc/index.php'),
    ('海棠PT',         os.path.expanduser('~/.pt-sessions/ht-session'),           'https://www.htpt.cc/index.php'),
    ('SunnyPT',       None,                                      'https://sunnypt.top/'),
]

BATCH = int(sys.argv[1]) if len(sys.argv) > 1 else 1
lo, hi = (BATCH - 1) * 9, BATCH * 9
todo = SITES[lo:hi]

try:
    results = json.load(open(OUT))
except Exception:
    results = {}

print('=== 批次 %d：%d 站（%d~%d）===' % (BATCH, len(todo), lo + 1, hi))
for name, prof, url in todo:
    if not prof or not os.path.isdir(prof):
        print('[跳过] %-14s 无浏览器档案' % name, flush=True)
        continue
    try:
        with Camoufox(headless=False, os="windows", humanize=True,
                      persistent_context=True, user_data_dir=prof) as browser:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(6000)
            links = page.evaluate("""() => Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({h: a.getAttribute('href'), t: (a.innerText||'').trim().slice(0,24)}))
                .filter(x => x.h && x.t)""")
            body = page.evaluate('() => document.body.innerText').replace('\n', ' ')
            results[name] = {
                'url': url,
                'title': page.title()[:80],
                'links': links[:400],
                'logged_in': ('退出' in body) or ('登出' in body) or ('歡迎回來' in body) or ('欢迎回来' in body),
                'text_head': body[:400],
            }
            uniq = sorted({l['h'].split('?')[0] for l in links})
            print('[✓] %-14s 链接 %3d 个（去重 %3d）| 登录态=%s' % (
                name, len(links), len(uniq), results[name]['logged_in']), flush=True)
    except Exception as exc:
        print('[✗] %-14s 异常: %s' % (name, str(exc)[:90]), flush=True)
        results.setdefault(name, {})['error'] = str(exc)[:200]
    json.dump(results, open(OUT, 'w'), ensure_ascii=False, indent=1)

print()
print('已落盘 %s（累计 %d 站）' % (OUT, len(results)))
