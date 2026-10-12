#!/usr/bin/env python3
"""M-Team 登录（适配 2026-09 新版 React UI）—— 替代旧脚本里失效的 index.php + 「退出」判据。

背景：站点已改版为 React（Powered by mTorrent），登录页变为 https://kp.m-team.cc/login，
控件 id=username / id=password；旧脚本去 index.php 找「退出」二字，新 UI 没有这两个字 → 误判未登录。

本脚本自适应：
  1. 先判登录态（有 #username 输入框 = 未登录）
  2. 登录：填 #username/#password → JS 点击提交
  3. 若出现邮箱/验证码步骤 → 自动触发发信 + 从本机邮箱读 6 位码（IMAP）
  4. 打印每一步的 URL/控件/文本，便于日后 UI 再变时快速定位

用法：cd /tmp && MTEAM_NO_DELAY=1 xvfb-run -a <camoufox venv>/bin/python mteam_login.py
"""
import os, re, sys, time, imaplib, email
import email.utils
from email.header import decode_header

ENV = os.environ.get('MTEAM_ENV', os.path.expanduser('~/.pt-sessions/.env'))
PROFILE = os.environ.get('MTEAM_PROFILE', os.path.expanduser('~/.pt-sessions/mteam-session'))
LOGIN_URL = os.environ.get('MTEAM_LOGIN_URL', 'https://kp.m-team.cc/login')
HOME_URL = os.environ.get('MTEAM_HOME_URL', 'https://kp.m-team.cc/index')


def load_env(path):
    env = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def dec(s):
    try:
        return ''.join(x.decode(c or 'utf-8', 'ignore') if isinstance(x, bytes) else x for x, c in decode_header(s))
    except Exception:
        return (s or '')[:60]


def fetch_email_code(env, since_epoch, timeout=None):
    """读 M-Team 的 6 位邮箱验证码（复用 M-Team 保活脚本的逻辑；INBOX + Junk 都扫）。"""
    host = env.get('MTEAM_EMAIL_IMAP_HOST', '')
    port = int(env.get('MTEAM_EMAIL_IMAP_PORT') or 993)
    user = env.get('MTEAM_EMAIL_USER', '')
    pwd = env.get('MTEAM_EMAIL_APP_PASSWORD', '')
    if timeout is None:
        try:
            timeout = int(env.get('MTEAM_EMAIL_CODE_TIMEOUT') or 240)
        except Exception:
            timeout = 240
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            box = imaplib.IMAP4_SSL(host, port, timeout=25)
            box.login(user, pwd)
            for folder in ('INBOX', 'Junk'):
                try:
                    typ, _ = box.select(folder)
                    if typ != 'OK':
                        continue
                    typ, data = box.search(None, 'ALL')
                except Exception:
                    continue
                ids = (data[0] or b'').split()[-30:]
                for mid in reversed(ids):
                    typ, raw = box.fetch(mid, '(RFC822)')
                    if typ != 'OK' or not raw or not raw[0]:
                        continue
                    msg = email.message_from_bytes(raw[0][1])
                    stamp = email.utils.parsedate_to_datetime(msg.get('Date', ''))
                    if stamp and stamp.timestamp() < since_epoch - 10:
                        continue
                    subj, frm = dec(msg.get('Subject', '')), dec(msg.get('From', ''))
                    parts = msg.walk() if msg.is_multipart() else [msg]
                    body = ''
                    for part in parts:
                        if part.get_content_type() in ('text/plain', 'text/html'):
                            try:
                                body += part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='replace')
                            except Exception:
                                pass
                    if not re.search(r'm[- ]?team|驗證碼|验证码|verification|code', subj + ' ' + body, re.I):
                        continue
                    m = re.findall(r'(?<!\d)\d{6}(?!\d)', subj + ' ' + body)
                    if m:
                        box.logout()
                        print('   [邮箱] 命中(%s): %s | %s' % (folder, subj[:44], frm[:30]), flush=True)
                        return m[0]
            box.logout()
        except Exception as exc:
            print('   [邮箱] 读取失败: %s: %s' % (type(exc).__name__, str(exc)[:90]), flush=True)
        time.sleep(5)
    return None


env = load_env(ENV)
USER, PWD = env.get('MTEAM_USERNAME', ''), env.get('MTEAM_PASSWORD', '')
os.makedirs(PROFILE, exist_ok=True)
from camoufox.sync_api import Camoufox


def dump(page, label, n=420):
    t = re.sub(r'\s+', ' ', page.evaluate('() => (document.body ? document.body.innerText : "")'))
    print('   %s: %s' % (label, t[:n]), flush=True)
    return t


with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=PROFILE) as browser:
    page = browser.new_page()
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(7000)

    has_form = page.evaluate("""() => !!document.querySelector('input#username, input[name="username"]')""")
    print('① URL=%s | 有登录表单=%s' % (page.url, has_form), flush=True)
    if not has_form:
        print('   → 无登录表单，可能已是登录态；去首页确认', flush=True)
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        t = dump(page, '首页')
        print('   判定:', '✅ 已登录' if not page.evaluate("""() => !!document.querySelector('input#username')""") else '❌ 仍需登录', flush=True)
        sys.exit(0)

    page.fill('input#username, input[name="username"]', USER)
    page.fill('input#password, input[name="password"]', PWD)
    print('② 已填表单，提交…', flush=True)
    page.evaluate("""() => {
        const b = document.querySelector('button[type="submit"]')
               || [...document.querySelectorAll('button,input[type=submit]')].find(e => /登\s*錄|登\s*录|登录|Sign in/i.test(e.innerText || e.value || ''));
        if (b) b.click();
    }""")
    page.wait_for_timeout(9000)
    print('③ 提交后 URL=%s' % page.url, flush=True)
    t = dump(page, '提交后页面')
    ctrls = page.evaluate("""() => [...document.querySelectorAll('input,button')].map(e =>
        [e.tagName, e.type||'', e.id||'', e.name||'', (e.placeholder||'').slice(0,24), (e.innerText||'').trim().slice(0,20)]) """)
    print('   控件:', ctrls[:14], flush=True)

    # 邮箱/验证码步骤（自适应）
    otp_sel = ''
    for sel in ('input[name="code"]', 'input[name="otp"]', 'input[name="emailCode"]', 'input#code', 'input[placeholder*="驗證"]', 'input[placeholder*="验证"]'):
        if page.locator(sel).count():
            otp_sel = sel
            break
    if otp_sel:
        print('④ 检测到验证码输入框: %s' % otp_sel, flush=True)
        email_addr = env.get('MTEAM_EMAIL_USER', '')
        if page.locator('#email').count() > 0:
            if not email_addr:
                print('   ❌ 未配置 MTEAM_EMAIL_USER，无法请求邮箱验证码', flush=True)
                sys.exit(2)
            page.fill('#email', email_addr)
            # M-Team 用前端受控表单：填完补发原生事件，否则“获取验证码”按钮保持禁用。
            page.locator('#email').press('Tab')
            page.evaluate("""(selector) => {
                const el = document.querySelector(selector);
                if (!el) return;
                for (const type of ['input', 'change', 'blur']) {
                    el.dispatchEvent(new Event(type, { bubbles: true }));
                }
            }""", '#email')
            page.wait_for_timeout(500)
            print('   已填邮箱并补发受控表单事件', flush=True)
        sent_at = time.time()
        clicked = False
        buttons = page.locator('button')
        for i in range(buttons.count()):
            button = buttons.nth(i)
            try:
                text = button.inner_text().strip()
            except Exception:
                text = ''
            if ('获取验证码' in text or '獲取驗證碼' in text) and button.is_enabled():
                button.click()
                clicked = True
                break
        if not clicked:
            page.evaluate("""() => {
                const b = [...document.querySelectorAll('button,a,span')].find(e => /獲取驗證碼|获取验证码|發送|发送|Send/i.test((e.innerText||'')));
                if (b) b.click();
            }""")
        print('   已点击获取验证码，等邮箱码…', flush=True)
        code = fetch_email_code(env, sent_at)
        if not code:
            print('   ❌ 未取到邮箱验证码，中止（未提交）', flush=True)
            sys.exit(2)
        page.fill(otp_sel, code)
        page.evaluate("""() => {
            const b = document.querySelector('button[type="submit"]')
                   || [...document.querySelectorAll('button,input[type=submit]')].find(e => /登\s*錄|提交|确认|確定/i.test(e.innerText || e.value || ''));
            if (b) b.click();
        }""")
        page.wait_for_timeout(9000)
        print('   再次提交后 URL=%s' % page.url, flush=True)
        dump(page, '页面')

    # 验证
    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(7000)
    t = dump(page, '首页')
    still_login = page.evaluate("""() => !!document.querySelector('input#username')""") or '/login' in page.url
    print('⑤ 判定: %s | URL=%s' % ('❌ 仍未登录' if still_login else '✅ 登录成功', page.url), flush=True)
    m = re.search(r'魔力值[^\d]{0,20}([\d.,]+)', t)
    if m:
        print('   魔力值:', m.group(1), flush=True)
    for lab, pat in [('邀请', r'邀請[^\d]{0,16}(\d+)'), ('分享率', r'分享率[：:]?\s*([\d.]+)'),
                     ('上传量', r'上傳量[：:]?\s*([\d.,]+\s*\w+)'), ('下载量', r'下載量[：:]?\s*([\d.,]+\s*\w+)')]:
        mm = re.search(pat, t)
        if mm:
            print('   %s: %s' % (lab, mm.group(1)), flush=True)
