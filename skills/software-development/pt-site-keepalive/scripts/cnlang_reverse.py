#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CnLang 站点逆向侦察（只读）：
① 快捷导航/功能清单 ② 用户组权限 ③ 资源帖(售价/附件)机制
④ 移动版/热搜 ⑤ CF 敏感路径矩阵 ⑥ 搜索接口 ⑦ 模板资产 ⑧ 遗留暴露面
"""
import html
import re
import subprocess

BASE = 'https://cnlang.org'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0'
JAR = 'cnlang_cookies.txt'


def curl(u, extra=None):
    args = ['curl', '-s', '-A', UA, '-b', JAR, '--max-time', '35']
    if extra:
        args += extra
    args.append(u)
    return subprocess.run(args, capture_output=True, text=True).stdout


def txt(h):
    h = re.sub(r'<script[\s\S]*?</script>', ' ', h)
    h = re.sub(r'<style[\s\S]*?</style>', ' ', h)
    h = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', html.unescape(h)).strip()


try:
    home = open('home.html', encoding='utf-8', errors='ignore').read()
except FileNotFoundError:
    home = curl(BASE + '/')
    open('home.html', 'w').write(home)

print('══ ① 快捷导航/功能清单 ══')
seen = set()
for u, t in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]{1,16}?)\s*</a>', home):
    if not t or 'member.php' in u or 'logout' in u:
        continue
    if any(k in u for k in ('spacecp', 'medal', 'task', 'magic', 'ranklist', 'sign', 'search', 'pm', 'notice', 'favorite', 'friend', 'wall')):
        key = (u[:40], t)
        if key in seen:
            continue
        seen.add(key)
        print('  %-56s %s' % (u[:54], t))

print()
print('══ ② 用户组权限面（spacecp ac=usergroup）══')
ug = curl(BASE + '/home.php?mod=spacecp&ac=usergroup')
open('usergroup.html', 'w').write(ug)
t = txt(ug)
k = t.find('列兵')
print(' ', t[k:k + 1500] if k >= 0 else t[:1200])

print()
print('══ ③ 资源帖机制（挑选含售价的帖）══')
m = re.search(r'href="(thread-\d+-1-1\.html)"[^>]*>([^<]{0,160}售价[^<]{0,80})', home)
if not m:
    m = re.search(r'href="(thread-\d+-1-1\.html)"', home)
if m:
    u = BASE + '/' + m.group(1)
    title0 = m.group(2)[:80] if m.lastindex and m.lastindex >= 2 else ''
    print('  帖：', u)
    print('  题：', title0)
    th = curl(u)
    open('thread.html', 'w').write(th)
    tt = txt(th)
    for key in ('售价', '购买', '已购买', '下载', '权限不足', '大洋', '附件'):
        for mm in re.findall(re.escape(key) + r'[^ ]{0,46}', tt)[:3]:
            print('   [%s] %s' % (key, mm[:104]))

print()
print('══ ④ 移动版 / 热搜 / 其他入口 ══')
for mm in re.findall(r'href="([^"]{0,80}mobile[^"]{0,40})"[^>]*>([^<]{0,16})', home)[:5]:
    print('  mobile:', mm)
j = txt(home)
k2 = j.find('热搜')
print('  热搜:', j[k2:k2 + 120] if k2 >= 0 else 'n/a')

print()
print('══ ⑤ CF 敏感路径矩阵 ══')
paths = [
    ('/', '首页'), ('/admin.php', '管理后台'), ('/search.php', '搜索页'),
    ('/attachment.php', '附件下载'), ('/api/mobile/index.php', 'App API'),
    ('/uc_server/', 'UCenter 根'), ('/uc_server/admin.php', 'UCenter 管理'),
    ('/home.php?mod=medal', '勋章'), ('/home.php?mod=task', '任务'),
    ('/misc.php?mod=stat', '统计'),
    ('/dsu_paulsign-sign.html', '签到(对照)'),
    ('/config/config_global.php', '配置文件'),
    ('/install/', '安装目录'),
    ('/robots.txt', 'robots'),
]
for p, name in paths:
    out = subprocess.run(
        ['curl', '-s', '-A', UA, '-b', JAR, '--max-time', '30', '-w', '\n@@%{http_code}',
         '-D', 'cnlh.txt', '-o', 'cnlb.bin', BASE + p],
        capture_output=True, text=True).stdout
    code = out.strip().split('@@')[-1] if '@@' in out else '?'
    hdr = ''
    try:
        hdr = open('cnlh.txt', errors='ignore').read()
    except Exception:
        pass
    cf = 'cf!' if 'cf-mitigated' in hdr.lower() else '  '
    b = ''
    try:
        b = open('cnlb.bin', errors='ignore').read()[:6000]
    except Exception:
        pass
    ti = re.search(r'<title>([^<]{0,46})', b)
    print('  %-18s %-4s %s  %s' % (name, code, cf, (ti.group(1).strip() if ti else b[:40]).replace('\n', ' ')[:56]))

print()
print('══ ⑥ 搜索接口测试（一次只读搜索）══')
sp = curl(BASE + '/search.php')
mf = re.search(r'name="formhash" value="([0-9a-f]+)"', sp) or re.search(r'formhash=([0-9a-f]+)', sp)
fh = mf.group(1) if mf else ''
print('  formhash:', fh or '未取到')
if fh:
    r = subprocess.run(
        ['curl', '-s', '-A', UA, '-b', JAR, '--max-time', '35', '-X', 'POST',
         '--data', 'formhash=' + fh + '&srchtxt=%E5%8F%98%E5%BD%A2%E9%87%91%E5%88%9A&mod=forum&searchsubmit=yes',
         BASE + '/search.php'], capture_output=True, text=True).stdout
    tr = txt(r)
    print('  结果片段:', tr[:260])

print()
print('══ ⑦ 模板与静态资产 ══')
for mm in sorted(set(re.findall(r'(?:href|src)="(static/[^"]{4,60}|template/[^"]{4,60})"', home)))[:22]:
    print('  ', mm)
