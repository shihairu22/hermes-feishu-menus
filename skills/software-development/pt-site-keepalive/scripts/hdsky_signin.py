#!/usr/bin/env python3
"""HDSky 签到（showup 弹层）—— 导出验证码 + 打印净化点阵，等答案文件后提交一次。
答案文件：/tmp/hdsky_signin_ans.txt（写 6 位验证码）
"""
import os, re, base64, sys, time, subprocess
BASE = 'https://hdsky.me/'
UD = os.path.expanduser('~/.pt-sessions/hdsky-login-session')
ANS = '/tmp/hdsky_signin_ans.txt'
PNG = '/tmp/hdsky_signin_captcha.png'
os.makedirs(UD, exist_ok=True)
from camoufox.sync_api import Camoufox

with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=UD) as browser:
    page = browser.new_page()
    page.goto(BASE + 'index.php', wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)

    page.evaluate("() => { const e = document.querySelector('#showup'); if (e) e.click(); }")
    page.wait_for_timeout(4000)
    info = page.evaluate("""() => ({
        img: (document.querySelector('#showupimg')||{}).src || '',
        input: !!document.querySelector('#imagestring'),
        btn: !!document.querySelector('#showupbutton')
    })""")
    print('① 签到层: 输入框=%s 按钮=%s' % (info['input'], info['btn']), flush=True)
    print('   验证码 src:', info['img'][:130], flush=True)

    if not info['img']:
        print('   ❌ 未取到验证码图；页面片段:', flush=True)
        print('  ', re.sub(r'\s+', ' ', page.evaluate('() => document.body.innerText'))[:300], flush=True)
        sys.exit(1)

    data = page.evaluate("""async (src) => {
        const r = await fetch(src, {credentials: 'include'});
        const b = await r.blob();
        return await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(b); });
    }""", info['img'])
    raw = base64.b64decode(data.split(',', 1)[1])
    open(PNG, 'wb').write(raw)
    print('② 验证码已导出:', PNG, len(raw), '字节', flush=True)

    code = '''
from PIL import Image
import numpy as np
a = np.array(Image.open("%s").convert("RGB")).astype(int)
r, g, b = a[:,:,0], a[:,:,1], a[:,:,2]
mx = np.maximum(np.maximum(r,g),b); mn = np.minimum(np.minimum(r,g),b)
sat = mx - mn
lum = (r*299 + g*587 + b*114) / 1000
mask = (sat < 60) & (lum < 140)
h, w = mask.shape
print("尺寸 %%dx%%d 笔画像素=%%d" %% (w, h, int(mask.sum())))
print("    " + "".join(str((x//10)%%10) if x%%10==0 else " " for x in range(w)))
for y in range(h):
    line = "".join("#" if mask[y,x] else "." for x in range(w))
    if "#" in line:
        print("%%3d %%s" %% (y, line))
''' % PNG
    print('③ 净化点阵（低饱和深色像素）:', flush=True)
    print(subprocess.run(['/usr/bin/python3', '-c', code], capture_output=True, text=True).stdout, flush=True)
    print('CAPTCHA_READY', flush=True)

    ans = ''
    for _ in range(420):
        if os.path.exists(ANS):
            ans = open(ANS).read().strip()
            if ans:
                break
        time.sleep(1)
    if not ans:
        print('❌ 等答案超时，退出（未提交）', flush=True)
        sys.exit(2)
    print('④ 收到答案:', ans, flush=True)

    page.fill('#imagestring', ans)
    page.evaluate("() => { const e = document.querySelector('#showupbutton'); if (e) e.click(); }")
    page.wait_for_timeout(8000)
    t = re.sub(r'\s+', ' ', page.evaluate('() => document.body.innerText'))
    print('⑤ 提交后:', t[:500], flush=True)
    m = re.search(r'(签到成功.{0,60}|已签到.{0,40}|验证码错误.{0,30}|Wrong CAPTCHA.{0,20}|今天.{0,20}签到.{0,20})', t)
    print('   ★ 判定:', m.group(0) if m else '（未见明确判定）', flush=True)
    os.remove(ANS)
