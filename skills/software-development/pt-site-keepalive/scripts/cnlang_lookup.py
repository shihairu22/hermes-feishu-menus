#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CnLang 一键查片/查资源 v2（修正解析：li.pbw + viewthread 结构）
用法: python3 cnlang_lookup.py "关键词" [--n 10] [--detail N] [--fresh]
"""
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

BASE = 'https://cnlang.org'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0'
JAR = os.path.expanduser('~/.hermes/cache/scratch/cnlang_cookies.txt')
CACHE = os.path.expanduser('~/.hermes/cache/scratch/cnlang_cache.json')


def curl(u, post=None, follow=False):
    args = ['curl', '-s', '-A', UA, '-b', JAR, '--max-time', '40']
    if follow:
        args.append('-L')
    if post:
        args += ['-X', 'POST', '--data', post]
    args.append(u)
    return subprocess.run(args, capture_output=True, text=True).stdout


def clean(s):
    s = re.sub(r'<[^>]+>', '', s)
    return re.sub(r'\s+', ' ', html.unescape(s)).strip()


def textify(h):
    h = re.sub(r'<script[\s\S]*?</script>', ' ', h)
    h = re.sub(r'<style[\s\S]*?</style>', ' ', h)
    h = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', html.unescape(h)).strip()


kw = sys.argv[1] if len(sys.argv) > 1 else ''
n, detail = 10, 0
fresh = '--fresh' in sys.argv
for i, a in enumerate(sys.argv):
    if a == '--n' and i + 1 < len(sys.argv):
        n = int(sys.argv[i + 1])
    if a == '--detail' and i + 1 < len(sys.argv):
        detail = int(sys.argv[i + 1])
if not kw:
    print('用法: cnlang_lookup.py "关键词" [--n 10] [--detail N] [--fresh]')
    sys.exit(1)

cache = {}
if os.path.exists(CACHE):
    try:
        cache = json.load(open(CACHE))
    except Exception:
        cache = {}

now = time.time()
ent = cache.get(kw)
if ent and not fresh and now - ent.get('ts', 0) < 6 * 3600 and ent.get('results'):
    results = ent['results']
    print('（缓存：%d 分钟前的搜索结果）' % int((now - ent['ts']) / 60))
else:
    page = curl(BASE + '/search.php')
    m = re.search(r'name="formhash" value="([0-9a-f]+)"', page)
    fh = m.group(1) if m else ''
    if not fh:
        print('formhash 获取失败（会话可能过期）→ 先跑 cnlang_login.py 重登')
        sys.exit(2)
    post = 'formhash=%s&srchtxt=%s&mod=forum&searchsubmit=yes' % (fh, urllib.parse.quote(kw))
    h = curl(BASE + '/search.php?searchsubmit=yes', post=post, follow=True)
    results = []
    seen = set()
    for ch in h.split('<li class="pbw"')[1:]:
        mtid = re.search(r'^[^>]*id="(\d+)"', ch)
        a = re.search(r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', ch)
        if not (mtid and a):
            continue
        tid = mtid.group(1)
        if tid in seen:
            continue
        seen.add(tid)
        meta = re.search(r'<p class="xg1">([^<]*)</p>', ch)
        date = re.search(r'<span>([^<]{6,20})</span>', ch)
        author = re.search(r'space-uid-\d+\.html"[^>]*>([^<]+)</a>', ch)
        forum = re.search(r'class="xi1">([^<]+)</a>', ch)
        results.append({
            'tid': tid,
            'title': clean(a.group(2))[:160],
            'meta': (meta.group(1).strip() if meta else ''),
            'date': (date.group(1).strip() if date else ''),
            'author': (author.group(1).strip() if author else ''),
            'forum': (forum.group(1).strip() if forum else ''),
        })
    if results:
        cache[kw] = {'ts': now, 'results': results}
        json.dump(cache, open(CACHE, 'w'), ensure_ascii=False, indent=1)
    print('（新搜索：%d 条结果）' % len(results))

print('══ 搜索「%s」══' % kw)
for i, r in enumerate(results[:n]):
    print('%2d. [%s] %s' % (i + 1, r['forum'] or '?', r['title']))
    print('      %s ｜ %s ｜ %s ｜ tid=%s' % (r['meta'], r['date'], r['author'], r['tid']))

if detail:
    if detail < 1 or detail > len(results):
        print('detail 序号超出范围')
        sys.exit(1)
    r = results[detail - 1]
    th = curl(BASE + '/thread-%s-1-1.html' % r['tid'])
    tt = textify(th)
    ti = re.search(r'<span id="thread_subject">([^<]+)', th)
    price = re.search(r'本主题需向作者支付 ?<strong>(\d+) 大洋</strong>', th)
    buys = re.search(r'已有 ?(\d+) ?人购买', th)
    atts = sorted(set(re.findall(r'aid=(\d+)', th)))
    files = sorted(set(re.findall(r'>([^<>]{3,70}\.(?:sup|ass|srt|ac3|dts|thd|eac3|mka|m4a|flac|wav|mkv|torrent|zip|rar|7z))<', th, re.I)))
    keys = [k for k in ('TrueHD', 'DTS-HD', 'DTS:X', 'Atmos', 'DD5.1', 'DD2.0', 'HDR', 'SDR', '重混', '上译', '长译', '央视', '中影', '东影', '台配', '辽艺', '德加拉', '华录') if k in tt]
    ext = sorted(set(re.findall(r'(pan\.baidu\.com[^\s"<]{0,40}|115\.com[^\s"<]{0,30}|aliyundrive[^\s"<]{0,30}|magnet:[^"<\s]{0,60}|ed2k:[^"<\s]{0,60})', th)))[:6]
    pdate = re.search(r'<em id="authorposton\d+">([^<]+)', th)
    print()
    print('── 详情 thread-%s ──' % r['tid'])
    print('标题:', ti.group(1) if ti else r['title'])
    print('发帖:', clean(pdate.group(1)) if pdate else '?')
    print('售价:', (('付费 %s 大洋（%s 人已购）' % (price.group(1), buys.group(1) if buys else '?')) if price else '免费/无主题售价'))
    print('附件:', ('、'.join(files[:12]) if files else ('aid=' + '/'.join(atts[:8]) if atts else '无（可能外链）')))
    print('规格:', '、'.join(keys) if keys else '未识别关键词')
    if ext:
        print('外链前 6:', ' | '.join(ext))
