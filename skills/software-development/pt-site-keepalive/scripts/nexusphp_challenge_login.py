#!/usr/bin/env python3
"""NexusPHP 「challenge-response」类站点的通用裸 HTTP 登录（默认按 discfan.net 的参数）。

机制（取自站点页面 JS，已在 discfan.net 上验证到「凭据判定」这一步）：
    chp  = sha256(password)
    ssh  = sha256(secret + chp)
    resp = hmac_sha256(message=challenge, key=ssh)      # 注意是 (message, key)

流程：GET login.php(取 imagehash) → GET 验证码图(存图 + 打印 ASCII 点阵)
     → 【阻塞等答案文件】→ POST /api/challenge → 本地算 response → POST takelogin.php

用法：
    <venv>/bin/python nexusphp_challenge_login.py \\
        --site https://discfan.net --env /path/.env
    写完答案文件即自动提交；脚本可反复重跑（验证码错通常不扣尝试次数）。

三条必须遵守的点（否则会误判成“识图不准”）：
  1) 取验证码图必须带浏览器图片 Accept 头 + Referer；
  2) 密码框没有 name 属性是正常的，别据此改选择器；
  3) 只读 .env 里的凭据，不打印密码明文。
"""
import argparse, hashlib, hmac, http.cookiejar, json, os, re, subprocess, sys, time
import urllib.parse, urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
IMG_ACCEPT = 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
HTML_ACCEPT = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'

POINTARRAY = '''
from PIL import Image
import numpy as np
im = Image.open(sys.argv[1]).convert("RGB")
w, h = im.size
d = np.array(im.convert("L")).astype(int) < 100
print("     " + "".join(str((x // 10) % 10) if x % 10 == 0 else " " for x in range(w)))
for y in range(h):
    row = "".join("#" if d[y, x] else "." for x in range(w))
    if row.count("#") >= 3:
        print("%3d %s" % (y, row))
'''


def load_env(path, user_key, pwd_key):
    env = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env[user_key], env[pwd_key]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', required=True, help='如 https://discfan.net')
    ap.add_argument('--env', required=True)
    ap.add_argument('--user-key', default='MTEAM_USERNAME')
    ap.add_argument('--password-key', default='MTEAM_PASSWORD')
    ap.add_argument('--login-path', default='/login.php')
    ap.add_argument('--challenge-path', default='/api/challenge')
    ap.add_argument('--post-path', default='/takelogin.php')
    ap.add_argument('--png', default='/tmp/nx_captcha.png')
    ap.add_argument('--answer', default='/tmp/nx_answer.txt')
    ap.add_argument('--wait', type=int, default=180)
    a = ap.parse_args()

    base = a.site.rstrip('/') + '/'
    user, pwd = load_env(a.env, a.user_key, a.password_key)
    for p in (a.png, a.answer):
        if os.path.exists(p):
            os.remove(p)

    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9')]

    def get(url, referer=None, accept=HTML_ACCEPT):
        h = {'Accept': accept}
        if referer:
            h['Referer'] = referer
        return op.open(urllib.request.Request(url, headers=h), timeout=40)

    def post(url, data, referer, as_json=False):
        body = json.dumps(data).encode() if as_json else urllib.parse.urlencode(data).encode()
        h = {'Referer': referer, 'Origin': base.rstrip('/'),
             'Content-Type': 'application/json' if as_json else 'application/x-www-form-urlencoded',
             'Accept': 'application/json, text/javascript, */*; q=0.01',
             'X-Requested-With': 'XMLHttpRequest'}
        return op.open(urllib.request.Request(url, data=body, headers=h), timeout=40)

    # 1) 登录页 → imagehash
    html = get(base + a.login_path.lstrip('/')).read().decode('utf-8', 'ignore')
    m = re.search(r'name=["\']imagehash["\'][^>]*value=["\']([a-f0-9]{32})["\']', html) or \
        re.search(r'value=["\']([a-f0-9]{32})["\'][^>]*name=["\']imagehash["\']', html)
    if not m:
        sys.exit('未找到 imagehash（页面可能被拦截 / 站点结构调整）: ' + html[:200])
    ih = m.group(1)

    # 2) 验证码图（关键：必须带图片 Accept 头）
    img = get('%simage.php?action=regimage&imagehash=%s&secret=' % (base, ih),
              referer=base + a.login_path.lstrip('/'), accept=IMG_ACCEPT).read()
    open(a.png, 'wb').write(img)
    print('验证码图已存 %s（%d 字节）' % (a.png, len(img)), flush=True)
    subprocess.run(['/usr/bin/python3', '-c', POINTARRAY, a.png], timeout=60)
    print('--- 点阵结束，把验证码写入 %s ---' % a.answer, flush=True)

    t0, code = time.time(), None
    while time.time() - t0 < a.wait:
        if os.path.exists(a.answer):
            code = open(a.answer).read().strip()
            if code:
                break
        time.sleep(0.2)
    if not code:
        sys.exit('等答案超时')

    # 3) challenge
    cd = json.loads(post(base + a.challenge_path.lstrip('/'), {'username': user},
                         base + a.login_path.lstrip('/'), as_json=True).read().decode())
    if cd.get('ret') not in (0, None):
        sys.exit('challenge 失败: %s' % cd.get('msg'))
    d = cd.get('data') or cd
    challenge, secret = str(d['challenge']), str(d['secret'])
    chp = hashlib.sha256(pwd.encode()).hexdigest()
    ssh = hashlib.sha256((secret + chp).encode()).hexdigest()
    resp = hmac.new(ssh.encode(), challenge.encode(), hashlib.sha256).hexdigest()
    print('challenge=%d 位 secret=%d 位 response=%s...' % (len(challenge), len(secret), resp[:16]), flush=True)

    # 4) 提交
    r = post(base + a.post_path.lstrip('/'),
             {'secret': '', 'username': user, 'two_step_code': '', 'imagestring': code,
              'imagehash': ih, 'response': resp},
             base + a.login_path.lstrip('/'))
    plain = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', r.read().decode('utf-8', 'ignore')))
    for kw in ('圖片代碼', '登錄失敗', '不正確', '驗證', '歡迎', '退出'):
        if kw in plain:
            i = plain.find(kw)
            print('「%s」→ %s' % (kw, plain[max(0, i - 60):i + 170]), flush=True)
    mm = re.search(r'你還有 \[(\d+)\] 次嘗試機會', plain)
    print('剩余尝试机会:', mm.group(1) if mm else '（无提示 → 可能已登录）', flush=True)
    print('判定:', '✅ 成功' if ('歡迎' in plain or '退出' in plain) else '❌ 未通过', flush=True)


if __name__ == '__main__':
    main()
