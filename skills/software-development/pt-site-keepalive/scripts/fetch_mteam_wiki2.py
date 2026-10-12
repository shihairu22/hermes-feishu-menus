#!/usr/bin/env python3
"""抓取 M-Team 官方 Wiki 全部页面（走 HTML 路径，GraphQL 只用来列目录）。

输出：~/safeline-research/wikis/M-Team-wiki.md
"""
import os  # 家目录展开（去敏时可移植化）
import html
import json
import re
import time
import urllib.request

GQL = 'https://wiki.m-team.cc/graphql'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36'


def gql(q):
    req = urllib.request.Request(
        GQL, data=json.dumps({'query': q}).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def get_html(path):
    url = 'https://wiki.m-team.cc/' + path.lstrip('/')
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=35) as r:
        return r.read().decode('utf-8', 'ignore')


def to_text(h):
    h = re.sub(r'(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>', '\n', h)
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    h = html.unescape(h)
    h = re.sub(r'[ \t\u00a0]+', ' ', h)
    h = re.sub(r'\n\s*\n+', '\n', h)
    return h.strip()


def main():
    d = gql('{pages{list{id,path,title,description,locale,updatedAt}}}')
    lst = d['data']['pages']['list']
    seen = set()
    pages = []
    for p in lst:
        if p['path'] in seen:
            continue
        seen.add(p['path'])
        pages.append(p)
    print('共 %d 页（去重后）' % len(pages))

    out = ['# M-Team 官方 Wiki 全文（wiki.m-team.cc）', '',
           '> 抓取：2026-09-28 · 语言 zh-tw · 共 %d 页' % len(pages),
           '> 目录来源：Wiki.js GraphQL · 正文来源：页面 HTML', '']
    ok = 0
    for i, p in enumerate(pages, 1):
        path = p['path']
        try:
            txt = to_text(get_html(path))
            out += ['', '=' * 72,
                    '## [%d] %s' % (i, p.get('title') or path),
                    '路径：/%s · 更新：%s' % (path, (p.get('updatedAt') or '')[:10])]
            if p.get('description'):
                out.append('摘要：%s' % p['description'])
            out += ['=' * 72, '', txt]
            ok += 1
            print('  [✓] %-3d %-34s %d 字' % (i, path[:34], len(txt)))
        except Exception as exc:
            print('  [✗] %-3d %-34s %s' % (i, path[:34], str(exc)[:60]))
        time.sleep(0.3)

    fp = os.path.expanduser('~/safeline-research/wikis/M-Team-wiki.md')
    body = '\n'.join(out)
    open(fp, 'w', encoding='utf-8').write(body)
    print()
    print('已落盘 %s（%d 页 / %d 字节）' % (fp, ok, len(body)))


main()
