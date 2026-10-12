#!/usr/bin/env python3
"""天雪（www.skyey2.com）纯 HTTP 登录 + 保活（无浏览器）。

核心难点 skfaid（Discuz 魔改反爬令牌）：= FingerprintJS Pro v3.3.0 的 visitorId。
已解：本地 Node（scripts/skyey_fp.js，桩好浏览器环境）直接跑站点官方 skfaid.js 现算，
输出 64 位 hex（与浏览器实测形态一致，服务端无法核验组件真伪）。

⚠ 登录尝试 5 次（登录页显示 5 TRY REMAINED）→ 脚本结构上「只提交一次」。
成功判据：cookie 出现 rkvl_2132_auth + 用户栏出现用户名/积分（本站无「退出」字样！）。

  --stage1   取登录页（提取 formhash/loginhash/表单校验）→ node 算 skfaid → 打印摘要
  --stage2   提交登录（一次）
  --stage3   保活：收集候选附件（字幕区为主，不足时扩 RAW/Rip、网盘区）→ 随机挑
             一个「近期未用过」的模拟下载；历史去重（用户要求：附件别每天一样）。
             附件链接令牌 = base64(附件号|哈希|时间戳|uid)，去重键取「附件号」（稳定）。
             下载上限 25MB（超出截断），HTML 响应视为不可下载并拉黑。

无签到插件（plugin.php?id=dsu_paulsign 已关闭）。

cookie：~/.pt-sessions/state/skyey_cookies.txt
解释器：/usr/bin/python3
"""
import re
import sys
import ssl
import json
import base64
import random
import subprocess
import urllib.request
import urllib.parse
import http.cookiejar

ENV = os.path.expanduser('~/.pt-sessions/.env')
BASE = 'https://www.skyey2.com/'
COOKIES = os.path.expanduser('~/.pt-sessions/state/skyey_cookies.txt')
STATE = os.path.expanduser('~/.pt-sessions/state/skyey_state.json')
SOURCES = [(75, '字幕区(新)'), (10, 'RAW/Rip'), (18, '网盘区')]
MAXB = 25 * 1024 * 1024
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


def clean(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s or '')).strip()


def load_cj():
    cj = http.cookiejar.LWPCookieJar(COOKIES)
    try:
        cj.load(ignore_discard=True, ignore_expires=True)
    except Exception:
        pass
    return cj


def opener(cj, referer=None):
    ctx = ssl.create_default_context()
    ctx.set_ciphers('DEFAULT@SECLEVEL=1')
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=ctx))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9'),
                     ('Referer', referer or BASE)]
    return op


def compute_skfaid():
    """本地 Node 跑官方 skfaid.js 现算令牌。"""
    import os
    fp_js = os.path.expanduser('~/.hermes/skills/software-development/pt-site-keepalive/scripts/skyey_fp.js')
    bundle = os.path.expanduser('~/.hermes/skills/software-development/pt-site-keepalive/scripts/skyey_skfaid.js')
    if not os.path.exists(bundle):
        # 补抓官方 JS（幂等）→ 直接落持久副本
        try:
            ctx = ssl.create_default_context(); ctx.set_ciphers('DEFAULT@SECLEVEL=1')
            req = urllib.request.Request(BASE + 'static/js/skfaid.js',
                                         headers={'User-Agent': UA, 'Referer': BASE})
            js = urllib.request.urlopen(req, timeout=45, context=ctx).read()
            open(bundle, 'wb').write(js)
        except Exception as e:
            return None, '补抓 skfaid.js 失败: %s' % e
    try:
        r = subprocess.run(['node', fp_js], capture_output=True, text=True, timeout=90)
    except Exception as e:
        return None, 'node 调用失败: %s' % e
    if r.returncode != 0:
        return None, 'node exit=%d stderr=%s' % (r.returncode, (r.stderr or '')[:200])
    try:
        out = json.loads(r.stdout[r.stdout.find('{'):r.stdout.rfind('}') + 1])
        return out.get('skfaId'), None
    except Exception as e:
        return None, 'JSON 解析失败: %s / %s' % (e, (r.stdout or '')[:200])


def stage1():
    cj = load_cj()
    op = opener(cj)
    r = op.open(BASE + 'member.php?mod=logging&action=login', timeout=45)
    html = r.read().decode('utf-8', 'ignore')
    open('/tmp/skyey_login_page.html', 'w').write(html)
    m = re.search(r'loginhash=([A-Za-z0-9]+)', html)
    if not m:
        if 'rkvl_2132_auth' in open(COOKIES).read() if __import__('os').path.exists(COOKIES) else False:
            print('① 已是登录态 → 可直接 --stage3'); return 0
        print('⚠ 未找到 loginhash len=%d' % len(html)); return 1
    loginhash = m.group(1)
    fh = re.search(r'name="formhash"[^>]*value="([^"]+)"', html)
    formhash = fh.group(1) if fh else ''
    qid_tag = re.search(r'<input[^>]*name="questionid"[^>]*>', html)
    questionid = ''
    if qid_tag:
        v = re.search(r'value="([^"]*)"', qid_tag.group(0))
        questionid = v.group(1) if v else ''
    skfaid, err = compute_skfaid()
    ok_fmt = bool(skfaid) and bool(re.fullmatch(r'[0-9A-Fa-f]{32,}', skfaid))
    st = {}
    try:
        st = json.load(open(STATE))
    except Exception:
        pass
    st.update({'loginhash': loginhash, 'formhash': formhash, 'questionid': questionid,
               'skfaid': skfaid})
    json.dump(st, open(STATE, 'w'))  # 合并写入：stage1 不能冲掉 ka_aids/ka_blocked 保活历史
    cj.save(ignore_discard=True, ignore_expires=True)
    print('① loginhash=%s formhash=%s questionid=%r' % (loginhash, formhash, questionid))
    print('② skfaid=%s (%s) err=%s' % (skfaid[:20] + '...' if skfaid else None,
                                       '格式OK' if ok_fmt else '格式异常', err))
    print('SKFAID_READY (登录额度 5 次，只提交一次)' if ok_fmt else '❌ skfaid 不可用，停止')
    return 0 if ok_fmt else 1


def stage2():
    user, pwd = creds()
    st = json.load(open(STATE))
    if not st.get('skfaid'):
        print('⚠ 无 skfaid，先跑 --stage1'); return 2
    cj = load_cj()
    op = opener(cj, BASE + 'member.php?mod=logging&action=login')
    url = BASE + ('member.php?mod=logging&action=login&loginsubmit=yes&loginhash=' + st['loginhash'])
    data = urllib.parse.urlencode({
        'formhash': st['formhash'], 'referer': BASE, 'skfaid': st['skfaid'],
        'loginfield': 'username', 'username': user, 'password': pwd,
        'questionid': st.get('questionid', '0'), 'answer': '',
        'cookietime': '2592000', 'loginsubmit': 'true',
    }).encode()
    r = op.open(url, data=data, timeout=45)
    html = r.read().decode('utf-8', 'ignore')
    low = html.lower()
    cj.save(ignore_discard=True, ignore_expires=True)
    jar_txt = open(COOKIES).read()
    has_auth = 'rkvl_2132_auth' in jar_txt
    ti = clean(html)
    if has_auth and ('积分' in ti or '金币' in ti):
        print('① 登录: ✅ 成功（rkvl_2132_auth 已就位）')
        m1 = re.search(r'金币[：:]?\s*(\d+)', ti)
        m2 = re.search(r'积分[：:]?\s*(\d+)', ti)
        m3 = re.search(r'用户组[：:]?\s*([^\s|]+)', ti)
        print('② 账号: PTUSER | 金币 %s | 积分 %s | 用户组 %s' % (
            m1.group(1) if m1 else '?', m2.group(1) if m2 else '?', m3.group(1) if m3 else '?'))
        return 0
    # 失败分支
    if 'just a moment' in low or 'cf-chl-' in low:
        print('❌ CF 拦截（页面是挑战页）→ 停止，不重试'); return 2
    print('① 登录: ❌ 失败（auth 缺失/无用户栏）')
    for kw in ('密码', '密碼', '用户名', '用戶名', '验证码', '驗證碼', '错误', '錯誤', '失败', '失敗', '非法', '禁止'):
        i = ti.find(kw)
        if i >= 0:
            print('   →', ti[max(0, i - 80):i + 160][:240]); break
    print('⚠ 一次即停（额度 5 次），剩余交给浏览器路径复核')
    return 1


def _decode_aid(url):
    """附件令牌 base64(附件号|哈希|时间戳|uid|帖号) → 返回稳定键 'a<附件号>' 与标签。"""
    m = re.search(r'[?&]aid=([^&"]+)', url)
    if not m:
        return None
    tok = urllib.parse.unquote(m.group(1))
    try:
        dec = base64.b64decode(tok + '=' * (-len(tok) % 4)).decode('utf-8', 'ignore')
        seg0 = dec.split('|')[0]
        if seg0.isdigit():
            return 'a%s' % seg0
    except Exception:
        pass
    return None


def _collect_source(fid, cj, max_threads=12):
    """扫一个版块：返回 ([候选], 帖子块数, 已扫线程数)。候选 = {key,tid,label,url,ref}。"""
    op = opener(cj, BASE + 'forum.php?mod=forumdisplay&fid=%s' % fid)
    lst = op.open(BASE + 'forum.php?mod=forumdisplay&fid=%s' % fid, timeout=45).read().decode('utf-8', 'ignore')
    blocks = re.findall(r'<tbody[^>]*id="normalthread_(\d+)"[^>]*>([\s\S]*?)</tbody>', lst)
    out, scanned = [], 0
    for tid, blk in blocks[:max_threads]:
        hm = re.search(r'href="(forum\.php\?mod=viewthread&(?:amp;)?tid=\d+[^"]*)"', blk)
        if not hm:
            continue
        post_url = BASE + hm.group(1).replace('&amp;', '&')
        scanned += 1
        page = op.open(post_url, timeout=45).read().decode('utf-8', 'ignore')
        for lm in re.finditer(r'<a[^>]+href="([^"]*mod=attachment[^"]*)"[^>]*>([\s\S]{0,160}?)</a>', page):
            href, text = lm.group(1), re.sub(r'<[^>]+>', '', lm.group(2)).strip()
            dl = href.replace('&amp;', '&')
            if not dl.startswith('http'):
                dl = BASE + dl.lstrip('/')
            key = _decode_aid(dl)
            if not key:
                continue
            out.append({'key': key, 'tid': tid, 'label': text[:60] or '(无标签)', 'url': dl, 'ref': post_url})
    return out, len(blocks), scanned


def stage3():
    """保活：收集候选附件 → 随机挑一个近期未用过的模拟下载（历史去重，不每天同一附件）。"""
    st_path = STATE
    st = {}
    try:
        st = json.load(open(st_path))
    except Exception:
        pass
    hist_aids = st.get('ka_aids', [])
    hist_tids = st.get('ka_tids', [])
    blocked = st.get('ka_blocked', [])

    cj = load_cj()
    all_c, seen = [], set()
    for fid, name in SOURCES:
        try:
            cands, nblk, scanned = _collect_source(fid, cj)
        except Exception as e:
            print('① %s fid=%s 扫描失败: %s' % (name, fid, e)); continue
        new = 0
        for c in cands:
            if c['key'] in seen:
                continue
            seen.add(c['key']); all_c.append(c); new += 1
        print('① %s fid=%s 帖子块 %d / 扫 %d 线程 → 新候选 %d（累计 %d）'
              % (name, fid, nblk, scanned, new, len(all_c)))
        fresh = [c for c in all_c if c['key'] not in hist_aids and c['key'] not in blocked]
        if len(fresh) >= 4:
            break

    fresh = [c for c in all_c if c['key'] not in hist_aids and c['key'] not in blocked]
    pool = fresh or [c for c in all_c if c['key'] not in blocked] or all_c
    print('② 候选合计 %d（近期未用 %d）; 已用历史: %s' % (len(all_c), len(fresh), '、'.join(hist_aids[-6:]) or '无'))

    picked, changed = None, False
    for c in random.sample(pool, min(3, len(pool))):
        try:
            op2 = opener(cj, c['ref'])
            r = op2.open(c['url'], timeout=120)
            ctype = (r.headers.get('Content-Type') or '').strip()
            head, size, truncated = b'', 0, False
            while True:
                chunk = r.read(262144)
                if not chunk:
                    break
                if not head:
                    head = chunk[:400]
                size += len(chunk)
                if size >= MAXB:
                    truncated = True
                    break
        except Exception as e:
            print('   ✗ %s [%s] 下载异常: %s' % (c['key'], c['label'][:30], e)); continue
        low = head[:200].lower().lstrip()
        if 'text/html' in ctype.lower() or low.startswith(b'<'):
            print('   ✗ %s [%s] 返回 HTML（可能需回复/不可下载）→ 拉黑，换下一候选' % (c['key'], c['label'][:30]))
            if c['key'] not in blocked:
                blocked.append(c['key']); blocked[:] = blocked[-30:]
            changed = True
            continue
        c['size'], c['ctype'], c['truncated'] = size, ctype, truncated
        picked = c
        break

    if picked:
        st['ka_aids'] = ([picked['key']] + [k for k in hist_aids if k != picked['key']])[:20]
        st['ka_tids'] = ([picked['tid']] + [t for t in hist_tids if t != picked['tid']])[:15]
        st['ka_blocked'] = blocked
        st['ka_last'] = {'tid': picked['tid'], 'key': picked['key'], 'label': picked['label'],
                         'bytes': picked['size'], 'ctype': picked['ctype']}
        json.dump(st, open(st_path, 'w'))
        print('③ 模拟下载 ✅ %s [%s] tid=%s %d 字节%s (%s) | 已记历史，下次自动换'
              % (picked['key'], picked['label'][:40], picked['tid'], picked['size'],
                 '（超 25MB 已截断）' if picked['truncated'] else '', picked['ctype']))
        return 0
    if changed:
        st['ka_blocked'] = blocked
        json.dump(st, open(st_path, 'w'))
    print('③ 无成功候选（候选 %d，拉黑 %d）→ 保活靠登录本身' % (len(all_c), len(blocked)))
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    cmd = sys.argv[1]
    if cmd == '--stage1':
        sys.exit(stage1())
    if cmd == '--stage2':
        sys.exit(stage2())
    if cmd == '--stage3':
        sys.exit(stage3())
    print('参数错误，见文档'); sys.exit(2)
