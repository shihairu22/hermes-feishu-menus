#!/usr/bin/env python3
"""PT 会话备份 —— 把各站浏览器档案里的 cookies 备份到 ~/pt_session_backup_<时间戳>。

用法：
    python3 pt_backup_sessions.py              # 备份到新时间戳目录
    python3 pt_backup_sessions.py --keep 5     # 提示哪些旧备份可清理（不会自动删）

为什么必须做：
    「图形验证码 + 强制 2FA」的站点（如 U2）一旦登出就极难登回来。
    U2 实测：cookie 有效期 ~400 天，直接从备份恢复 cookies.sqlite 就能免登录进站
    （不用验证码、不用动态码）。所以「每次登录成功后立刻备份」= 把登录成本
    摊平成「一次登录终身可恢复」。

铁律：不要删备份！删前先确认目标站能正常登录。
"""
import os
import re
import shutil
import sys
import time

ROOT = '/root'
STAMP = time.strftime('%Y%m%d_%H%M%S')
DEST = os.path.join(ROOT, 'pt_session_backup_%s' % STAMP)

SCAN_DIRS = [os.path.expanduser('~/.pt-sessions'), '/tmp', '/root', os.path.expanduser('~/.hermes/cache/documents')]
# 档案目录名关键字；父目录命中即向下看一层（子目录只要含 cookies.sqlite 就收）
NAME_RE = re.compile(r'(session|login|profile|camoufox|browser|keepalive)', re.I)
# 档案内部的子目录，不是独立档案（否则一个 profile 会被数两次）
EXCLUDE_SUB = {'sessionstore-backups', 'storage', 'cache2', 'datareporting',
               'safebrowsing', 'bookmarkbackups', 'security_state', 'extension-store'}
# 一个真正的火狐档案目录必须同时有这两个文件
PROFILE_MARKERS = ('cookies.sqlite', 'prefs.js')


def find_profiles():
    found = []
    for base in SCAN_DIRS:
        if not os.path.isdir(base):
            continue
        try:
            entries = os.listdir(base)
        except OSError:
            continue
        for name in entries:
            path = os.path.join(base, name)
            if not os.path.isdir(path) or not NAME_RE.search(name):
                continue
            candidates = [path]
            try:
                for sub in os.listdir(path):
                    sp = os.path.join(path, sub)
                    # 子目录不再过滤名字：只要里面有 cookies.sqlite 就算一个档案
                    # （历史案例：父目录名不含 session 关键字）
                    if os.path.isdir(sp) and sub.lower() not in EXCLUDE_SUB:
                        candidates.append(sp)
            except OSError:
                pass
            for c in candidates:
                # ★ 必须同时有 cookies.sqlite 和 prefs.js 才算一个火狐档案
                #   （否则 sessionstore-backups 这类内部目录会被当成独立档案，个数翻倍）
                if all(os.path.isfile(os.path.join(c, mk)) for mk in PROFILE_MARKERS):
                    found.append(c)
    return sorted(set(found))


def main():
    keep = None
    if '--keep' in sys.argv:
        try:
            keep = int(sys.argv[sys.argv.index('--keep') + 1])
        except (IndexError, ValueError):
            keep = None

    profiles = find_profiles()
    os.makedirs(DEST, exist_ok=True)
    n = 0
    for src in profiles:
        nm = os.path.basename(src.rstrip('/'))
        tag = nm if not os.path.exists(os.path.join(DEST, '%s__cookies.sqlite' % nm)) \
            else '%s_%d' % (nm, n)
        for suffix in ('cookies.sqlite', 'cookies.sqlite-wal'):
            s = os.path.join(src, suffix)
            if os.path.isfile(s):
                try:
                    shutil.copy2(s, os.path.join(DEST, '%s__%s' % (tag, suffix)))
                except OSError:
                    pass
        n += 1

    size = sum(os.path.getsize(os.path.join(DEST, f))
               for f in os.listdir(DEST) if os.path.isfile(os.path.join(DEST, f)))
    print('备份目录: %s' % DEST)
    print('站点档案: %d 个   总大小: %.1f MB' % (n, size / 1048576.0))

    if keep:
        backups = sorted(d for d in os.listdir(ROOT)
                         if d.startswith('pt_session_backup_') and
                         os.path.isdir(os.path.join(ROOT, d)))
        for old in backups[:-keep]:
            print('⚠️  建议手工确认后再删: %s' % os.path.join(ROOT, old))
    return 0


if __name__ == '__main__':
    sys.exit(main())
