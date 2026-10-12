#!/usr/bin/env python3
"""用浏览器（已有登录档案）过 CF，识别被遮蔽站点的真实框架。

对每个站：打开首页 → 读 title / HTML 特征 / 引用的 JS / cookie 名 → 判定框架。
只读，不做任何登录或签到动作。
"""
import os  # 家目录展开（去敏时可移植化）
import re

from camoufox.sync_api import Camoufox

SITES = [
    ('Audiences',    os.path.expanduser('~/.pt-sessions/audiences-login-session'),    'https://audiences.me/index.php'),
    ('OurBits',      os.path.expanduser('~/.pt-sessions/ourbits-login-session'),      'https://ourbits.club/index.php'),
    ('KEEPFRDS',     os.path.expanduser('~/.pt-sessions/keepfrds-login-session'),     'https://pt.keepfrds.com/'),
    ('PigGo',        os.path.expanduser('~/.pt-sessions/piggo-login-session'),        'https://piggo.me/index.php'),
    ('UBits',        os.path.expanduser('~/.pt-sessions/ubits-login-session'),        'https://ubits.club/index.php'),
    ('HDDolby',      os.path.expanduser('~/.pt-sessions/hddolby-login-session'),      'https://www.hddolby.com/index.php'),
    ('TTG',          os.path.expanduser('~/.pt-sessions/ttg-login-session'),          'https://totheglory.im/index.php'),
    ('PTHOME',       os.path.expanduser('~/.pt-sessions/pthome-login-session'),       'https://www.pthome.net/index.php'),
    ('织梦',          os.path.expanduser('~/.pt-sessions/zm-session'),                 'https://zmpt.cc/index.php'),
    ('OpenCD',       os.path.expanduser('~/.pt-sessions/opencd-login-session'),       'https://www.open.cd/index.php'),
    ('U2',           os.path.expanduser('~/.pt-sessions/u2-login-session'),           'https://u2.dmhy.org/index.php'),
    
]

MARKERS = [
    (r'Powered by NexusPHP', 'NexusPHP'),
    (r'Powered by mTorrent', 'mTorrent（自研 React）'),
    (r'Powered [Bb]y TNode', 'TNode（Vue SPA）'),
    (r'Powered by Discuz', 'Discuz!'),
    (r'UNIT3D', 'UNIT3D (Laravel)'),
    (r'Nexus Project', 'Nexus Project'),
    (r'Powered by .{0,24}Nexus', 'NexusPHP 分支'),
    (r'Powered by .{0,24}PT', 'NexusPHP 变体'),
]

for name, prof, url in SITES:
    print('===== %s =====' % name, flush=True)
    try:
        with Camoufox(headless=False, os="windows", humanize=True,
                      persistent_context=True, user_data_dir=prof) as browser:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(7000)
            html = page.content()
            title = re.sub(r'\s+', ' ', page.title())[:60]
            print('  URL: %s' % page.url[:70], flush=True)
            print('  title: %s' % title, flush=True)
            fw = next((n for p, n in MARKERS if re.search(p, html, re.I)), '')
            if not fw:
                m = re.search(r'Powered\s+by\s+([^<\n]{2,30})', html, re.I)
                if m:
                    fw = 'Powered by %s' % m.group(1).strip()[:24]
            print('  框架: %s' % (fw or '（仍未识别）'), flush=True)
            # cookie 名
            try:
                cks = browser.cookies()
                names = sorted({c['name'] for c in cks if 'dmhy' not in c.get('domain', '')})[:8]
                print('  cookie: %s' % ','.join(names), flush=True)
            except Exception as exc:
                print('  cookie 读取失败: %s' % str(exc)[:60], flush=True)
            # JS 引用
            js = re.findall(r'<script[^>]*src=["\']([^"\']+)', html, re.I)
            key = [j.split('/')[-1][:30] for j in js if any(
                k in j.lower() for k in ('crypto', 'vue', 'react', 'antd', 'layui',
                                         'bootstrap', 'jquery', 'app', 'main'))][:6]
            print('  JS: %s' % (','.join(key) or '—'), flush=True)
    except Exception as exc:
        print('  ❌ 异常: %s' % str(exc)[:100], flush=True)
    print(flush=True)
