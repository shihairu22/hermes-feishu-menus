#!/usr/bin/env python3
"""葡萄 PT（pt.sjtu.edu.cn，Nexus Project 框架）登录 + 签到探测。

特点：无图形验证码、无 JS 加密、无 CF；表单只有 username/password/checkcode(固定令牌)。
注意：该站 15 分钟不活动自动登出，且长期不登录会清号 → 例行做「登录保活」。
"""
import os  # 家目录展开（去敏时可移植化）
import re, sys, urllib.request, urllib.parse, http.cookiejar

ENV = os.path.expanduser('~/.pt-sessions/.env')
BASE = 'https://pt.sjtu.edu.cn/'
COOKIES = os.path.expanduser('~/.pt-sessions/state/sjtu_cookies.txt')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

env = {}
for line in open(ENV):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
USER, PWD = env['MTEAM_USERNAME'], env['MTEAM_PASSWORD']

cj = http.cookiejar.LWPCookieJar(COOKIES)
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9'),
                 ('Referer', BASE + 'login.php')]

# 1) 取登录页，拿 checkcode 令牌
html = op.open(BASE + 'login.php', timeout=30).read().decode('utf-8', 'ignore')
m = re.search(r'name="checkcode"[^>]*value="([^"]*)"', html) or re.search(r'value="([^"]*)"[^>]*name="checkcode"', html)
checkcode = m.group(1) if m else 'XxXx'
print('checkcode 令牌:', checkcode)
print('登录页含验证码图:', 'image.php' in html or 'captcha' in html.lower())

# 2) 提交
data = urllib.parse.urlencode({'username': USER, 'password': PWD, 'checkcode': checkcode}).encode()
r = op.open(BASE + 'takelogin.php', data=data, timeout=40)
h = r.read().decode('utf-8', 'ignore')
ok = ('index.php' in r.geturl()) and ('name="username"' not in h)
print('① 登录: %s (URL=%s)' % ('✅ 成功' if ok else '❌ 失败', r.geturl()))
if not ok:
    t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style).*?</\1>', ' ', h, flags=re.S)))
    print('   响应文本:', t[:400])
    for kw in ['密码', '用户名', '禁用', '禁止', '错误', '尝试', '不存在']:
        i = t.find(kw)
        if i >= 0:
            print('   「%s」→ %s' % (kw, t[max(0, i - 70):i + 110]))
    sys.exit(1)

cj.save(ignore_discard=True, ignore_expires=True)

# 3) 首页与账号信息
idx = op.open(BASE + 'index.php', timeout=40).read().decode('utf-8', 'ignore')
body = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style).*?</\1>', ' ', idx, flags=re.S)))
print('② 用户栏:', body[:260])
for lb, pat in [('上传', r'上传[^\d]{0,20}([\d.,]+\s*[KMGT]?i?B)'), ('下载', r'下载[^\d]{0,20}([\d.,]+\s*[KMGT]?i?B)'),
                ('分享率', r'分享率[^\d]{0,20}([\d.]+)'), ('积分', r'积分[^\d]{0,20}([\d.,]+)'),
                ('做种', r'做种[^\d]{0,20}(\d+)')]:
    mm = re.search(pat, body)
    if mm:
        print('   %s: %s' % (lb, mm.group(1)))

# 4) 找签到入口
print('\n③ 签到入口探测:')
found = False
cand = re.findall(r'href="([^"]*(?:sign|checkin|attendance|bonus|qiandao)[^"]*)"', idx, re.I)
if cand:
    print('   页面里的候选链接:', sorted(set(cand))[:6]); found = True
for p in ('attendance.php', 'mybonus.php', 'qiandao.php', 'signin.php'):
    try:
        rr = op.open(BASE + p, timeout=30)
        bb = rr.read().decode('utf-8', 'ignore')
        bt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', bb))
        print('   %-18s HTTP %s | %s' % (p, rr.status, ('含「签到」→ ' + bt[bt.find('签到') - 40:bt.find('签到') + 90]) if '签到' in bt else bt[:80]))
        if '签到' in bt:
            found = True
    except urllib.error.HTTPError as e:
        print('   %-18s HTTP %s' % (p, e.code))
    except Exception as e:
        print('   %-18s 异常 %s' % (p, type(e).__name__))
print('   → 结论:', '有签到相关入口（见上）' if found else '页面未见签到入口（可能只需登录保活）')
