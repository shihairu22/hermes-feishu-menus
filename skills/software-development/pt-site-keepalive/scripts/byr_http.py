#!/usr/bin/env python3
"""BYRBT（byr.pt，北邮人）纯 HTTP 登录保活（无浏览器）。

⚠ 必须走 NAS 代理 http://127.0.0.1:7890（教育网站，直连不通）——对本脚本是例外红线。
流程（2026-09-30 从 SPA 前端逆向）：
  ① POST https://byr.pt/api/v2/login.php
     JSON: {"type":"username","username":U,"password":P,"remember":false}
     响应信封 {"success":bool,"code":200,"msg":...,"data":{"auth_token":...}}
  ② token 可用于 Authorization: Bearer <token>；同时保留 Session cookie
  ③ GET index.php 复核「欢迎」+ 分享率/上传量/魔力值（经典页由 SPA 登录的 cookie 复用）
本站无签到，保活即本脚本。

  --stage1   登录（一次）
  --stage2   index.php 复核
存档：~/.pt-sessions/state/byr_state.json + byr_cookies.json
解释器：/usr/bin/python3（requests）
"""
import os
import re
import sys
import json

import requests

ENV = os.path.expanduser('~/.pt-sessions/.env')
BASE = 'https://byr.pt/'
PROXIES = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
STATE = os.path.expanduser('~/.pt-sessions/state/byr_state.json')
COOKJAR = os.path.expanduser('~/.pt-sessions/state/byr_cookies.json')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


def creds():
    env = {}
    for line in open(ENV):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env['MTEAM_USERNAME'], env['MTEAM_PASSWORD']


def clean(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s or '')).strip()


def make_session():
    s = requests.Session()
    s.proxies = PROXIES
    s.headers.update({'User-Agent': UA, 'Accept-Language': 'zh-CN,zh;q=0.9'})
    if os.path.exists(COOKJAR):
        try:
            s.cookies = requests.utils.cookiejar_from_dict(json.load(open(COOKJAR)))
        except Exception:
            pass
    return s


def stage1():
    user, pwd = creds()
    s = make_session()
    r = s.post(BASE + 'api/v2/login.php',
               json={'type': 'username', 'username': user, 'password': pwd, 'remember': False},
               headers={'Origin': 'https://byr.pt', 'Referer': 'https://byr.pt/login',
                        'Content-Type': 'application/json'},
               timeout=60)
    try:
        j = r.json()
    except Exception:
        print('非 JSON 响应: HTTP %s / %s' % (r.status_code, r.text[:300]))
        return 1
    ok = bool(j.get('success')) and str(j.get('code')) == '200'
    print('① 登录: %s (HTTP %s) msg=%r' % ('✅ 成功' if ok else '❌ 失败', r.status_code, j.get('msg')))
    if not ok:
        print('   →', json.dumps(j, ensure_ascii=False)[:400])
        return 1
    data = j.get('data') or {}
    tok = data.get('auth_token')
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump({'token': tok, 'uid': data.get('userId') or data.get('uid'),
               'username': data.get('username') or user}, open(STATE, 'w'))
    json.dump(requests.utils.dict_from_cookiejar(s.cookies), open(COOKJAR, 'w'))
    print('② token: %s... | uid=%s | cookie 数=%d' % ((tok or '')[:16], data.get('uid') or data.get('userId'),
                                                      len(s.cookies)))
    return 0


def stage2():
    s = make_session()
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {}
    h = {}
    if st.get('token'):
        h['Authorization'] = 'Bearer ' + st['token']
    r = s.get(BASE + 'index.php', headers=h, timeout=60)
    html = r.text
    ti = clean(html)
    print('① index.php HTTP %s len=%d' % (r.status_code, len(html)))
    i = ti.find('欢迎')
    if i >= 0:
        print('② 欢迎语:', ti[i:i + 70])
    for label, pat in [('分享率', r'分享率[：:]?\s*([\d.,]+)'),
                       ('上传量', r'上传量[：:]?\s*([\d.,]+ ?\w+-?B)'),
                       ('魔力值', r'魔力值[：:]?\s*([\d,.]+)')]:
        m = re.search(pat, ti)
        if m:
            print('   %s: %s' % (label, m.group(1)))
    if '欢迎' not in ti:
        print('   ⚠ 未见欢迎语；页面片段:', ti[:220])
        return 1
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    cmd = sys.argv[1]
    if cmd == '--stage1':
        sys.exit(stage1())
    if cmd == '--stage2':
        sys.exit(stage2())
    print('参数错误，见文档'); sys.exit(2)
