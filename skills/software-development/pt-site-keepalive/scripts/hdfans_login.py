#!/usr/bin/env python3
"""HDFans（hdfans.org）登录 + 签到。NexusPHP + 图形验证码，无 Cloudflare。

两阶段用法（验证码必须双路读准再提交，站点失败提示含糊、会消耗尝试）：
  --stage1           取验证码图并保存，打印 CAPTCHA_READY（不提交，零消耗，可反复）
  --stage2 <验证码>  提交登录 → 输出账号状态 → 打开 attendance.php（即自动签到）

解释器：~/.pt-sessions/venv/bin/python
成功判据：跳转 index.php + 出现用户名 + 无 name="username"
签到判据：attendance.php 出现「第 N 次签到」/「签到已得」
"""
import os  # 家目录展开（去敏时可移植化）
import sys, re, json, urllib.request, urllib.parse, http.cookiejar

ENV = os.path.expanduser('~/.pt-sessions/.env')
BASE = 'https://hdfans.org/'
CAPTCHA_PNG = '/tmp/hdfans_captcha.png'
STATE = os.path.expanduser('~/.pt-sessions/state/hdfans_state.json')
COOKIES = os.path.expanduser('~/.pt-sessions/state/hdfans_cookies.txt')
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


def opener_with(cj):
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9'),
                     ('Referer', BASE + 'login.php')]
    return op


def stage1():
    cj = http.cookiejar.CookieJar()
    op = opener_with(cj)
    html = op.open(BASE + 'login.php', timeout=30).read().decode('utf-8', 'ignore')
    form = re.search(r'<form[^>]*action="?takelogin\.php.*?</form>', html, re.S)
    fh = form.group(0) if form else ''
    hidden = dict(re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', fh))
    secret, imagehash = hidden.get('secret', ''), hidden.get('imagehash', '')
    if not imagehash:
        print('未取到 imagehash，登录页结构可能变了'); return 1
    url = BASE + 'image.php?action=regimage&imagehash=%s&secret=%s' % (imagehash, urllib.parse.quote(secret))
    data = op.open(url, timeout=30).read()
    open(CAPTCHA_PNG, 'wb').write(data)
    json.dump({'secret': secret, 'imagehash': imagehash}, open(STATE, 'w'))
    print('imagehash=%s | secret长度=%d | 验证码图 %d 字节 → %s'
          % (imagehash[:12] + '...', len(secret), len(data), CAPTCHA_PNG))
    print('下一步：视觉模型 + ASCII 点阵双读，然后 --stage2 <验证码>')
    print('CAPTCHA_READY')
    return 0


def stage2(captcha):
    user, pwd = creds()
    st = json.load(open(STATE))
    cj = http.cookiejar.LWPCookieJar(COOKIES)
    op = opener_with(cj)

    data = urllib.parse.urlencode({
        'username': user, 'password': pwd, 'two_step_code': '',
        'imagestring': captcha, 'imagehash': st['imagehash'],
        'secret': st['secret'],
        # ★ 不要发 securelogin（站点标签为「限制只能使用本IP登录」）—— 用户明确要求一律不勾
    }).encode()
    r = op.open(BASE + 'takelogin.php', data=data, timeout=40)
    html = r.read().decode('utf-8', 'ignore')
    ok = 'index.php' in r.geturl() and 'name="username"' not in html
    print('① 登录: %s (%s)' % ('✅ 成功' if ok else '❌ 失败', r.geturl()))
    if not ok:
        for kw in ['验证码', '密码', '尝试', '禁用']:
            if kw in html:
                i = html.find(kw)
                print('   →', re.sub(r'\s+', ' ', html[max(0, i - 80):i + 100])[:160])
        return 1
    cj.save(ignore_discard=True, ignore_expires=True)

    idx = op.open(BASE + 'index.php', timeout=40).read().decode('utf-8', 'ignore')

    def grab(pat, src=idx):
        m = re.search(pat, src, re.S)
        return re.sub(r'\s+', ' ', m.group(1)).strip() if m else None

    print('② 账号: %s | 上传 %s | 下载 %s | 分享率 %s | 魔力值 %s | 做种 %s' % (
        user,
        grab(r'(?:上传量|上传)[^\d]{0,20}([\d.,]+\s*[KMGT]?i?B)'),
        grab(r'(?:下载量|下载)[^\d]{0,20}([\d.,]+\s*[KMGT]?i?B)'),
        grab(r'(?:分享率|Ratio)[^\d]{0,20}([\d.]+)'),
        grab(r'(?:魔力值)[^\d]{0,40}([\d.,]+)'),
        grab(r'(?:做种|Seeding)[^\d]{0,30}(\d+)')))

    ah = op.open(BASE + 'attendance.php', timeout=40).read().decode('utf-8', 'ignore')
    m = re.search(r'这是您的第\s*(\d+)\s*次签到[^。]*。([^<]{0,80})', ah)
    if m:
        print('③ 签到: 第 %s 次 | %s' % (m.group(1), re.sub(r'\s+', ' ', m.group(2)).strip()[:60]))
        print('   → 今天已是签到状态（attendance.php 打开即自动签），无需再点 ✅')
    elif '签到已得' in ah:
        i = ah.find('签到已得')
        print('③ 签到: 已是签到状态 →', re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', ah[i - 60:i + 80]))[:120])
    else:
        print('③ 签到: 未在页面发现签到标记，请人工核对 attendance.php 内容')
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    if sys.argv[1] == '--stage1':
        sys.exit(stage1())
    if sys.argv[1] == '--stage2':
        if len(sys.argv) < 3:
            print('用法: --stage2 <验证码>'); sys.exit(2)
        sys.exit(stage2(sys.argv[2].strip()))
    print('未知参数，见文档'); sys.exit(2)
