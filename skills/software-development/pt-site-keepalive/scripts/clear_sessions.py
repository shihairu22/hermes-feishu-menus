#!/usr/bin/env python3
"""PT 站会话备份 / 清空 —— 用于「清掉所有 cookie 从零跑一遍」的全新测试。

做法：
  1. 把每个浏览器 profile 的 cookies.sqlite* 与纯脚本站的 cookie/state 文件全部复制到
     备份目录（默认 ~/pt_session_backup_<时间戳>/），并写一个 MANIFEST.txt；
  2. 删除原文件（即模拟 cookie 到期）；
  3. 回滚：把备份目录里的文件按 MANIFEST 拷回去（--restore <备份目录>）。

★ 2026-09-30 改为「自动发现」：不再维护写死的 profile 清单（曾因站点搬家连续两次漏站），
  改为扫描 ~/.pt-sessions/ 下所有含 cookies.sqlite* 的档案目录 + state/ 与各处兜底路径。

用法：
  python3 clear_sessions.py --backup          # 备份 + 清空
  python3 clear_sessions.py --list            # 只看现状，不动
  python3 clear_sessions.py --restore ~/pt_session_backup_20260930_xxxxxx
"""
import os, sys, glob, shutil, time

def targets():
    out = []
    # 1) 浏览器档案：~/.pt-sessions/ 下所有含 cookies.sqlite* 的目录（自动发现，防清单过时）
    for prof in glob.glob(os.path.expanduser('~/.pt-sessions/*/')):
        out += glob.glob(os.path.join(prof, 'cookies.sqlite*'))
    # 1b) /tmp 下老式档案目录，兜底（新档案统一在 ~/.pt-sessions/）
    for prof in glob.glob('/tmp/*-login-session/'):
        out += glob.glob(os.path.join(prof, 'cookies.sqlite*'))
    # 2) 纯脚本站的 cookie / state 文件：统一位置 ~/.pt-sessions/state/ + /tmp 兜底
    for pat in (os.path.expanduser('~/.pt-sessions/state/*cookies*.txt'), os.path.expanduser('~/.pt-sessions/state/*cookies*.json'),
                os.path.expanduser('~/.pt-sessions/state/*state*.json'),
                '/tmp/*cookies*.txt', '/tmp/*state*.json', '/tmp/*_cookies.txt'):
        out += glob.glob(pat)
    # 3) 明确路径兜底
    for p in ('/tmp/discfan_cookies.txt',):
        if os.path.exists(p):
            out.append(p)
    return sorted(set(out))

mode = sys.argv[1] if len(sys.argv) > 1 else '--list'
files = targets()

if mode == '--list':
    print('共 %d 个会话文件：' % len(files))
    for f in files:
        print('   %-72s %8d 字节' % (f, os.path.getsize(f)))
    sys.exit(0)

if mode == '--restore':
    bdir = sys.argv[2]
    man = os.path.join(bdir, 'MANIFEST.txt')
    n = 0
    for line in open(man):
        src, dst = line.rstrip('\n').split('\t')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(bdir, src), dst)
        n += 1
    print('✅ 已从 %s 回滚 %d 个文件' % (bdir, n))
    sys.exit(0)

# --backup
bdir = os.path.expanduser('~/pt_session_backup_%s') % time.strftime('%Y%m%d_%H%M%S')
os.makedirs(bdir, exist_ok=True)
man = []
for i, f in enumerate(files):
    flat = '%03d_%s' % (i, os.path.basename(f))
    shutil.copy2(f, os.path.join(bdir, flat))
    man.append('%s\t%s' % (flat, f))
open(os.path.join(bdir, 'MANIFEST.txt'), 'w').write('\n'.join(man) + '\n')
print('✅ 已备份 %d 个文件 → %s' % (len(files), bdir))

removed = 0
for f in files:
    try:
        os.remove(f)
        removed += 1
    except Exception as e:
        print('   ⚠ 删除失败 %s: %s' % (f, e))
print('✅ 已清除 %d 个会话文件（cookie 已空，等效于 cookie 到期）' % removed)
print('   回滚命令：python3 %s --restore %s' % (os.path.abspath(__file__), bdir))
