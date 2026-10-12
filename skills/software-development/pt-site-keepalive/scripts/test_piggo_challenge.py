#!/usr/bin/env python3
"""验证 SafeLine 挑战算法在 PigGo 上是否有效（只读探测，不尝试登录）。

来源：github.com/xj2268-TA/SafeLine-bypass
"""
import json
import re
import sys

import requests

ORIGIN = 'https://piggo.me'


def calc(data):
    """SafeLine challenge 的令牌算法（来自公开 PoC）。"""
    t, n, total = 1, len(data), sum(data)
    r = (6 + n + total) % 6 + 6
    for _ in range(r):
        t *= 6
    if t < 6666:
        t *= n
    if t > 0x3F940AA:
        t //= n
    for idx, val in enumerate(data):
        t += pow(val, 3)
        t ^= idx
        t ^= val + idx
    result = []
    while t > 0:
        result.insert(0, t & 63)
        t >>= 6
    return result


s = requests.Session()
s.headers['User-Agent'] = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                           '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

print('=== ① 探测拦截状态 ===', flush=True)
r1 = s.get(ORIGIN + '/', timeout=20)
print('  HTTP %s  (468=被拦)' % r1.status_code, flush=True)

m = re.search(r'SafeLineChallenge\("([^"]+)"', r1.text)
if not m:
    print('  页面里没有 SafeLineChallenge 标记', flush=True)
    print('  片段: %s' % re.sub(r'\s+', ' ', r1.text)[:300], flush=True)
    sys.exit(0)

client_id = m.group(1)
print('  ✓ client_id = %s' % client_id, flush=True)

print('=== ② 请求 PoW 数据 ===', flush=True)
r2 = s.post(ORIGIN + '/.safeline/challenge/v2/api/issue',
            json={'client_id': client_id, 'level': 1}, timeout=20)
print('  HTTP %s' % r2.status_code, flush=True)
try:
    d = r2.json()['data']
except Exception as exc:
    print('  解析失败: %s' % exc, flush=True)
    print('  原始: %s' % r2.text[:300], flush=True)
    sys.exit(1)
print('  issue_id = %s' % d.get('issue_id'), flush=True)
print('  data 长度 = %s' % len(d.get('data', [])), flush=True)

print('=== ③ 计算令牌 ===', flush=True)
result = calc(d['data'])
print('  result 长度 = %d  前 10 位 = %s' % (len(result), result[:10]), flush=True)

print('=== ④ 提交验证 ===', flush=True)
r4 = s.post(ORIGIN + '/.safeline/challenge/v2/api/verify',
            json={'issue_id': d['issue_id'], 'result': result, 'serials': [],
                  'client': {'userAgent': '', 'platform': '', 'language': '', 'vendor': '',
                             'screen': [0, 0], 'visitorId': '', 'score': 0, 'target': []}},
            timeout=20)
print('  HTTP %s' % r4.status_code, flush=True)
try:
    jwt = r4.json()['data']['jwt']
    print('  ✓ 拿到 JWT: %s...' % jwt[:60], flush=True)
except Exception as exc:
    print('  未拿到 JWT: %s' % exc, flush=True)
    print('  原始: %s' % r4.text[:300], flush=True)
    sys.exit(1)

print('=== ⑤ 带 cookie 重试 ===', flush=True)
s.cookies.set('sl-challenge-jwt', jwt, path='/')
s.cookies.set('sl-challenge-server', 'local', path='/')
r5 = s.get(ORIGIN + '/', timeout=20)
ok = r5.status_code != 468 and 'SafeLineChallenge' not in r5.text
print('  HTTP %s  → %s' % (r5.status_code, '✅ 成功通过！' if ok else '❌ 仍被拦'), flush=True)
if ok:
    print('  页面片段: %s' % re.sub(r'\s+', ' ', r5.text)[:200], flush=True)
