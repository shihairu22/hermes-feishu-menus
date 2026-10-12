#!/usr/bin/env python3
"""SunnyPT（sunnypt.top）登录 + 签到 —— 纯 Python（urllib），无需浏览器。

站点是 Next.js SPA（非 NexusPHP），主题海贼王。无图形验证码。

链路（三步）：
  1. POST https://sunnypt.top/api/auth/session/login
     JSON {"username":..., "password":..., "code":"", "rememberMe":true}  → 下发 AuthSession/AuthRefresh cookie
  2. GET  https://sunnypt.top/api/auth/session   → data.accessToken（236 位 JWT）
     ★ 关键：给 api.sunnypt.top 用的 Bearer 就是这个 accessToken，不是 AuthSession cookie！
  3. GET  https://api.sunnypt.top/api/v1/attendance/status   → checked_in 布尔
     POST https://api.sunnypt.top/api/v1/attendance/check-in → 签到（无 body）
     GET  https://api.sunnypt.top/api/v1/user/details/info  → 账号数据

若账号开了两步验证：设环境变量 SP_2FA=<动态码>。
用法：python sunnypt_login.py
"""
import json
import os
import sys
import urllib.error
import urllib.request
import http.cookiejar

ENV = os.environ.get('MTEAM_ENV', os.path.expanduser('~/.pt-sessions/.env'))
SITE = 'https://sunnypt.top'
API = 'https://api.sunnypt.top/api/v1'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0'


def load_env(path):
    env = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


env = load_env(ENV)
USER = env.get('MTEAM_USERNAME')
PWD = env.get('MTEAM_PASSWORD')
CODE = os.environ.get('SP_2FA', '')

# ★ 持久化 cookie：优先用 AuthRefresh 续期，失败才重新登录（省一次密码校验）
COOKIE_FILE = os.path.expanduser('~/.pt-sessions/state/sunnypt_cookies.txt')
cj = http.cookiejar.MozillaCookieJar(COOKIE_FILE)
try:
    cj.load(ignore_discard=True, ignore_expires=True)
    print('[0] 已载入上次会话 cookie（%d 条）' % len(cj))
except Exception:
    print('[0] 无历史 cookie，将走完整登录')
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def call(method, url, data=None, extra=None):
    headers = {
        'User-Agent': UA,
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.8',
        'Origin': SITE,
        'Referer': SITE + '/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
    }
    if extra:
        headers.update(extra)
    body = json.dumps(data).encode() if data is not None else None
    if body:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = opener.open(req, timeout=45)
        return resp.status, resp.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode('utf-8', 'ignore')
    except Exception as exc:  # noqa: BLE001
        return 0, 'ERR %s' % exc


def main():
    print('=' * 58)
    print('SunnyPT 登录 + 签到')
    print('=' * 58)

    # ① 先试续期：AuthRefresh cookie 有效时，直接 GET /api/auth/session 就能拿到 accessToken
    token = None
    st, body = call('GET', SITE + '/api/auth/session')
    if st == 200:
        try:
            token = json.loads(body).get('data', {}).get('accessToken')
        except Exception:
            token = None
    if token:
        print('[1] ★ 续期成功（用历史会话换到 accessToken，%d 位）' % len(token))
    else:
        print('[1] 续期不可用（HTTP %s），走完整登录' % st)
        st, body = call('POST', SITE + '/api/auth/session/login',
                        {'username': USER, 'password': PWD, 'code': CODE, 'rememberMe': True})
        print('[1] 登录 HTTP %s  %s' % (st, body[:120]))
        if st != 200:
            print('    ✗ 登录失败'); return 1

        st, body = call('GET', SITE + '/api/auth/session')
        if st != 200:
            print('[2] 取 accessToken 失败 HTTP %s  %s' % (st, body[:200])); return 1
        token = json.loads(body).get('data', {}).get('accessToken')
        if not token:
            print('[2] 响应里没有 accessToken：%s' % body[:300]); return 1
        print('[2] accessToken 已获取（%d 位）' % len(token))
    try:
        cj.save(ignore_discard=True, ignore_expires=True)
        print('[2b] cookie 已保存（供下次续期）')
    except Exception as exc:
        print('[2b] cookie 保存失败: %s' % exc)
    auth = {'Authorization': 'Bearer ' + token}

    st, body = call('GET', API + '/attendance/status', extra=auth)
    print('[3] 签到状态 HTTP %s  %s' % (st, body[:300]))
    done = False
    try:
        d = json.loads(body).get('data', {})
        done = bool(d.get('checked_in'))
        if done:
            print('    → 今日已签到（连续 %s 天 / 累计 %s 天 / 本次 %s 魔力）'
                  % (d.get('days'), d.get('total_days'), d.get('points')))
    except Exception:
        pass

    if not done:
        st, body = call('POST', API + '/attendance/check-in', extra=auth)
        print('[4] 执行签到 HTTP %s  %s' % (st, body[:300]))
        if st == 200 and '"code":0' in body:
            print('    ✅ 签到成功')
    else:
        print('[4] 跳过签到（今天已完成）')

    st, body = call('GET', API + '/user/details/info', extra=auth)
    if st == 200:
        try:
            d = json.loads(body).get('data', {})
            print('[5] 账号：%s (id %s)  等级 %s' % (d.get('username'), d.get('id'), d.get('class')))
            for k, lab in [('seed_points', '魔力值'), ('uploaded', '上传'), ('downloaded', '下载'),
                           ('ratio', '分享率'), ('bonus', '魔力'), ('seeding', '做种')]:
                if k in d:
                    print('    %s: %s' % (lab, d[k]))
        except Exception:
            print('[5] 账号原始：%s' % body[:400])
    print('=' * 58)
    return 0


if __name__ == '__main__':
    sys.exit(main())
