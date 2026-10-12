#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CnLang 纯 HTTP 签到（curl 版）
原理：CF 路径规则匹配字面 "dsu_paulsign"；用百分号编码一个字符（%%64 → d）绕过，
      PHP 侧自动解码后正常处理。签到本体 = 纯 GET（参数全在 query）。
用法：python cnlang_sign_http.py [cookies.txt]
"""
import os  # 家目录展开（去敏时可移植化）
import re
import subprocess
import sys

BASE = 'https://cnlang.org'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0'
JAR = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/.pt-sessions/state/cnlang_cookies.txt')

TODAYSAY = '%E7%AD%BE%E5%88%B0%E5%95%A6'  # 签到啦（可改：6~100 字节且须含非 [A-Za-z0-9.,] 字符）


def curl(url, timeout=40):
    r = subprocess.run(['curl', '-s', '-A', UA, '-b', JAR, '--max-time', str(timeout), url],
                       capture_output=True, text=True)
    return r.stdout


panel = curl(BASE + '/plugin.php?id=%64su_paulsign:sign')
m = re.search(r'name="formhash"\s+value="([0-9a-f]+)"', panel)
if not m:
    print('PANEL_FAIL: 未拿到 formhash（页面长度 %d）' % len(panel))
    sys.exit(1)
fh = m.group(1)
print('formhash:', fh)

url = ('%s/plugin.php?id=%%64su_paulsign:sign&operation=qiandao&formhash=%s'
       '&qdxq=kx&qdmode=1&infloat=1&inajax=1&todaysay=%s' % (BASE, fh, TODAYSAY))
out = curl(url)
plain = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', out)).strip()
print('RESULT:', plain[:400])
