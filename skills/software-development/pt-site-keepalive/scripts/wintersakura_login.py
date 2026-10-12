#!/usr/bin/env python3
"""WinterSakura（wintersakura.net）登录 + 签到 —— 标准 NexusPHP，纯 urllib，无需浏览器。

两阶段验证码：导出图到 /tmp/ws_captcha.png + 打印点阵，等 /tmp/ws_answer.txt 被写入答案。

关键点：
  1) 本站是标准 NexusPHP：password 有 name、明文 POST，**没有 response/challenge-response**
  2) 取验证码图要带图片类 Accept 头
  3) 签到 = GET /attendance.php，打开即自动签

用法：MTEAM_NO_DELAY=1 <venv>/bin/python wintersakura_login.py
"""
import os, re, sys, time, subprocess
import urllib.request, urllib.parse, http.cookiejar

ENV = os.environ.get('MTEAM_ENV', os.path.expanduser('~/.pt-sessions/.env'))
BASE = 'https://wintersakura.net/'
CJFILE = os.environ.get('WS_COOKIE',
                        os.path.expanduser('~/.pt-sessions/state/wintersakura_cookies.txt'))
PNG, ANSWER = '/tmp/ws_captcha.png', '/tmp/ws_answer.txt'
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

def post(url, data, ref):
    h = {'Referer': ref, 'Origin': BASE.rstrip('/'),
         'Accept': HTML_ACCEPT, 'Content-Type': 'application/x-www-form-urlencoded'}
    return opener.open(urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), headers=h), timeout=45).read()

def text(b):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', b.decode('utf-8', 'ignore')))

logged = False
if os.path.exists(CJFILE):
    try:
        t = text(get(BASE + 'index.php', accept=HTML_ACCEPT))
        if '欢迎回来' in t or '歡迎回來' in t:
            print('[i] 已保存会话仍有效，跳过登录', flush=True)
            logged = True
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
          BASE + 'image.php?action=regimage&imagehash=%s&secret=' % IH
    open(PNG, 'wb').write(get(cap, ref=BASE + 'login.php', accept=IMG_ACCEPT))
    if os.path.exists(ANSWER): os.remove(ANSWER)
    ASCII_CODE = '''
from PIL import Image
import numpy as np, sys
im = Image.open(sys.argv[1]).convert("RGB")
w, h = im.size
d = np.array(im.convert("L")).astype(int) < 100
# 去掉外边框
for x in (0, 1, w-1, w-2): d[:, x] = False
for y in (0, h-1): d[y, :] = False
print("     " + "".join(str((x // 10) % 10) if x % 10 == 0 else " " for x in range(w)))
for y in range(h):
    seg = "".join("#" if d[y, x] else "." for x in range(w))
    if seg.count("#") >= 2: print("%3d %s" % (y, seg))
'''
    # ★ 不要用 % 格式化这个代码串（转义极易出错，曾导致登录路径直接崩）
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

    body = post(BASE + 'takelogin.php',
                {'secret': '', 'username': USER, 'password': PWD, 'two_step_code': '',
                 'imagestring': code, 'imagehash': IH}, BASE + 'login.php')  # 不发 securelogin（限制本IP登录，用户要求一律不勾）
    p = text(body)
    if '图片代码' in p or '圖片代碼' in p:
        print('  验证码无效 → 换图重试', flush=True); continue
    if '欢迎回来' in p or '歡迎回來' in p:
        logged = True
        cj.save(ignore_discard=True)
        print('  登录成功（第 %d 轮），会话已存' % rnd, flush=True)
        break
    print('  登录失败:', p[:220], flush=True); break

if not logged:
    print('!! 未能登录'); sys.exit(1)

print('\n===== 签到 =====', flush=True)
at = text(get(BASE + 'attendance.php', ref=BASE + 'index.php', accept=HTML_ACCEPT))
i = at.find('签到成功')
if i < 0: i = at.find('簽到成功')
print('  ' + (at[i:i+220] if i >= 0 else '未检出「签到成功」: ' + at[:200]), flush=True)

idx = text(get(BASE + 'index.php', accept=HTML_ACCEPT))
k = idx.find('欢迎回来')
if k < 0: k = idx.find('歡迎回來')
print('\n用户栏: ' + idx[k:k+220], flush=True)
cj.save(ignore_discard=True)
