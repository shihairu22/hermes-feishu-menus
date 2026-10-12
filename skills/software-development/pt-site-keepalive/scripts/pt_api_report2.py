#!/usr/bin/env python3
"""把 API 扫描 v2 结果（真实网络流量）整理成可读档案。

读 ~/safeline-research/apis/*.json（v2 结构：calls/pages/hosts/assets_js/fingerprints）
输出 每站 <site>.md + SUMMARY.md
"""
import glob
import json
import os
import re

INDIR = os.path.expanduser('~/safeline-research/apis')

GROUPS = [
    ('API 接口（REST/JSON）', r'/(api|apis|api/v\d|graphql|rpc|rest)(/|\?|$)'),
    ('动态请求（XHR/fetch）', None),
    ('认证/会话', r'login|logout|auth|session|token|signin|verify|captcha|2fa|otp'),
    ('签到', r'attend|sign|checkin|check-in|qiandao|bakatest'),
    ('种子', r'torrent|detail|download|upload|seed|peer|search|browse'),
    ('用户', r'user|member|profile|account|usercp|bonus|invite|message|notify'),
    ('游戏/娱乐', r'gaming|game|draw|lottery|bet|blackjack|wheel|prize|card|magic|artifact|bounty|chat'),
    ('论坛', r'forum|post|comment|thread|topic|shout'),
]

TAG = {
    'xhr': 'XHR', 'fetch': 'fetch', 'document': '文档', 'script': 'JS',
    'stylesheet': 'CSS', 'image': '图片', 'font': '字体', 'other': '其他',
    'media': '媒体', 'websocket': 'WS', 'manifest': '清单',
}


def is_api(u):
    return bool(re.search(r'/(api|apis|api/v\d|graphql|rpc|rest)(/|\?|$)', u, re.I))


def main():
    files = sorted(glob.glob('%s/*.json' % INDIR))
    if not files:
        print('无数据')
        return
    rows = []
    for f in files:
        d = json.load(open(f))
        site = d.get('site') or os.path.basename(f)[:-5]
        calls = d.get('calls') or []
        pages = d.get('pages') or []
        hosts = d.get('hosts') or []
        js = d.get('assets_js') or []
        fp = d.get('fingerprints') or []
        api_calls = [c for c in calls if is_api(c['url'])]

        out = ['# %s —— API / 前端代码档案' % site, '',
               '- 首页：%s' % d.get('home', ''),
               '- **技术指纹**：%s' % ('、'.join(fp) if fp else '（未识别）'),
               '- 访问页面：%d 个' % len(pages),
               '- 捕获动态调用：%d 条（其中 **REST API %d 条**）' % (len(calls), len(api_calls)),
               '- JS 资源：%d 个' % len(js), '']

        if fp:
            out += ['## 一、技术栈指纹', ''] + ['- %s' % x for x in fp] + ['']

        if pages:
            out += ['## 二、扫描时访问的页面', '']
            for p in pages:
                out += ['- `%s`' % p['url'][:110] + ('  — %s' % p['title'][:50] if p.get('title') else '')]
            out += ['']

        if api_calls:
            out += ['## 三、★ REST API 接口（%d 条）' % len(api_calls), '']
            g = {}
            for c in api_calls:
                for name, pat in GROUPS:
                    if pat and re.search(pat, c['url'], re.I):
                        g.setdefault(name, []).append(c)
                        break
                else:
                    g.setdefault('其他接口', []).append(c)
            for k in g:
                out += ['### %s（%d）' % (k, len(g[k]))]
                for c in g[k]:
                    out += ['- `%s %s`' % (c['method'], c['url'][:120])]
                    if c.get('post'):
                        out += ['  - post: `%s`' % c['post'][:150].replace('\n', ' ')]
                out += ['']
        else:
            out += ['## 三、REST API 接口', '',
                    '**未捕获到 REST API。**（该站为服务端渲染，无独立 API 层；'
                    '「接口」即 PHP/HTML 端点）', '']

        if calls:
            out += ['## 四、全部动态调用（%d 条）' % len(calls), '']
            for c in calls[:80]:
                out += ['- `%s` [%s] `%s`' % (c['method'], TAG.get(c['type'], c['type']), c['url'][:130])]
            if len(calls) > 80:
                out += ['- …（还有 %d 条，见原始 JSON）' % (len(calls) - 80)]
            out += ['']

        if hosts:
            out += ['## 五、出现的域名（按请求数）', '']
            for h in hosts[:20]:
                if isinstance(h, (list, tuple)) and len(h) == 2:
                    out += ['- `%s` — %s 次' % (h[0], h[1])]
                else:
                    out += ['- `%s`' % h]
            out += ['']

        if js:
            out += ['## 六、JS 资源（%d 个）' % len(js), '']
            for u in js[:30]:
                out += ['- `%s`' % u[:130]]
            out += ['']

        if d.get('errors'):
            out += ['## 七、抓取异常', ''] + ['- %s' % x for x in d['errors'][:10]] + ['']

        open('%s/%s.md' % (INDIR, site), 'w', encoding='utf-8').write('\n'.join(out))
        print('  [✓] %-14s 页%2d 调用%3d API%3d | %s'
              % (site, len(pages), len(calls), len(api_calls), '、'.join(fp[:3])))
        rows.append((site, fp, len(pages), len(calls), len(api_calls), len(js)))

    # 总览
    s = ['# 29 站 API / 前端代码总览', '',
         '> 2026-09-28 扫描 · 数据源：真实浏览器网络流量（22 站有档案）', '',
         '| 站点 | 技术指纹 | 访问页 | 动态调用 | REST API | JS |',
         '|---|---|---|---|---|---|']
    for site, fp, np_, nc, na, nj in rows:
        s.append('| %s | %s | %d | %d | **%d** | %d |'
                 % (site, '、'.join(fp[:3]) or '-', np_, nc, na, nj))
    s += ['', '## 关键结论', '',
          '- **只有极少站点有 REST API**：朱雀（TNode）、MonikaDesign（UNIT3D/Laravel）、',
          '  M-Team（带 `_sgin` 签名）、OurBits（独立域 `api.ourhelp.club`）、',
          '  SunnyPT（Next.js）、BYR（Vue）、PigGo/UBits 的 wiki（Wiki.js GraphQL）。',
          '- **NexusPHP 系（占 71%）没有 REST API**：服务端渲染 PHP，',
          '  「接口」就是 `*.php` 端点（`takelogin.php` / `attendance.php` / `bakatest.php` …）。',
          '- **天雪** 是 Discuz!（`forum.php?mod=…`）。**TTG** 是自研框架（仅 jQuery）。',
          '- 详细数据：`apis/<site>.json`（原始）与 `apis/<site>.md`（可读）。']
    open('%s/SUMMARY.md' % INDIR, 'w', encoding='utf-8').write('\n'.join(s))
    print()
    print('总览：%s/SUMMARY.md' % INDIR)


main()
