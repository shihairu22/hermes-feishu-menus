#!/usr/bin/env python3
"""把抓到的各站 wiki 原文压缩成可读摘要。

对每站：抽取含关键词的句子（分享率/H&R/封禁/保号/魔力/邀请/考核/警告），
并按原文章节标题分组，输出 <site>.md。
"""
import glob
import json
import os
import re
import sys

WIKI_DIR = os.path.expanduser('~/safeline-research/wikis')
OUT_DIR = os.path.expanduser('~/safeline-research/wikis/digest')
os.makedirs(OUT_DIR, exist_ok=True)

KEYS = ['分享率', 'H&R', 'HR', 'Hit and Run', '封禁', '封号', '禁用帐号', '删除帐号',
        '不登录', '未登录', '无活动', '魔力', '邀请', '考核', '警告', '违规',
        '禁止', '必须', '不得', '上限', '下限', '下载量', '上传量', '做种',
        '申诉', '限制', 'VIP', '捐赠', '种子', '规则']

SECTION = re.compile(r'^(?:[0-9]+[\.、\)]\s*|[一二三四五六七八九十]+[、\.]\s*|[【\[].{1,20}[】\]]\s*|\S{1,30}(?:规则|規定|说明|說明|注意|警告|须知|須知)\s*$)')


def digest_site(path):
    site = os.path.basename(path)[:-5]
    d = json.load(open(path))
    out = ['# %s 规则摘要' % site, '',
           '> 来源：站点 rules.php / faq.php（2026-09-28 抓取）',
           '> 原文：`~/safeline-research/wikis/%s.json`' % site, '']
    for label, v in d.items():
        t = (v.get('text') or '')
        if len(t) < 40:
            out += ['', '## %s（未取到内容：%s）' % (label, (v.get('error') or v.get('title') or '')[:60])]
            continue
        out += ['', '## %s' % label, '']
        # 分句
        sents = re.split(r'(?<=[。！？；;])|\n', t)
        kept = []
        for s in sents:
            s = s.strip()
            if len(s) < 10 or len(s) > 400:
                continue
            if any(k in s for k in KEYS):
                kept.append(s)
        # 去重 + 限量
        seen = set()
        uniq = []
        for s in kept:
            k = s[:40]
            if k in seen:
                continue
            seen.add(k)
            uniq.append(s)
        for s in uniq[:120]:
            out.append('- %s' % s)
        out += ['', '（原文共 %d 字，摘出 %d 条）' % (len(t), len(uniq))]
    p = '%s/%s.md' % (OUT_DIR, site)
    open(p, 'w', encoding='utf-8').write('\n'.join(out))
    return site, len('\n'.join(out))


if __name__ == '__main__':
    files = sorted(glob.glob('%s/*.json' % WIKI_DIR))
    print('处理 %d 个站点文件' % len(files))
    for f in files:
        site, size = digest_site(f)
        print('  [✓] %-16s 摘要 %d 字节' % (site, size))
    print()
    print('摘要目录：%s' % OUT_DIR)
