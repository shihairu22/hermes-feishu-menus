#!/usr/bin/env python3
"""海棠PT（htpt.cc）登录 + 签到 —— 纯 Python（urllib），无需浏览器。

★ 关键坑：提交时【只发四个字段】username / password / imagestring / imagehash。
  多发 `securelogin`（或 ssl/trackerssl/logout）会让服务器回
  「用户名或密码不正确！或者你还没有通过验证」——极具误导性。

两阶段验证码：导出图到 /tmp/ht_captcha.png + 打印点阵，等 /tmp/ht_answer.txt。

用法：MTEAM_NO_DELAY=1 <venv>/bin/python htpt_login.py
"""
import os, re, sys, time, subprocess
import urllib.request, urllib.parse, http.cookiejar

ENV = os.environ.get('MTEAM_ENV', os.path.expanduser('~/.pt-sessions/.env'))
BASE = 'https://www.htpt.cc/'
CJFILE = os.environ.get('HTPT_COOKIE',
                        os.path.expanduser('~/.pt-sessions/state/htpt_cookies.txt'))
PNG, ANSWER = '/tmp/ht_captcha.png', '/tmp/ht_answer.txt'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
IMG_ACCEPT = 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
HTML_ACCEPT = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'

def load_env(path):
    env = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env

env = load_env(ENV)
USER, PWD = env['MTEAM_USERNAME'], env['MTEAM_PASSWORD']
USER = os.environ.get('HT_USER', USER)

cj = http.cookiejar.LWPCookieJar(CJFILE)
if os.path.exists(CJFILE):
    try: cj.load(ignore_discard=True)
    except Exception: pass
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9')]

def get(url, ref=None, accept=None):
    h = {}
    if ref: h['Referer'] = ref
    if accept: h['Accept'] = accept
    return opener.open(urllib.request.Request(url, headers=h), timeout=45).read()

def text(b):
    h = b.decode('utf-8', 'ignore')
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))

logged = False
if os.path.exists(CJFILE):
    try:
        if '欢迎回来' in text(get(BASE + 'index.php', accept=HTML_ACCEPT)):
            print('[i] 已保存会话仍有效，跳过登录', flush=True); logged = True
    except Exception:
        pass

for rnd in range(1, 5):
    if logged: break
    print('===== 登录第 %d 轮 =====' % rnd, flush=True)
    html = get(BASE + 'login.php', accept=HTML_ACCEPT).decode('utf-8', 'ignore')
    m = re.search(r'name=["\']imagehash["\'][^>]*value=["\']([a-f0-9]+)["\']', html)
    if not m:
        print('  !! 未拿到 imagehash'); sys.exit(1)
    IH = m.group(1)
    src = re.search(r'<img[^>]*src=["\']([^"\']*(?:regimage|image\.php)[^"\']*)["\']', html, re.I)
    cap = urllib.parse.urljoin(BASE, src.group(1).replace('&amp;', '&')) if src else \
          BASE + 'image.php?action=regimage&imagehash=%s' % IH
    open(PNG, 'wb').write(get(cap, ref=BASE + 'login.php', accept=IMG_ACCEPT))
    if os.path.exists(ANSWER): os.remove(ANSWER)
    ASCII_CODE = '''
from PIL import Image
import numpy as np, sys
im = Image.open(sys.argv[1]).convert("RGB")
w, h = im.size
d = np.array(im.convert("L")).astype(int) < 100
for x in (0, 1, w-1, w-2): d[:, x] = False
for y in (0, h-1): d[y, :] = False
print("     " + "".join(str((x // 10) % 10) if x % 10 == 0 else " " for x in range(w)))
for y in range(h):
    seg = "".join("#" if d[y, x] else "." for x in range(w))
    if seg.count("#") >= 2: print("%3d %s" % (y, seg))
'''
    # ★ 注意：不要用 % 格式化这个代码串（转义极易出错，曾导致登录路径直接崩）
    subprocess.run(['/usr/bin/python3', '-c', ASCII_CODE, PNG], timeout=90)
    print('CAPTCHA_READY → %s ；把答案写入 %s' % (PNG, ANSWER), flush=True)

    t0, code = time.time(), None
    while time.time() - t0 < 420:
        if os.path.exists(ANSWER):
            code = open(ANSWER).read().strip()
            if code: break
        time.sleep(0.15)
    if not code:
        print('  !! 等答案超时'); sys.exit(1)

    # ★ 只发四个字段（带 securelogin 会失败）
    data = urllib.parse.urlencode({'username': USER, 'password': PWD,
                                   'imagestring': code, 'imagehash': IH}).encode()
    r = opener.open(urllib.request.Request(BASE + 'takelogin.php', data=data, headers={
        'Referer': BASE + 'login.php', 'Origin': BASE.rstrip('/'),
        'Accept': HTML_ACCEPT, 'Content-Type': 'application/x-www-form-urlencoded'}), timeout=45)
    body = r.read(); p = text(body)
    if '图片代码' in p or '圖片代碼' in p:
        print('  验证码无效 → 换图重试', flush=True); continue
    if '欢迎回来' in p:
        logged = True
        cj.save(ignore_discard=True)
        print('  登录成功（第 %d 轮），会话已存' % rnd, flush=True)
        break
    print('  登录失败:', p[:260], flush=True)
    break

if not logged:
    print('!! 未能登录'); sys.exit(1)

print('\n===== 签到 =====', flush=True)
at = text(get(BASE + 'attendance.php', ref=BASE + 'index.php', accept=HTML_ACCEPT))
for kw in ('签到成功', '已经签到过了', '已签到', '获得'):
    i = at.find(kw)
    if i >= 0:
        print('  ' + at[max(0, i-60):i+200], flush=True)
        break
else:
    print('  未检出签到状态:', at[:220], flush=True)

idx = text(get(BASE + 'index.php', accept=HTML_ACCEPT))
k = idx.find('欢迎回来')
print('\n用户栏: ' + idx[k:k+230], flush=True)
for lb, pat in [('魔力值', r'魔力值 \[[^\]]*\][：:]?\s*([\d.,]+)'), ('分享率', r'分享率：\s*([\d.,]+)'),
                ('上传量', r'上传量：\s*([\d.,]+ \w+)'), ('下载量', r'下载量：\s*([\d.,]+ \w+)'),
                ('邀请', r'邀请 \[发送\]:\s*([\d/]+)')]:
    m2 = re.search(pat, idx)
    if m2: print('  %s: %s' % (lb, m2.group(1)), flush=True)
cj.save(ignore_discard=True)
