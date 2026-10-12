#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 Camoufox(Firefox) profile 导出 cnlang.org cookie 为 Netscape 格式"""
import os  # 家目录展开（去敏时可移植化）
import sqlite3

prof = os.path.expanduser('~/.pt-sessions/cnlang-login-session')
con = sqlite3.connect(prof + '/cookies.sqlite')
out = []
names = []
for host, name, value, path, expiry, secure, honly in con.execute(
        "SELECT host,name,value,path,expiry,isSecure,isHttpOnly FROM moz_cookies WHERE host LIKE '%cnlang.org%'"):
    flag = 'TRUE' if str(host).startswith('.') else 'FALSE'
    sec = 'TRUE' if secure else 'FALSE'
    out.append('\t'.join([str(host), flag, str(path), sec, str(int(expiry) if expiry else 0), str(name), str(value)]))
    names.append('%s(len=%d)' % (name, len(str(value))))
open(os.path.expanduser('~/.pt-sessions/state/cnlang_cookies.txt'), 'w').write('# Netscape HTTP Cookie File\n' + '\n'.join(out) + '\n')
print('导出 %d 条：%s' % (len(out), ', '.join(names)))
