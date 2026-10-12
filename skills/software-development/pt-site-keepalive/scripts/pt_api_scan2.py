#!/usr/bin/env python3
"""PT 站 API 扫描器 v2 —— 抓真实网络流量。

做法：用已登录档案打开站点，记录浏览器发出的每个请求（XHR/fetch/document），
再依次访问站内几个关键页面，汇总去重后落盘。

这比「下载 JS 再正则」可靠得多：SPA 的 API 路径是运行时拼的，静态扫描抓不到。

输出：~/safeline-research/apis/<site>.json
用法：python3 pt_api_scan2.py <批次号>     # 每批 3 站
"""
import json
import os
import re
import sys
from collections import defaultdict

from camoufox.sync_api import Camoufox

OUTDIR = os.path.expanduser('~/safeline-research/apis')
os.makedirs(OUTDIR, exist_ok=True)

SITES = [
    ('M-Team', os.path.expanduser('~/.pt-sessions/mteam-session'), 'https://kp.m-team.cc/index'),
    ('OurBits', os.path.expanduser('~/.pt-sessions/ourbits-login-session'), 'https://ourbits.club/index.php'),
    ('朱雀', os.path.expanduser('~/.pt-sessions/zhuque-login-session'), 'https://zhuque.in/index'),
    ('MonikaDesign', os.path.expanduser('~/.pt-sessions/monika-login-session'), 'https://monikadesign.uk/'),
    ('PigGo', os.path.expanduser('~/.pt-sessions/piggo-login-session'), 'https://piggo.me/index.php'),
    ('CHDBits', os.path.expanduser('~/.pt-sessions/chdbits-login-session'), 'https://ptchdbits.co/index.php'),
    ('HDSky', os.path.expanduser('~/.pt-sessions/hdsky-login-session'), 'https://hdsky.me/index.php'),
    ('UBits', os.path.expanduser('~/.pt-sessions/ubits-login-session'), 'https://ubits.club/index.php'),
    ('TTG', os.path.expanduser('~/.pt-sessions/ttg-login-session'), 'https://totheglory.im/index.php'),
    ('HDHome', os.path.expanduser('~/.pt-sessions/hdhome-login-session'), 'https://hdhome.org/index.php'),
    ('OpenCD', os.path.expanduser('~/.pt-sessions/opencd-login-session'), 'https://www.open.cd/index.php'),
    ('PTHOME', os.path.expanduser('~/.pt-sessions/pthome-login-session'), 'https://www.pthome.net/index.php'),
    ('U2', os.path.expanduser('~/.pt-sessions/u2-login-session'), 'https://u2.dmhy.org/index.php'),
    ('HDU', os.path.expanduser('~/.pt-sessions/hdu-login-session'), 'https://pt.hdupt.com/index.php'),
    ('大青虫', os.path.expanduser('~/.pt-sessions/bug-login-session'), 'https://cyanbug.net/index.php'),
    ('织梦', os.path.expanduser('~/.pt-sessions/zm-session'), 'https://zmpt.cc/index.php'),
    ('DiscFan', os.path.expanduser('~/.pt-sessions/df-login-session'), 'https://discfan.net/index.php'),
    ('海棠PT', os.path.expanduser('~/.pt-sessions/ht-session'), 'https://www.htpt.cc/index.php'),
    ('天雪', os.path.expanduser('~/.pt-sessions/skyey-login-session'), 'https://www.skyey2.com/'),
    ('HDDolby', os.path.expanduser('~/.pt-sessions/hddolby-login-session'), 'https://www.hddolby.com/index.php'),
    ('Audiences', os.path.expanduser('~/.pt-sessions/audiences-login-session'), 'https://audiences.me/index.php'),
    ('KEEPFRDS', os.path.expanduser('~/.pt-sessions/keepfrds-login-session'), 'https://pt.keepfrds.com/index.php'),
]

# 这些是「真正的接口」特征
API_HINT = re.compile(r'/(api|apis|api/v\d|ajax|json|graphql|rpc|rest)(/|$|\?)', re.I)
XHR_TYPES = ('xhr', 'fetch')


def scan(site, profile, home):
    res = {'site': site, 'home': home, 'calls': [], 'pages': [],
           'hosts': [], 'assets_js': [], 'fingerprints': [], 'errors': []}
    calls = {}
    hosts = defaultdict(int)
    js_assets = set()

    with Camoufox(headless=False, os="windows", humanize=True,
                  persistent_context=True, user_data_dir=profile) as b:
        page = b.new_page()

        def on_req(req):
            try:
                rt = req.resource_type
                u = req.url
                host = re.sub(r'^https?://([^/]+).*', r'\1', u)
                hosts[host] += 1
                if rt == 'script':
                    js_assets.add(u)
                if rt in XHR_TYPES or API_HINT.search(u):
                    key = (req.method, u.split('#')[0])
                    if key not in calls:
                        calls[key] = {'method': req.method, 'url': u.split('#')[0],
                                      'type': rt,
                                      'post': (req.post_data or '')[:300]}
            except Exception:
                pass

        page.on('request', on_req)

        # 首页
        try:
            page.goto(home, wait_until='networkidle', timeout=80000)
            page.wait_for_timeout(7000)
            res['pages'].append({'url': home, 'title': page.title()[:80]})
        except Exception as exc:
            res['errors'].append('home: ' + str(exc)[:80])

        # 抓站内链接，选几个关键页访问
        try:
            links = page.evaluate('''() => Array.from(document.querySelectorAll('a'))
                .map(a => a.href).filter(h => h && !h.startsWith('javascript'))''')
        except Exception:
            links = []
        base = re.sub(r'^(https?://[^/]+).*', r'\1', home)
        seen, targets = set(), []
        for h in links or []:
            if not h.startswith(base) or h in seen:
                continue
            seen.add(h)
            low = h.lower()
            if any(k in low for k in ('torrent', 'detail', 'user', 'usercp', 'bonus',
                                      'attendance', 'signin', 'sign', 'forum', 'game',
                                      'gaming', 'mall', 'my', 'profile', 'index',
                                      'seed', 'upload', 'rule', 'faq', 'claim', 'task')):
                targets.append(h)
            if len(targets) >= 7:
                break
        for t in targets:
            try:
                page.goto(t, wait_until='domcontentloaded', timeout=60000)
                page.wait_for_timeout(4500)
                res['pages'].append({'url': t, 'title': page.title()[:80]})
            except Exception as exc:
                res['errors'].append('page %s: %s' % (t[:50], str(exc)[:60]))

        # 指纹
        try:
            html = page.content()
        except Exception:
            html = ''
        FPS = {'Spring Boot': r'/actuator|whitelabel|org\.springframework',
               'Laravel': r'XSRF-TOKEN|livewire|@vite',
               'Next.js': r'__NEXT_DATA__|/_next/',
               'Nuxt': r'__NUXT__|/_nuxt/',
               'Vue': r'__vue__|createApp|vue\.runtime',
               'React': r'__REACT|react-dom',
               'Ant Design': r'antd|ant-design',
               'Element UI': r'element-ui',
               'jQuery': r'jquery',
               'NexusPHP': r'NexusPHP|takelogin\.php|imagehash',
               'Discuz': r'discuz|forum\.php\?mod=',
               'TNode': r'x-csrf-token|gaming/genshin',
               'crypto-js': r'crypto-js|CryptoJS'}
        res['fingerprints'] = [k for k, p in FPS.items() if re.search(p, html, re.I)]

    # 只保留「像接口」的调用 + 全部 XHR
    api_calls = []
    for (m, u), v in calls.items():
        if API_HINT.search(u) or v['type'] in XHR_TYPES:
            # 过滤静态资源
            if re.search(r'\.(js|css|png|jpe?g|gif|svg|woff2?|ico|map)(\?|$)', u, re.I):
                continue
            api_calls.append(v)
    api_calls.sort(key=lambda x: (x['url']))
    res['calls'] = api_calls
    res['hosts'] = sorted(hosts.items(), key=lambda x: -x[1])[:25]
    res['assets_js'] = sorted(js_assets)[:40]

    json.dump(res, open('%s/%s.json' % (OUTDIR, site), 'w'), ensure_ascii=False, indent=1)
    return res


if __name__ == '__main__':
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    group = SITES[(batch - 1) * 3:batch * 3]
    print('=== 批次 %d：%s ===' % (batch, ', '.join(s[0] for s in group)), flush=True)
    for site, profile, home in group:
        if not os.path.isdir(profile):
            print('  [跳过] %-14s 无档案' % site, flush=True)
            continue
        try:
            r = scan(site, profile, home)
            n_api = sum(1 for c in r['calls'] if API_HINT.search(c['url']))
            print('  [✓] %-14s 访问 %d 页 | 接口调用 %d 条（其中 API %d）| JS %d | %s'
                  % (site, len(r['pages']), len(r['calls']), n_api,
                     len(r['assets_js']), ','.join(r['fingerprints'][:4])), flush=True)
        except Exception as exc:
            print('  [✗] %-14s %s' % (site, str(exc)[:100]), flush=True)
    print('已落盘到 %s' % OUTDIR)
