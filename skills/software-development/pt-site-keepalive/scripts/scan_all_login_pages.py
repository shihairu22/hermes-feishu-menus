#!/usr/bin/env python3
"""29 站登录页「源码级」系统扫描（只读，不尝试登录）。

对每站抓登录页 HTML，提取：
  - HTTP 状态 / 是否被 CF / WAF 拦截
  - 表单 action / method
  - 所有 input 字段（name / type / 是否隐藏 / 是否有值）
  - 引用的 JS 文件（并标记是否含加密相关文件名）
  - meta 令牌（csrf / token）
  - 页面里出现的加密关键词（md5 / sha256 / crypto / hmac / rsa / challenge）
输出：逐站明细 + 末尾横向对比表 + JSON 落盘。
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
    ('U2',            'https://u2.dmhy.org/login.php'),
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

CF_MARK = ('Just a moment', 'cf_chl', 'challenge-platform', 'Attention Required',
           'Enable JavaScript and cookies')
WAF_MARK = ('SafeLine', 'safeline', 'Client Verifying', 'Security Detection')
CRYPTO_MARK = ('md5', 'sha1', 'sha256', 'crypto', 'hmac', 'rsa', 'challenge',
               'CryptoJS', 'forge', 'jsencrypt', 'bcrypt', 'pwmd5')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

results = []
for name, url in SITES:
    row = {'site': name, 'url': url}
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            html = r.read().decode('utf-8', errors='ignore')
            row['status'] = r.status
            row['bytes'] = len(html)
    except urllib.error.HTTPError as e:
        try:
            html = e.read().decode('utf-8', errors='ignore')
        except Exception:
            html = ''
        row['status'] = e.code
        row['bytes'] = len(html)
    except Exception as e:
        row['status'] = 'ERR'
        row['err'] = str(e)[:70]
        html = ''
    row['secs'] = round(time.time() - t0, 2)

    if html:
        row['cf'] = any(m.lower() in html.lower() for m in CF_MARK)
        row['waf'] = any(m.lower() in html.lower() for m in WAF_MARK)
        # 表单
        forms = re.findall(r'<form[^>]*>', html, re.I)
        row['forms'] = len(forms)
        act = re.search(r'<form[^>]*action=["\']([^"\']+)', html, re.I)
        row['form_action'] = act.group(1) if act else ''
        meth = re.search(r'<form[^>]*method=["\']([^"\']+)', html, re.I)
        row['form_method'] = (meth.group(1) if meth else '').upper()
        # input 字段
        fields = []
        for m in re.finditer(r'<input([^>]*)>', html, re.I):
            a = m.group(1)
            n = re.search(r'name=["\']([^"\']+)', a, re.I)
            ty = re.search(r'type=["\']([^"\']+)', a, re.I)
            if n:
                fields.append({
                    'n': n.group(1),
                    't': (ty.group(1) if ty else 'text').lower(),
                })
        row['inputs'] = fields
        row['hidden'] = [f['n'] for f in fields if f['t'] == 'hidden']
        row['passwords'] = [f['n'] for f in fields if f['t'] == 'password']
        # JS
        js = re.findall(r'<script[^>]*src=["\']([^"\']+)', html, re.I)
        row['js'] = [j.split('/')[-1][:40] for j in js][:10]
        row['js_crypto'] = [j.split('/')[-1][:40] for j in js
                            if any(k in j.lower() for k in ('md5', 'sha', 'crypto', 'hmac',
                                                            'rsa', 'encrypt', 'challenge', 'login'))]
        # meta 令牌
        metas = {}
        for m in re.finditer(r'<meta[^>]*name=["\']([^"\']+)["\'][^>]*content=["\']([^"\']*)', html, re.I):
            if any(k in m.group(1).lower() for k in ('csrf', 'token', 'verify')):
                metas[m.group(1)] = m.group(2)[:16] + '…' if len(m.group(2)) > 16 else m.group(2)
        row['meta_tokens'] = metas
        # 加密关键词
        row['crypto_words'] = sorted({k for k in CRYPTO_MARK if k.lower() in html.lower()})
        # 标题
        ti = re.search(r'<title[^>]*>([^<]{0,60})', html, re.I)
        row['title'] = ti.group(1).strip() if ti else ''
    else:
        row['cf'] = row['waf'] = False
    results.append(row)

    flag = 'CF' if row.get('cf') else ('WAF' if row.get('waf') else '  ')
    print('[%-3s] %-14s %-6s %-8s %5.1fs  %s' % (
        flag, name, row['status'], '%dB' % row.get('bytes', 0), row['secs'],
        row.get('title', '')[:30]), flush=True)
    time.sleep(1.5)

json.dump(results, open(os.path.expanduser('~/safeline-research/site_source_scan.json'), 'w'),
          ensure_ascii=False, indent=1)
print('\n=== 落盘: ~/safeline-research/site_source_scan.json ===', flush=True)
