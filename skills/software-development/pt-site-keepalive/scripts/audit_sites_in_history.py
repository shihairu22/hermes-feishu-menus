#!/usr/bin/env python3
"""审计：哪些 PT 站真的执行过登录/签到，哪些域名只是被提到过。

回答用户「之前还有哪些站你执行了但没加入清单」这类问题——不要凭记忆答，跑这个脚本。

用法（Hermes 主机上直接跑，纯标准库）：
    python3 scripts/audit_sites_in_history.py
    python3 scripts/audit_sites_in_history.py --db ~/.hermes/state.db

输出三段：
  1) 每个命中域名的总次数 + 出现在用户消息里的次数（user>0 = 用户真的提过）
  2) 其中带「登录/签到动作词」的域名（更像真的执行过）
  3) 不在 KNOWN 清单里的候选 —— 人工判读，别直接当成新站
另附 /tmp/*-login-session 目录列表：目录存在＝该站真的走完了登录流程，是最硬的证据。

判读规则见 SKILL.md「站点审计」一节：扫到域名 ≠ 跑过（可能只是在第三方脚本/模板配置/调研网页里读到过）；
别名与镜像域名（skyeysnow.com＝天雪、anime-no-index.com＝MonikaDesign Tracker、naudiences.me＝Audiences 镜像）不算新站。
"""

import argparse
import collections
import glob
import os
import re
import sqlite3
import sys

# SKILL.md 里已登记的站点（17 站 + 非 PT 的 CnLang）——新增站点后同步更新这里
KNOWN = {
    'm-team.cc', 'm-team.io', 'audiences.me', 'ourbits.club', 'keepfrds.com', 'hdsky.me',
    'piggo.me', 'ptchdbits.co', 'chdbits.co', 'ubits.club', 'hddolby.com', 'totheglory.im',
    'ttg.im', 'hdhome.org', 'open.cd', 'u2.dmhy.org', 'skyey2.com', 'skyeysnow.com',
    'monikadesign.uk', 'pthome.net', 'zhuque.in', 'cnlang.org', 'cnlang.me',
}

DOMAIN_RE = re.compile(
    r'\b((?:[a-z0-9][a-z0-9\-]{0,62}\.)+'
    r'(?:com|cc|me|club|org|net|im|uk|cd|co|in|top|xyz|info|tv|io|tw|cn|moe|pw|se|gg|bar|'
    r'dev|app|link|site|online|fun|space|store|one|life|pro|asia|nu|ws|biz))\b',
    re.I,
)
# 服务器响应里出现这些词，说明那条消息更可能是「真的执行过」而不是纯讨论
ACTION_WORDS = ('签到成功', '已签到', 'loggedIn": true', 'loggedin": true', '欢迎回来',
                '登录成功', '登陆成功', '签到得魔力', 'sign_in')
# 明显不是站点的域名噪音，检索时排除
NOISE = ('github', 'google', 'gstatic', 'telegram', 'cloudflare', 'docker', 'npmjs', 'python.org',
         'pypi.org', 'mozilla', 'w3.org', 'wikipedia', 'youtube', 'stackoverflow', 'shields.io',
         'readthedocs', 'discuz', 'greasyfork', 'csdn', 'baidu', 'gitee', 'aliyun', 'tencent',
         'jsdelivr', 'unpkg', 'sqlite.org', 'debian.org', 'openssh.com', 'nousresearch')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=os.path.expanduser('~/.hermes/state.db'))
    ap.add_argument('--limit', type=int, default=150)
    ap.add_argument('--include-tool', action='store_true',
                    help='把 role=tool 的消息也算进「用户提过」（默认只统计 user 消息）')
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print('会话库不存在: %s' % args.db)
        return 1

    con = sqlite3.connect(args.db)
    rows = con.execute('SELECT role, content FROM messages').fetchall()
    print('会话消息数: %d' % len(rows))

    total = collections.Counter()
    user = collections.Counter()
    act = collections.Counter()
    for role, content in rows:
        if not content:
            continue
        low = content.lower()
        domains = set(DOMAIN_RE.findall(low))
        if not domains:
            continue
        has_action = any(w.lower() in low for w in ACTION_WORDS)
        for d in domains:
            total[d] += 1
            if role == 'user':
                user[d] += 1
            if has_action:
                act[d] += 1

    def is_known(d):
        return any(k in d for k in KNOWN)

    def is_noise(d):
        return any(n in d for n in NOISE)

    print('\n== 1) 站域名命中（user>0 表示用户真的提过）==')
    for d, c in total.most_common(args.limit):
        if not user[d] or is_noise(d):
            continue
        tag = 'KNOWN' if is_known(d) else '*** NOT-IN-LIST ***'
        print('%-34s total:%-5d user:%-4d action:%-4d %s' % (d, c, user[d], act[d], tag))

    print('\n== 2) 待人工判读：出现的、带动作词、但不在 KNOWN 清单里 ==')
    cand = [(d, total[d], act[d]) for d in total
            if act[d] and not is_known(d) and not is_noise(d)]
    for d, c, a in sorted(cand, key=lambda x: -x[1])[:args.limit]:
        print('%-34s total:%-5d action:%-4d  ← 核实是否只是读到过（第三方脚本/模板/调研页）' % (d, c, a))
    if not cand:
        print('(无)')

    print('\n== 3) 持久登录会话目录（存在＝真的走完了登录）==')
    sessions = sorted(glob.glob('/tmp/*-login-session*'))
    for s in sessions:
        print('  %s' % s)
    if not sessions:
        print('  (无)')

    print('\n提示：本机站点脚本可用 `ls ~/*.py`, `ls ~/*.sh`, `grep -rl <域名> /root /tmp` 交叉核对。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
