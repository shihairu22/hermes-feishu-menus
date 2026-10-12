#!/usr/bin/env python3
"""PT 站批量巡检（持久会话版）—— 一次跑完“需要浏览器”的那一批站。

思路（2026-09-27 实测把 29 站例行从数小时压到 ~30 分钟）：
  1) 先用纯脚本的站（sunnypt / sjtu / tl / hdfans / panda / discfan / wintersakura / htpt …）跑一遍；
  2) 再用本脚本把其余“浏览器站”串行巡检一遍：逐站复用持久 profile → 判登录态 → 进签到页（多数站打开即签）；
  3) 只对报告异常的站单独处理（重登 / 过验证码 / 过 WAF）。

设计要点：
  - **串行**，每站用完就 killall camoufox-bin，避免风控与 profile 锁冲突。
  - **只读优先**：只打开页面 + 读取状态，需要点击的站才用配置里的 click / text_click。
  - 登录态判据：页面出现 退出/登出/控制面板/欢迎回来 等标记；签到态：正则抓「第 N 次签到 / 签到已得 / 已签到 / 已签…」。
  - 会话失效的站不会自动尝试登录（很多站尝试次数有限），而是在输出里报「❌ 未登录/需重登」等人工处理。

用法：
  cd /tmp && MTEAM_NO_DELAY=1 xvfb-run -a --server-args="-screen 0 1280x900x24" \
      <camoufox venv>/bin/python pt_batch_check.py
可选：环境变量 PT_ONLY=关键字（逗号分隔）只跑部分站。
"""
import os, re, sys

os.environ.setdefault('MTEAM_NO_DELAY', '1')

# 站点 → (首页/签到页 URL, 持久 profile 目录, 可选点击器)
SITES = [
    dict(n='2 Audiences',    base='https://audiences.me/',       prof=os.path.expanduser('~/.pt-sessions/audiences-login-session'),  path='attendance.php'),
    dict(n='3 OurBits',      base='https://ourbits.club/',       prof=os.path.expanduser('~/.pt-sessions/ourbits-login-session'),    path='attendance.php'),
    dict(n='4 KEEPFRDS',     base='https://pt.keepfrds.com/',    prof=os.path.expanduser('~/.pt-sessions/keepfrds-login-session'),   path='index.php'),
    dict(n='5 HDSky',        base='https://hdsky.me/',           prof=os.path.expanduser('~/.pt-sessions/hdsky-login-session'),      path='index.php', click='#showup'),
    dict(n='6 PigGo',        base='https://piggo.me/',           prof=os.path.expanduser('~/.pt-sessions/piggo-login-session'),      path='attendance.php'),
    dict(n='7 CHDBits',      base='https://ptchdbits.co/',       prof=os.path.expanduser('~/.pt-sessions/chdbits-login-session'),    path='bakatest.php'),
    dict(n='8 UBits',        base='https://ubits.club/',         prof=os.path.expanduser('~/.pt-sessions/ubits-login-session'),      path='attendance.php'),
    dict(n='9 HDDolby',      base='https://www.hddolby.com/',    prof=os.path.expanduser('~/.pt-sessions/hddolby-login-session'),    path='attendance.php'),
    dict(n='10 TTG',         base='https://totheglory.im/',      prof=os.path.expanduser('~/.pt-sessions/ttg-login-session'),        path='index.php', click='#signed'),
    dict(n='11 HDHome',      base='https://hdhome.org/',         prof=os.path.expanduser('~/.pt-sessions/hdhome-login-session'),     path='attendance.php'),
    dict(n='13 U2',          base='https://u2.dmhy.org/',        prof=os.path.expanduser('~/.pt-sessions/u2-login-session'),         path='index.php'),
    dict(n='14 天雪',        base='https://www.skyey2.com/',     prof=os.path.expanduser('~/.pt-sessions/skyey-login-session'),      path='index.php'),
    dict(n='15 MonikaDesign', base='https://monikadesign.uk/',   prof=os.path.expanduser('~/.pt-sessions/monika-login-session'),     path='index.php'),
    dict(n='16 PTHOME',      base='https://www.pthome.net/',     prof=os.path.expanduser('~/.pt-sessions/pthome-login-session'),     path='attendance.php'),
    dict(n='17 朱雀',        base='https://zhuque.in/',          prof=os.path.expanduser('~/.pt-sessions/zhuque-login-session'),     path='/'),
    dict(n='1 M-Team',       base='https://kp.m-team.cc/',       prof=os.path.expanduser('~/.pt-sessions/mteam-session'), path='/'),
    dict(n='20 HDU',         base='https://pt.hdupt.com/',       prof=os.path.expanduser('~/.pt-sessions/hdu-login-session'),        path='index.php'),
    dict(n='23 大青虫',      base='https://cyanbug.net/',        prof=os.path.expanduser('~/.pt-sessions/bug-login-session'),        path='attendance.php'),
    dict(n='26 织梦',        base='https://zmpt.cc/',            prof=os.path.expanduser('~/.pt-sessions/zm-session'),               path='attendance.php'),
    # ★ BYR 是 IPv6-only 教育网站，家宽直连 403（源 IP 黑名单：240e/2409/2408 段被屏蔽）
    #   → 全站唯一必须走代理的站。地址可用 BYR_PROXY 覆盖，默认 NAS mihomo。
    dict(n='27 BYR',         base='https://byr.pt/',             prof=os.path.expanduser('~/.pt-sessions/byr-session'),             path='index.php',
         proxy=os.environ.get('BYR_PROXY', 'http://127.0.0.1:7890')),
    dict(n='28 海棠PT',      base='https://www.htpt.cc/',        prof=os.path.expanduser('~/.pt-sessions/ht-session'),               path='attendance.php'),
]

LOGIN_MARKS = re.compile(r'退出|登出|控制面板|控制台|個人中心|个人中心|欢迎回来|歡迎回來|欢迎,|歡迎,')
SIGN_PAT = re.compile(r'(第\s*\d+\s*次签到.{0,50}|签到成功.{0,60}|已签到.{0,40}|簽到成功.{0,60}|'
                      r'今天已经签到过了.{0,20}|您今天已经签到过了.{0,20}|今天已经签过到了.{0,30}|'
                      r'簽到已得[^\s]*|签到已得[^\s]*|已连续.{0,20}天|已經签到.{0,30}|'
                      r'簽到得魔力|签到得魔力|立即签到|\[签到\]|簽到)')

only = [s for s in os.environ.get('PT_ONLY', '').split(',') if s.strip()]
from camoufox.sync_api import Camoufox

summary = []
for s in SITES:
    name, base, prof, path = s['n'], s['base'], s['prof'], s['path']
    if only and not any(k in name for k in only):
        continue
    print('\n' + '=' * 62, flush=True)
    print('===== [%s] %s' % (name, base), flush=True)
    if not os.path.isdir(prof):
        print('  ⚠ profile 不存在：%s（需要先走一次完整登录）' % prof, flush=True)
        summary.append((name, '无会话目录'))
        continue
    try:
        px = {'server': s['proxy']} if s.get('proxy') else None
        print('  代理: %s' % (px['server'] if px else '（直连）'), flush=True)
        with Camoufox(headless=False, os="windows", humanize=True,
                      persistent_context=True, user_data_dir=prof,
                      **({'proxy': px} if px else {})) as browser:
            page = browser.new_page()
            resp = page.goto(base + path, wait_until="domcontentloaded", timeout=60000)
            http_status = getattr(resp, 'status', None)
            page.wait_for_timeout(5000)
            t = re.sub(r'\s+', ' ', page.evaluate('() => document.body.innerText'))
            url = page.url
            # ★ 登录态判据（2026-09-27 修假阳性：登录页里含「自动登出」会被旧判据误判为已登录）
            #   硬判据：页面上还有登录表单（username/password 输入框）→ 肯定未登录；
            #           URL 含 login/sign-in/auth → 未登录；文本含「未登录/必须登录」→ 未登录。
            has_login_form = page.evaluate("""() => !!document.querySelector(
                'input[name="username"], input#username, input[type="password"], input[name="password"]')""")
            url_l = url.lower()
            url_is_login = any(k in url_l for k in ('login', 'sign-in', 'signin', '/auth'))
            not_logged_txt = bool(re.search(r'未登录|未登錄|請登錄|请登录|必须在登录后|登錄 / 註冊|登錄\s*/\s*註冊|Sign in to', t))
            # ★ 再修一个假阳性：Cloudflare/SafeLine 的人机验证页既无登录表单也无「未登录」字样，
            #   旧判据会误报为「已登录」；这类页要单独报「被拦，无法判定」。
            cf_blocked = bool(re.search(r'Performing security verification|Just a moment|Ray ID|Checking your browser|'
                                        r'Security Detection|SafeLine|安全检测|验证您不是机器人', t, re.I))
            # ★ 再修一个假阳性：被源 IP 黑名单拦下时站点返回 403，页面上既无登录表单
            #   也无「未登录」字样 → 旧判据会误报成「已登录」（BYR 实测踩过）。
            http_403 = (http_status == 403)
            logged = (not has_login_form) and (not url_is_login) and (not not_logged_txt) \
                and (not cf_blocked) and (not http_403)
            m = SIGN_PAT.search(t)
            print('  URL: %s' % url, flush=True)
            verdict = ('✅ 已登录' if logged else
                       '⚠ 被 CF/WAF 拦，无法判定' if cf_blocked else
                       '⚠ HTTP 403 被源 IP 黑名单拦（此站必须走代理）' if http_403 else
                       '❌ 未登录/需重登')
            print('  登录: %s (表单=%s URL含login=%s CF拦=%s HTTP=%s)' % (
                verdict, has_login_form, url_is_login, cf_blocked, http_status), flush=True)
            print('  签到态: %s' % (m.group(0) if m else '（未见签到相关文字）'), flush=True)
            # 需要点击的站
            clicked = None
            if s.get('click'):
                try:
                    page.evaluate("(sel) => { const e = document.querySelector(sel); if (e) e.click(); }", s['click'])
                    clicked = s['click']
                except Exception as e:
                    clicked = 'ERR %s' % str(e)[:60]
            if clicked:
                page.wait_for_timeout(6000)
                t2 = re.sub(r'\s+', ' ', page.evaluate('() => document.body.innerText'))
                m2 = SIGN_PAT.search(t2)
                print('  点击 [%s] 后: %s' % (clicked, m2.group(0) if m2 else t2[:200]), flush=True)
                if m2:
                    m = m2
            print('  用户栏片段: %s' % t[:230], flush=True)
            summary.append((name, ('✅ ' + (m.group(0)[:40] if m else '已登录')) if logged
                            else ('⚠ HTTP 403 被拦' if http_403 else '❌ 未登录')))
    except Exception as e:
        print('  ⚠ 异常: %s: %s' % (type(e).__name__, str(e)[:200]), flush=True)
        summary.append((name, '异常 %s' % type(e).__name__))
    sys.stdout.flush()
    os.system('killall -q camoufox-bin 2>/dev/null; sleep 2')

print('\n' + '=' * 62)
print('汇总：')
for n, r in summary:
    print('  %-16s %s' % (n, r))
