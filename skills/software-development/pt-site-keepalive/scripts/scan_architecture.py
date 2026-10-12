#!/usr/bin/env python3
"""29 站架构差异研究：框架 / 后端栈 / 前端栈 / 认证模型 / 反爬机制。

只读：每站 1 次 GET（登录页），分析响应头 + Set-Cookie + HTML 特征。
"""
import os  # 家目录展开（去敏时可移植化）
import json
import re
import ssl
import time
import urllib.error
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

SITES = [
    ('M-Team',        'https://kp.m-team.cc/login'),
    ('Audiences',     'https://audiences.me/login.php'),
    ('OurBits',       'https://ourbits.club/login.php'),
    ('KEEPFRDS',      'https://pt.keepfrds.com/login.php'),
    ('HDSky',         'https://hdsky.me/login.php'),
    ('PigGo',         'https://piggo.me/login.php'),
    ('CHDBits',       'https://ptchdbits.co/login.php'),
    ('UBits',         'https://ubits.club/login.php'),
    ('HDDolby',       'https://www.hddolby.com/login.php'),
    ('TTG',           'https://totheglory.im/login.php'),
    ('HDHome',        'https://hdhome.org/login.php'),
    ('OpenCD',        'https://www.open.cd/login.php'),
    ('U2',            'https://u2.dmhy.org/portalbc.php'),
    ('天雪',           'https://www.skyey2.com/'),
    ('MonikaDesign',  'https://monikadesign.uk/login'),
    ('PTHOME',        'https://www.pthome.net/login.php'),
    ('朱雀',           'https://zhuque.in/entry/login'),
    ('TorrentLeech',  'https://www.torrentleech.org/user/account/login/'),
    ('HDFans',        'https://hdfans.org/login.php'),
    ('HDU',           'https://pt.hdupt.com/login.php'),
    ('PANDA',         'https://pandapt.net/login.php'),
    ('SJTU葡萄',       'https://pt.sjtu.edu.cn/'),
    ('大青虫',         'https://cyanbug.net/login.php'),
    ('DiscFan',       'https://discfan.net/login.php'),
    ('冬樱',           'https://wintersakura.net/login.php'),
    ('织梦',           'https://zmpt.cc/login.php'),
    ('海棠PT',         'https://www.htpt.cc/login.php'),
    ('SunnyPT',       'https://sunnypt.top/'),
]

# 框架指纹：标题/HTML 里的标志
FRAMEWORK = [
    (r'Powered by NexusPHP', 'NexusPHP'),
    (r'Powered by mTorrent', 'mTorrent（自研 React 版）'),
    (r'Powered By TNode|Powered by TNode', 'TNode（Vue SPA）'),
    (r'Powered by Discuz', 'Discuz!'),
    (r'UNIT3D|unit3d', 'UNIT3D (Laravel)'),
    (r'Nexus Project', 'Nexus Project（教育网）'),
    (r'Powered by .{0,20}Nexus', 'NexusPHP 分支'),
]
# 前端栈
FRONTEND = [
    (r'jquery', 'jQuery'),
    (r'bootstrap', 'Bootstrap'),
    (r'layui', 'layui'),
    (r'vue(\.min)?\.js|createApp\(', 'Vue'),
    (r'react', 'React'),
    (r'antd|ant-design', 'Ant Design'),
    (r'_next/static|__NEXT_DATA__', 'Next.js'),
    (r'tailwind', 'Tailwind'),
    (r'crypto-js', 'crypto-js'),
]
# 反爬/防护
GUARD = [
    (r'Just a moment|cf_chl|challenge-platform', 'Cloudflare'),
    (r'safeline|SafeLine|Client Verifying', 'SafeLine'),
    (r'turnstile', 'Turnstile'),
    (r'skfaid', 'Discuz skfaid 令牌'),
    (r'input\[name="response"\]|crypto-js', 'challenge-response'),
    (r'bcrypt', '前端 bcrypt'),
]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

out = []
for name, url in SITES:
    rec = {'site': name, 'url': url}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA,
                                                   'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'})
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            html = r.read().decode('utf-8', errors='ignore')
            rec['status'] = r.status
            hdrs = {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        html = e.read().decode('utf-8', errors='ignore') if e.fp else ''
        rec['status'] = e.code
        hdrs = {k.lower(): v for k, v in (e.headers or {}).items()}
    except Exception as e:
        rec['status'] = 'ERR'
        rec['err'] = str(e)[:60]
        html, hdrs = '', {}

    rec['server'] = hdrs.get('server', '')
    rec['powered'] = hdrs.get('x-powered-by', '')
    sc = hdrs.get('set-cookie', '')
    rec['cookies'] = sorted({c.split('=')[0].strip() for c in re.split(r',(?=[^;]+=)', sc) if '=' in c})[:6]
    rec['framework'] = next((n for p, n in FRAMEWORK if re.search(p, html, re.I)), '')
    rec['frontend'] = sorted({n for p, n in FRONTEND if re.search(p, html, re.I)})
    rec['guard'] = sorted({n for p, n in GUARD if re.search(p, html, re.I)})
    ti = re.search(r'<title[^>]*>([^<]{0,50})', html, re.I)
    rec['title'] = ti.group(1).strip() if ti else ''
    out.append(rec)
    print('%-14s %-5s srv=%-16s fw=%-22s fe=%-28s guard=%s' % (
        name, rec['status'], (rec['server'] or '—')[:16], (rec['framework'] or '—')[:22],
        ','.join(rec['frontend'])[:28] or '—', ','.join(rec['guard']) or '—'), flush=True)
    time.sleep(1.2)

json.dump(out, open(os.path.expanduser('~/safeline-research/site_architecture.json'), 'w'),
          ensure_ascii=False, indent=1)
print('\n落盘: ~/safeline-research/site_architecture.json', flush=True)
