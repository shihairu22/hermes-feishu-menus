#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CnLang CF 规则边界变体探测：编码 / 大小写 / 替代入口"""
import os  # 家目录展开（去敏时可移植化）
import json
import time

from camoufox.sync_api import Camoufox

PROFILE = os.path.expanduser('~/.pt-sessions/cnlang-login-session')
BASE = 'https://cnlang.org'

variants = [
    ('对照-正常页', '/home.php'),
    ('冒号编码', '/plugin.php?id=dsu_paulsign%3Asign'),
    ('首字符编码', '/plugin.php?id=%64su_paulsign:sign'),
    ('下划线编码', '/plugin.php?id=dsu%5Fpaulsign:sign'),
    ('大小写-首字大', '/plugin.php?id=Dsu_paulsign:sign'),
    ('大小写-混合', '/plugin.php?id=Dsu_Paulsign:sign'),
    ('大小写-全大', '/plugin.php?id=DSU_PAULSIGN:sign'),
    ('双斜杠', '//plugin.php?id=dsu_paulsign:sign'),
    ('html变体-大写', '/Dsu_Paulsign-Sign.html'),
    ('html变体-尾点', '/dsu_paulsign-sign.html.'),
    ('hack-qiandao', '/hack.php?H_name=qiandao'),
    ('hack-dsu', '/hack.php?H_name=dsu_paulsign'),
    ('源码目录', '/source/plugin/dsu_paulsign/sign.inc.php'),
]


def challeng(p):
    try:
        t = (p.title() or '').lower()
    except Exception:
        t = ''
    return ('just a moment' in t) or ('请稍候' in t) or ('请稍等' in t) or ('attention' in t)


with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=PROFILE,
              locale="zh-CN") as browser:
    page = browser.new_page()
    page.set_default_timeout(60000)
    page.goto(BASE + '/home.php', wait_until='domcontentloaded')
    for _ in range(20):
        time.sleep(3)
        if not challeng(page):
            break

    for name, path in variants:
        res = page.evaluate("""async ([url]) => {
            try {
                const r = await fetch(url, {credentials:'include'});
                const t = await r.text();
                return {status: r.status, cf: r.headers.get('cf-mitigated') || '',
                        ct: (r.headers.get('content-type') || '').slice(0, 30),
                        snip: t.replace(/\\s+/g, ' ').slice(0, 130)};
            } catch(e) { return {err: String(e).slice(0, 120)}; }
        }""", [BASE + path])
        print('== [%-14s] %-56s -> %s' % (name, path[:56], json.dumps(res, ensure_ascii=False)[:300]), flush=True)

    print('DONE', flush=True)
