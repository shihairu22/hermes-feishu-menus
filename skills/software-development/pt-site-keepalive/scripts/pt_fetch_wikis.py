#!/usr/bin/env python3
"""抓取 PT 站的规则 / FAQ / wiki 全文（只读）。

输出：
  ~/safeline-research/wikis/<site>.json  每页原文
  ~/safeline-research/wikis/<site>.md    可读摘要

用法：python3 pt_fetch_wikis.py <批次号>
批次 1-5，每批 5-6 站。
"""
import json
import os
import sys

from camoufox.sync_api import Camoufox

OUTDIR = os.path.expanduser('~/safeline-research/wikis')
os.makedirs(OUTDIR, exist_ok=True)

# (站点, 档案, 域名, [(标签, 路径)])
SITES = [
    ('Audiences', os.path.expanduser('~/.pt-sessions/audiences-login-session'), 'https://audiences.me',
     [('规则', '/rules.php'), ('常见问题', '/faq.php')]),
    ('OurBits', os.path.expanduser('~/.pt-sessions/ourbits-login-session'), 'https://ourbits.club',
     [('规则', '/rules.php'), ('常见问题', '/faq.php')]),
    ('KEEPFRDS', os.path.expanduser('~/.pt-sessions/keepfrds-login-session'), 'https://pt.keepfrds.com',
     [('规则', '/rules.php'), ('FAQ', '/faq.php'), ('帮助Wiki', '/wiki.php')]),
    ('HDSky', os.path.expanduser('~/.pt-sessions/hdsky-login-session'), 'https://hdsky.me',
     [('规则', '/rules.php'), ('常见问题', '/faq.php')]),
    ('PigGo', os.path.expanduser('~/.pt-sessions/piggo-login-session'), 'https://piggo.me',
     [('站点规则', '/zh/%E7%AB%99%E7%82%B9%E8%A7%84%E5%88%99'),
      ('盒子及限速规则', '/zh/%E7%AB%99%E7%82%B9%E8%A7%84%E5%88%99/%E7%9B%92%E5%AD%90%E5%8F%8A%E9%99%90%E9%80%9F%E8%A7%84%E5%88%99')]),

    ('CHDBits', os.path.expanduser('~/.pt-sessions/chdbits-login-session'), 'https://ptchdbits.co',
     [('规则', '/rules.php'), ('常见问题', '/faq.php')]),
    ('UBits', os.path.expanduser('~/.pt-sessions/ubits-login-session'), 'https://ubits.club',
     [('规则', '/rules.php'), ('常见问题', '/faq.php')]),
    ('HDDolby', os.path.expanduser('~/.pt-sessions/hddolby-login-session'), 'https://www.hddolby.com',
     [('规则', '/rules.php'), ('常见问题', '/faq.php')]),
    ('TTG', os.path.expanduser('~/.pt-sessions/ttg-login-session'), 'https://totheglory.im',
     [('规则', '/rules.php'), ('FAQ', '/faq.php')]),
    ('HDHome', os.path.expanduser('~/.pt-sessions/hdhome-login-session'), 'https://hdhome.org',
     [('规则', '/rules.php'), ('常见问题', '/faq.php')]),

    ('OpenCD', os.path.expanduser('~/.pt-sessions/opencd-login-session'), 'https://www.open.cd',
     [('百科Wiki', '/wiki.php'), ('规则', '/rules.php'), ('常见问题', '/faq.php')]),
    ('U2', os.path.expanduser('~/.pt-sessions/u2-login-session'), 'https://u2.dmhy.org',
     [('规则', '/rules.php'), ('常见问题', '/faq.php')]),
    ('PTHOME', os.path.expanduser('~/.pt-sessions/pthome-login-session'), 'https://www.pthome.net',
     [('规则', '/rules.php'), ('常见问题', '/faq.php')]),
    ('HDU', os.path.expanduser('~/.pt-sessions/hdu-login-session'), 'https://pt.hdupt.com',
     [('规则', '/rules.php'), ('常见问题', '/faq.php')]),
    ('大青虫', os.path.expanduser('~/.pt-sessions/bug-login-session'), 'https://cyanbug.net',
     [('网站规则', '/rules.php'), ('常见问题', '/faq.php')]),

    ('织梦', os.path.expanduser('~/.pt-sessions/zm-session'), 'https://zmpt.cc',
     [('训练家手册', '/rules.php'), ('常见问题', '/faq.php')]),
    ('DiscFan', os.path.expanduser('~/.pt-sessions/df-login-session'), 'https://discfan.net',
     [('规则', '/rules.php'), ('常见问题', '/faq.php')]),
    ('海棠PT', os.path.expanduser('~/.pt-sessions/ht-session'), 'https://www.htpt.cc',
     [('规则', '/rules.php'), ('常见问题', '/faq.php')]),
    ('天雪', os.path.expanduser('~/.pt-sessions/skyey-login-session'), 'https://www.skyey2.com',
     [('快速帮助', '/help/')]),
    ('MonikaDesign', os.path.expanduser('~/.pt-sessions/monika-login-session'), 'https://monikadesign.uk',
     [('规则', '/pages/1'), ('帮助台', '/tickets')]),
]

BATCH = int(sys.argv[1]) if len(sys.argv) > 1 else 1
GROUP = SITES[BATCH - 1]

name, prof, host, pages = GROUP
print('=== 批次 %d：【%s】%d 页 ===' % (BATCH, name, len(pages)), flush=True)

res = {}
try:
    with Camoufox(headless=False, os="windows", humanize=True,
                  persistent_context=True, user_data_dir=prof) as browser:
        page = browser.new_page()
        for label, path in pages:
            url = host + path
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=75000)
                page.wait_for_timeout(4000)
                body = ' '.join(page.evaluate('() => document.body.innerText').split())
                res[label] = {'url': url, 'title': page.title()[:80], 'text': body}
                print('  [✓] %-12s %d 字 | %s' % (label, len(body), page.title()[:50]))
            except Exception as exc:
                res[label] = {'url': url, 'error': str(exc)[:120]}
                print('  [✗] %-12s %s' % (label, str(exc)[:80]))
except Exception as exc:
    print('  [✗] 浏览器异常: %s' % str(exc)[:120])

json.dump(res, open('%s/%s.json' % (OUTDIR, name), 'w'), ensure_ascii=False, indent=1)
print('  已落盘 %s/%s.json' % (OUTDIR, name))
