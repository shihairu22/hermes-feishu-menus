#!/usr/bin/env python3
"""把 API 扫描结果（scripts/pt_api_scan2.py 的产物）整理成可读档案。

读 ~/safeline-research/apis/*.json
输出 ~/safeline-research/apis/<site>.md + SUMMARY.md
"""
import glob
import json
import os
import re

INDIR = os.path.expanduser('~/safeline-research/apis')

GROUPS = [
    ('登录/认证', r'login|logout|auth|session|token|signin|sign-in|register|verify|captcha|2fa|otp|passkey'),
    ('签到/考勤', r'attend|sign|checkin|check-in|qiandao|bakatest|签到'),
    ('种子/资源', r'torrent|detail|download|upload|seed|peer|search|browse|catalog'),
    ('用户/资料', r'user|member|profile|account|usercp|mybonus|bonus|invite|message|pm|notify'),
    ('游戏/娱乐', r'gaming|game|draw|lottery|bet|blackjack|wheel|prize|card|magic|artifact|bounty'),
    ('论坛/社区', r'forum|post|comment|thread|topic|shout|chat'),
    ('管理/统计', r'admin|stat|rank|log|report|staff|sys'),
]


def categorize(path):
    low = path.lower()
    for name, pat in GROUPS:
        if re.search(pat, low):
            return name
    return '其他'


def clean(paths):
    out = set()
    for p in paths:
        p = (p or '').strip()
        if len(p) < 3 or len(p) > 200:
            continue
        if re.search(r'\.(png|jpg|jpeg|gif|svg|woff2?|ttf|eot|ico|css|map)(\?|$)', p, re.I):
            continue
        if re.search(r'(cdn|static|assets|node_modules|webpack|chunk)', p, re.I):
            continue
        out.add(p)
    return sorted(out)


def main():
    files = sorted(glob.glob('%s/*.json' % INDIR))
    if not files:
        print('还没有扫描结果')
        return
    summary = ['# 各站 API / 前端代码总览', '',
               '> 数据源：各站首页 + 真实网络流量（scripts/pt_api_scan2.py）', '']
    for f in files:
        d = json.load(open(f))
        site = d.get('site') or os.path.basename(f)[:-5]
        api = clean(d.get('api') or [])
        php = clean(d.get('php') or [])
        fetch = clean(d.get('fetch') or [])
        routes = clean(d.get('routes') or [])
        hosts = clean(d.get('hosts') or [])
        calls = d.get('calls') or []
        fp = d.get('fingerprints') or []

        out = ['# %s —— API / 前端代码' % site, '',
               '- 首页：%s' % d.get('home', ''),
               '- 技术指纹：%s' % ('、'.join(fp) if fp else '（未识别）'),
               '- JS 资源：%d 个' % len(d.get('assets_js') or d.get('assets') or []),
               '- 访问页面：%d 个' % len(d.get('pages') or []),
               '- 提取到：API %d 条 · PHP %d 条 · 请求调用 %d 条 · 前端路由 %d 条'
               % (len(api), len(php), len(fetch), len(routes)), '']

        if fp:
            out += ['## 技术栈指纹', ''] + ['- %s' % x for x in fp] + ['']

        if calls:
            out += ['## 真实接口调用（%d）' % len(calls), '']
            for c in calls:
                out.append('- `%s %s`  [%s]' % (c.get('method'), c.get('url'), c.get('type')))
                if c.get('post'):
                    out.append('  - post: `%s`' % str(c['post'])[:200].replace('\n', ' '))
            out += ['']

        if api:
            out += ['## API 路径（%d）' % len(api), '']
            g = {}
            for p in api:
                g.setdefault(categorize(p), []).append(p)
            for k in sorted(g):
                out += ['### %s（%d）' % (k, len(g[k]))]
                out += ['- `%s`' % x for x in g[k][:60]]
                out += ['']

        if php:
            out += ['## PHP 端点（%d）' % len(php), '']
            out += ['- `%s`' % x for x in php[:80]] + ['']

        if fetch:
            out += ['## JS 里的请求调用（%d）' % len(fetch), '']
            out += ['- `%s`' % x for x in fetch[:60]] + ['']

        if routes:
            out += ['## 前端路由（%d）' % len(routes), '']
            out += ['- `%s`' % x for x in routes[:80]] + ['']

        if hosts:
            out += ['## 出现的域名（%d）' % len(hosts), '']
            out += ['- %s' % x for x in hosts[:40]] + ['']

        if d.get('errors'):
            out += ['## 抓取异常', ''] + ['- %s' % x for x in d['errors'][:10]] + ['']

        body = '\n'.join(out)
        open('%s/%s.md' % (INDIR, site), 'w', encoding='utf-8').write(body)
        print('  [✓] %-14s API %3d · PHP %3d · 路由 %3d · %d 字节'
              % (site, len(api), len(php), len(routes), len(body)))

        summary.append('| %s | %s | %d | %d | %d | %d |'
                       % (site, '、'.join(fp[:3]) or '-', len(api), len(php),
                          len(calls), len(routes)))

    if len(summary) > 3:
        summary.insert(4, '')
        summary.insert(5, '| 站点 | 技术指纹 | API | PHP | 真实调用 | 路由 |')
        summary.insert(6, '|---|---|---|---|---|---|')
    open('%s/SUMMARY.md' % INDIR, 'w', encoding='utf-8').write('\n'.join(summary))
    print()
    print('总览：%s/SUMMARY.md' % INDIR)


main()
