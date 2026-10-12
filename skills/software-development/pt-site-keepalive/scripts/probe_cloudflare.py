#!/usr/bin/env python3
"""PigGo 的 Cloudflare 层实测：挑战类型、响应头、cookie、TLS 指纹对比。

只读探测：GET 首页 + 登录页，比较不同客户端的差异。不尝试登录。
"""
import re
import subprocess
import sys

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0')


def show(tag, code, headers, body):
    print('--- %s ---' % tag, flush=True)
    print('  HTTP %s' % code, flush=True)
    for k in ('server', 'cf-ray', 'cf-mitigated', 'cf-cache-status', 'set-cookie',
              'cf-chl-bypass', 'x-frame-options'):
        for hk, hv in headers.items():
            if hk.lower() == k:
                print('  %s: %s' % (hk, hv[:120]), flush=True)
    t = re.sub(r'\s+', ' ', body)[:200]
    print('  body: %s' % t, flush=True)
    for kw in ('Just a moment', 'cf_chl', 'challenge-platform', 'turnstile',
               'Attention Required', 'Enable JavaScript'):
        if kw.lower() in body.lower():
            print('  ★ 命中特征: %s' % kw, flush=True)
    print(flush=True)


print('=== ① 纯 requests ===', flush=True)
try:
    import requests
    s = requests.Session()
    s.headers['User-Agent'] = UA
    for path in ('/', '/login.php'):
        r = s.get('https://piggo.me' + path, timeout=25, allow_redirects=False)
        show('requests %s' % path, r.status_code, dict(r.headers), r.text)
except Exception as exc:
    print('  异常: %s' % str(exc)[:150], flush=True)

print('=== ② curl（系统 TLS 指纹）===', flush=True)
for path in ('/', '/login.php'):
    try:
        out = subprocess.run(
            ['curl', '-s', '-o', '/tmp/cf_probe_body.html', '-D', '/tmp/cf_probe_hdr.txt',
             '-w', '%{http_code}', '-A', UA, '--max-time', '25', 'https://piggo.me' + path],
            capture_output=True, text=True, timeout=40).stdout.strip()
        hdr = open('/tmp/cf_probe_hdr.txt').read()
        body = open('/tmp/cf_probe_body.html', errors='ignore').read()
        print('--- curl %s --- HTTP %s' % (path, out), flush=True)
        for line in hdr.split('\n'):
            if re.match(r'(?i)^(server|cf-ray|cf-mitigated|cf-cache-status|set-cookie)', line):
                print('  %s' % line.strip()[:130], flush=True)
        for kw in ('Just a moment', 'cf_chl', 'challenge-platform', 'turnstile'):
            if kw.lower() in body.lower():
                print('  ★ 命中特征: %s' % kw, flush=True)
        print(flush=True)
    except Exception as exc:
        print('  curl 异常: %s' % str(exc)[:120], flush=True)

print('=== ③ curl_cffi 是否可用（可模拟浏览器 TLS 指纹）===', flush=True)
try:
    from curl_cffi import requests as creq
    for imp in ('firefox133', 'chrome124'):
        try:
            r = creq.get('https://piggo.me/', impersonate=imp, timeout=25)
            print('  impersonate=%-12s HTTP %s  含挑战=%s' % (
                imp, r.status_code,
                any(k in r.text for k in ('Just a moment', 'cf_chl', 'challenge-platform'))),
                flush=True)
        except Exception as exc:
            print('  impersonate=%s 失败: %s' % (imp, str(exc)[:100]), flush=True)
except ImportError:
    print('  ✗ curl_cffi 未安装（如需要：pip install curl_cffi）', flush=True)

print('=== ④ Camoufox 档案里的 CF cookie ===', flush=True)
import os
import sqlite3
f = os.path.expanduser('~/.pt-sessions/piggo-login-session/cookies.sqlite')
if os.path.isfile(f):
    try:
        con = sqlite3.connect('file:%s?mode=ro' % f, uri=True)
        rows = con.execute('SELECT host, name, expiry FROM moz_cookies').fetchall()
        con.close()
        cf = [r for r in rows if 'cf' in r[1].lower() or 'clearance' in r[1].lower()]
        print('  总 cookie %d 条，其中 CF 相关 %d 条：' % (len(rows), len(cf)), flush=True)
        for h, n, e in cf:
            print('    %s / %s' % (h, n), flush=True)
    except Exception as exc:
        print('  读取失败（浏览器可能正在用）: %s' % str(exc)[:100], flush=True)
else:
    print('  无 cookies.sqlite', flush=True)
