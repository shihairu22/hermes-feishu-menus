#!/usr/bin/env python3
"""通用 NexusPHP 登录脚本（Camoufox）—— 一次覆盖 11 个站。

为什么需要：这 11 站以前只靠「复用持久会话」，cookie 一到期就只能人工重登（全量压测暴露的 P1 缺口）。
本脚本把它们的登录流程统一成一份配置表 + 一套通用逻辑。

支持：
  - 已有登录态自动跳过（先判登录态，不死等表单）
  - 图形验证码：导出图 + 打印 ASCII 点阵 → 等答案文件（两阶段等待）
  - 需要 2FA 的站：**先取图形验证码图 → 最后才要动态码 → 两者同一秒填入并提交**
    （反例：先填 TOTP 再等验证码，等 2 分钟 → 站点回「两步验证码错误！」，因为 TOTP 只 30 秒）
  - Cloudflare / Turnstile：先等页面渲染完再操作
  - 登录后可选进签到页
  - 只用 JS 点击提交（避免 Playwright click 卡在 performing click action）

用法：
  cd /tmp && MTEAM_NO_DELAY=1 xvfb-run -a --server-args="-screen 0 1280x900x24" \
      <camoufox venv>/bin/python nexusphp_login.py --site hdsky
  python nexusphp_login.py --list          # 列出全部站点 key
  python nexusphp_login.py --site hdsky --check   # 只判登录态，不登录

答案文件约定：
  验证码 → /tmp/nx_<key>_captcha.txt
  动态码 → /tmp/nx_<key>_2fa.txt
"""
import os, re, sys, time, base64, subprocess, argparse

os.environ.setdefault('MTEAM_NO_DELAY', '1')
ENV = os.environ.get('MTEAM_ENV', os.path.expanduser('~/.pt-sessions/.env'))

# ====== 站点配置表 ======
SITES = {
    'audiences': dict(name='2 Audiences', base='https://audiences.me/', prof=os.path.expanduser('~/.pt-sessions/audiences-login-session'),
                      login='login.php', signin='attendance.php', need_2fa=False, risk='',
                      ok=['退出', '欢迎回来', '控制面板'], note='CF 人机验证 + 图形验证码'),
    'ourbits': dict(name='3 OurBits', base='https://ourbits.club/', prof=os.path.expanduser('~/.pt-sessions/ourbits-login-session'),
                    login='login.php', signin='attendance.php', need_2fa=False, risk='',
                    ok=['退出', '欢迎回来'], note='CF + 无图形验证码'),
    'keepfrds': dict(name='4 KEEPFRDS', base='https://pt.keepfrds.com/', prof=os.path.expanduser('~/.pt-sessions/keepfrds-login-session'),
                     login='login.php', signin=None, need_2fa=False, risk='',
                     ok=['退出', '欢迎回来'], note='TOTP 可空，可能出 Turnstile'),
    'hdsky': dict(name='5 HDSky', base='https://hdsky.me/', prof=os.path.expanduser('~/.pt-sessions/hdsky-login-session'),
                  login='login.php', signin='index.php', need_2fa=False, risk='连错 10 次封 IP',
                  ok=['退出', '欢迎回来'], note='图形验证码，两步可空'),
    'chdbits': dict(name='7 CHDBits', base='https://ptchdbits.co/', prof=os.path.expanduser('~/.pt-sessions/chdbits-login-session'),
                    login='login.php', signin='bakatest.php', need_2fa=False, risk='',
                    ok=['退出', '欢迎回来'], note='图形验证码'),
    'ubits': dict(name='8 UBits', base='https://ubits.club/', prof=os.path.expanduser('~/.pt-sessions/ubits-login-session'),
                  login='login.php', signin='index.php', need_2fa=False, risk='仅 6 次尝试，失败封 IP',
                  ok=['退出', '欢迎回来'], note='CF + Turnstile（提交前等令牌就绪）'),
    'hddolby': dict(name='9 HDDolby', base='https://www.hddolby.com/', prof=os.path.expanduser('~/.pt-sessions/hddolby-login-session'),
                    login='login.php', signin='attendance.php', need_2fa=True, risk='20 次',
                    ok=['退出', '欢迎回来'], note='CF + 图形验证码 + 强制两步验证'),
                    'piggo': dict(name='6 PigGo', base='https://piggo.me/', prof=os.path.expanduser('~/.pt-sessions/piggo-login-session'),
                    login='login.php', signin='attendance.php', need_2fa=True, risk='未知',
                    ok=['退出', '欢迎回来'], note='SafeLine WAF（自动过）+ 强制两步验证，2FA 字段 two_step_code'),
                    'u2': dict(name='13 U2', base='https://u2.dmhy.org/', prof=os.path.expanduser('~/.pt-sessions/u2-login-session'),
                    login='login.php', signin='', need_2fa=True, risk='10 次',
                    ok=['退出', '欢迎回来'], note='图形验证码 + 强制两步验证；签到是图像题，登录后跑 scripts/u2_showup_signin.py'),
    'ttg': dict(name='10 TTG', base='https://totheglory.im/', prof=os.path.expanduser('~/.pt-sessions/ttg-login-session'),
                login='login.php', signin='index.php', need_2fa=False, risk='仅 6 次，失败封 IP，绝不盲试',
                ok=['退出', '欢迎回来'], note='无验证码无 CF，但次数极少'),
    'hdhome': dict(name='11 HDHome', base='https://hdhome.org/', prof=os.path.expanduser('~/.pt-sessions/hdhome-login-session'),
                   login='login.php', signin='attendance.php', need_2fa=False, risk='20 次',
                   ok=['退出', '欢迎回来'], note='无验证码无 CF'),
    'pthome': dict(name='16 PTHOME', base='https://www.pthome.net/', prof=os.path.expanduser('~/.pt-sessions/pthome-login-session'),
                   login='login.php', signin='attendance.php', need_2fa=False, risk='',
                   ok=['退出', '欢迎回来'], note='CF JS 挑战（curl 403）+ 图形验证码'),
    'opencd': dict(name='12 OpenCD', base='https://www.open.cd/', prof=os.path.expanduser('~/.pt-sessions/opencd-login-session'),
                   login='login.php', signin='plugin_sign-in.php', need_2fa=False, risk='',
                   ok=['退出', '欢迎回来', '控制面板'], note='登录+签到都要图形验证码'),
}

ASCII_CODE = r'''
from PIL import Image
import numpy as np, sys
im = Image.open(sys.argv[1]).convert("RGB")
a = np.array(im).astype(int)
h, w, _ = a.shape
blk = np.logical_and(np.logical_and(a[:,:,0] < 100, a[:,:,1] < 100), a[:,:,2] < 100)
if int(blk.sum()) < 200:                      # 彩色噪点少/非纯黑文字 → 退回灰度阈值
    g = np.array(im.convert("L")).astype(float)
    bg = np.percentile(g, 85, axis=0)
    blk = (bg[None, :] - g) > 18
print("    " + "".join(str((x // 10) % 10) if x % 10 == 0 else " " for x in range(w)))
print("    " + "".join(str(x % 10) for x in range(w)))
for y in range(h):
    line = "".join("#" if blk[y, x] else "." for x in range(w))
    if "#" in line: print("%3d %s" % (y, line))
'''


def load_env(path):
    env = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def body_text(page, tries=25):
    """安全读页面文本：CF 挑战/导航过渡期 document.body 可能为 null（直接 evaluate 会崩）。"""
    for _ in range(tries):
        try:
            if page.evaluate('() => !!document.body'):
                return re.sub(r'\s+', ' ', page.evaluate('() => document.body.innerText'))
        except Exception:
            pass
        page.wait_for_timeout(1000)
    return ''


def wait_file(path, timeout=420, label='答案'):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(path):
            v = open(path).read().strip()
            if v:
                os.remove(path)
                return v
        time.sleep(0.2)
    return None


def run(site_key, check_only=False):
    cfg = SITES[site_key]
    env = load_env(ENV)
    USER, PWD = env.get('MTEAM_USERNAME', ''), env.get('MTEAM_PASSWORD', '')
    prof, base = cfg['prof'], cfg['base']
    os.makedirs(prof, exist_ok=True)
    cap_file = '/tmp/nx_%s_captcha.txt' % site_key
    fa_file = '/tmp/nx_%s_2fa.txt' % site_key
    for f in (cap_file, fa_file):
        if os.path.exists(f):
            os.remove(f)

    from camoufox.sync_api import Camoufox
    print('=' * 62, flush=True)
    print('===== [%s] %s   %s' % (cfg['name'], base, cfg['note']), flush=True)
    if cfg['risk']:
        print('  ⚠ 风险：%s' % cfg['risk'], flush=True)

    with Camoufox(headless=False, os="windows", humanize=True,
                  persistent_context=True, user_data_dir=prof) as browser:
        page = browser.new_page()

        # ① 先看是否已有登录态
        page.goto(base + 'index.php', wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        t = body_text(page)
        has_form = page.evaluate("""() => !!document.querySelector('input[name="username"], input#username')""")
        logged = (not has_form) and any(k in t for k in cfg['ok'])
        print('  ① 登录态：%s' % ('✅ 已登录（跳过登录）' if logged else '未登录，走登录流程'), flush=True)
        if check_only:
            return 'already' if logged else 'logged_out'

        if not logged:
            # ★ 2FA 站的正确顺序：先取验证码图 → 读图 → 最后才要动态码 → 一起填 → 立刻提交。
            #   反例（曾踩坑）：先填 TOTP 再等验证码 → 等 2 分钟 → 站点回「两步验证码错误！」
            code2fa = ''
            page.goto(base + cfg['login'], wait_until="domcontentloaded", timeout=60000)
            for _ in range(15):
                page.wait_for_timeout(2000)
                if page.evaluate("""() => !!document.querySelector('input[name="username"], input#username')"""):
                    break
            print('  ③ 登录页：%s' % page.url, flush=True)

            page.fill('input[name="username"], input#username', USER)
            page.fill('input[name="password"], input#password', PWD)

            # ④ 图形验证码（两阶段）
            cap_img = page.evaluate("""() => {
                const i = [...document.querySelectorAll('img')].find(e =>
                    /image\.php|regimage|captcha|verify/i.test(e.src || ''));
                return i ? i.src : '';
            }""")
            if cap_img:
                # ★ 取图必须带图片类 Accept 头（缺了它，某些站返回的图与校验答案不匹配 → 怎么读都「图片代码无效」）
                data = page.evaluate("""async (src) => {
                    const r = await fetch(src, {credentials: 'include',
                        headers: {'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'}});
                    const b = await r.blob();
                    return await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(b); });
                }""", cap_img)
                png = '/tmp/nx_%s_captcha.png' % site_key
                open(png, 'wb').write(base64.b64decode(data.split(',', 1)[1]))
                print('  ④ 验证码已导出：%s' % png, flush=True)
                print(subprocess.run(['/usr/bin/python3', '-c', ASCII_CODE, png], capture_output=True, text=True).stdout, flush=True)
                # 额外生成「净化 + 6x 放大」图，便于视觉模型或用户读（高噪点图很有效）
                try:
                    clean_code = '''
from PIL import Image
import numpy as np, sys
a = np.array(Image.open(sys.argv[1]).convert("RGB")).astype(int)
blk = np.logical_and(np.logical_and(a[:,:,0] < 100, a[:,:,1] < 100), a[:,:,2] < 100)
if int(blk.sum()) < 200:
    g = np.array(Image.open(sys.argv[1]).convert("L")).astype(float)
    bg = np.percentile(g, 85, axis=0); blk = (bg[None, :] - g) > 18
blk[:2,:]=False; blk[-2:,:]=False; blk[:,:2]=False; blk[:,-2:]=False
h, w = blk.shape
Image.fromarray(np.where(blk, 0, 255).astype("uint8")).resize((w*6, h*6), Image.NEAREST).save(sys.argv[2])
print("CLEAN_IMG " + sys.argv[2])
'''
                    print(subprocess.run(['/usr/bin/python3', '-c', clean_code, png, png.replace('.png', '_clean.png')],
                                         capture_output=True, text=True).stdout, flush=True)
                except Exception as exc:
                    print('   （净化图生成失败，不影响主流程）', flush=True)
                print('  CAPTCHA_READY → 请把验证码写入 %s%s'
                      % (cap_file, '（本页还需动态码，可一并给出）' if cfg['need_2fa'] else ''), flush=True)
                cap = wait_file(cap_file, timeout=1800, label='验证码')
                if not cap:
                    print('  ❌ 等验证码超时，中止（未提交）', flush=True)
                    return 'timeout_captcha'
                for sel in ('input[name="imagestring"]', 'input[name="imagecode"]', 'input[name="verify_code"]',
                            'input[name="captcha"]', 'input[name="code"]', 'input[name="imagestring"]'):
                    if page.locator(sel).count():
                        page.fill(sel, cap)
                        break
                print('  ⑤ 已填入验证码', flush=True)
            else:
                print('  ④ 本页无图形验证码', flush=True)

            # ⑤b 动态码：放在提交前最后一步（TOTP 仅 30 秒，必须「拿到就提交」）
            if cfg['need_2fa']:
                print('  NEED_2FA → 请把该站动态码写入 %s' % fa_file, flush=True)
                code2fa = wait_file(fa_file, timeout=1800, label='动态码')
                if not code2fa:
                    print('  ❌ 等动态码超时，中止（未提交）', flush=True)
                    return 'timeout_2fa'
                filled_2fa = False
                for sel in ('input[name="two_step_code"]', 'input[name="oneCode"]', 'input[name="2fa"]',
                            'input[name="2FA"]', 'input[name="code"]', 'input[name="otp"]'):
                    if page.locator(sel).count():
                        page.fill(sel, code2fa)
                        filled_2fa = True
                        break
                print('  ⑤b 已填入动态码%s' % ('' if filled_2fa else '（⚠ 未找到 2FA 输入框）'), flush=True)

            # ⑤ 若站点有 Cloudflare Turnstile，**必须等令牌就绪再提交**（否则站点回「验证失败：未进行验证」）
            has_ts = page.evaluate("""() => !!document.querySelector('input[name="cf-turnstile-response"], .cf-turnstile, iframe[src*="challenges.cloudflare"]')""")
            if has_ts:
                print('  ⑤ 检测到 Turnstile，等令牌就绪…', flush=True)
                tok = ''
                for _ in range(40):
                    tok = page.evaluate("""() => (document.querySelector('input[name="cf-turnstile-response"]') || {}).value || ''""")
                    if tok and len(tok) > 20:
                        break
                    page.wait_for_timeout(1500)
                print('    令牌%s（长度 %d）' % ('已就绪' if len(tok) > 20 else '未就绪，仍尝试提交', len(tok)), flush=True)

            # ⑥ 只用 JS 点击提交（Playwright click 可能卡死）
            page.evaluate("""() => {
                const b = document.querySelector('input[type="submit"], button[type="submit"], #login-form input[type="button"]')
                       || [...document.querySelectorAll('input,button')].find(e => /登\s*录|登录|Sign in/i.test(e.value || e.innerText || ''));
                if (b) b.click();
            }""")
            page.wait_for_timeout(8000)
            t2 = body_text(page)
            still_form = page.evaluate("""() => !!document.querySelector('input[name="username"], input#username')""")
            ok = (not still_form) and any(k in t2 for k in cfg['ok'])
            print('  ⑦ 登录：%s | URL=%s' % ('✅ 成功' if ok else '❌ 失败/需确认', page.url), flush=True)
            if not ok:
                print('     页面片段：%s' % t2[:260], flush=True)
                print('     ⚠ 已停止（不重试，避免白耗尝试次数）', flush=True)
                return 'login_failed'

        # ⑦ 登录后（可选）进签到页
        if cfg['signin']:
            try:
                r = page.goto(base + cfg['signin'], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)
                t3 = body_text(page)
                m = re.search(r'(第\s*\d+\s*次签到.{0,40}|签到成功.{0,40}|已签到.{0,30}|签到已得[^\s]*|'
                              r'今天已经签过到了.{0,30}|您今天已经签到过了.{0,20}|簽到已得[^\s]*|已連續簽到.{0,20})', t3)
                print('  ⑧ 签到页 %s → HTTP %s | %s' % (cfg['signin'], r.status if r else '?',
                      m.group(0) if m else '（未见签到文字）'), flush=True)
            except Exception as e:
                print('  ⑧ 签到页异常：%s' % str(e)[:100], flush=True)
        return 'ok'


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', help='站点 key（见 --list）')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--check', action='store_true', help='只判登录态，不登录')
    a = ap.parse_args()
    if a.list or not a.site:
        print('可用站点（--site <key>）：')
        for k, v in SITES.items():
            print('  %-12s %-14s %-18s %s' % (k, v['name'], v['base'], v['note']))
        sys.exit(0)
    if a.site not in SITES:
        print('未知站点：%s' % a.site); sys.exit(1)
    sys.exit(0 if run(a.site, a.check) in ('ok', 'already', 'logged_out') else 1)
