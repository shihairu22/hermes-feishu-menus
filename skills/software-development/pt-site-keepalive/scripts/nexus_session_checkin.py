#!/usr/bin/env python3
"""会话复用签到（NexusPHP 系通用）—— 带已存 cookie 直接读页面，零消耗、不开浏览器。

为什么要它：hdfans_login.py / panda_login.py 等只提供「--stage1 取码 / --stage2 <码> 提交」两阶段，
**没有「已是登录态就跳过」的捷径**；而它们的 cookie（NexusPHP 的 c_secure_uid/c_secure_pass）
是持久 cookie，跨日仍有效。此时根本不需要读验证码：带同一 cookie jar 读 index.php 判登录态，
再读 attendance.php —— NexusPHP 打开该页即自动签到。

用法：
  /usr/bin/python3 scripts/nexus_session_checkin.py --name HDFans --base https://hdfans.org/ \
      --cookies ~/.pt-sessions/state/hdfans_cookies.txt [--attendance attendance.php] [--user PTUSER]

判据：index.php 无 name="username" 且出现用户名 → 已登录；attendance.php 出现「第 N 次签到 / 已签到 / 签到已得 N」（简繁双匹配：「簽到」系写法同样识别，DiscFan 等繁体站适用）。
退出码：0=已登录并读到签到结果；1=网络/站点错误；2=未登录（需走 --stage1/--stage2 读码登录）。
实测 2026-10-04/05：HDFans、PANDA、冬樱 均靠它免验证码完成签到。
"""
import argparse
import http.cookiejar
import re
import sys
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


def plain(html):
    txt = re.sub(r'<script.*?</script>', ' ', html, flags=re.S | re.I)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    return re.sub(r'\s+', ' ', txt).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True)
    ap.add_argument('--base', required=True)
    ap.add_argument('--cookies', required=True)
    ap.add_argument('--attendance', default='attendance.php')
    ap.add_argument('--user', default='PTUSER')
    a = ap.parse_args()
    base = a.base if a.base.endswith('/') else a.base + '/'

    cj = http.cookiejar.LWPCookieJar(a.cookies)
    try:
        cj.load(ignore_discard=True)
    except Exception as e:
        print('❌ cookie 载入失败：%s' % e)
        return 2
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9')]

    def get(path):
        return op.open(base + path, timeout=45).read().decode('utf-8', 'ignore')

    print('===== %s 会话复用签到 =====' % a.name)
    try:
        html = get('index.php')
    except Exception as e:
        print('❌ index.php 失败：%s' % e)
        return 1

    logged = ('name="username"' not in html) and (a.user in html)
    print('① 登录态：%s（index.php %d 字节）' % ('✅ 已登录' if logged else '❌ 未登录/需重登', len(html)))
    if not logged:
        print('   → 需走 --stage1/--stage2 读码登录')
        return 2

    t = plain(html)
    m = re.search(r'(欢迎回来[^ ]*(?: [^ ]+){0,3})', t) or re.search(r'魔力值[^ ]*[:：]? ?([\d,\.]+)', t)
    if m:
        print('   用户栏：%s' % m.group(0)[:160])
    try:
        att = plain(get(a.attendance))
    except Exception as e:
        print('❌ %s 失败：%s' % (a.attendance, e))
        return 1

    hit = None
    for pat in (r'签到成功[^。]{0,80}', r'簽到成功[^。]{0,80}',
                r'第 ?\d+ ?次签到[^。]{0,60}', r'第 ?\d+ ?次簽到[^。]{0,60}',
                r'今天已经签到过[^。]{0,40}', r'今天已經簽到過[^。]{0,40}',
                r'已签到[^ ]{0,20}', r'已簽到[^ ]{0,20}',
                r'签到已得 ?\d+', r'簽到已得 ?\d+'):
        mm = re.search(pat, att)
        if mm:
            hit = mm.group(0)
            break
    print('② 签到页：%s' % (hit if hit else '（未见签到文字，片段见下）'))
    if not hit:
        print('   %s' % att[:300])
    cj.save(ignore_discard=True)
    print('③ cookie 已回写（保持会话新鲜）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
