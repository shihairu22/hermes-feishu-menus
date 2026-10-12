#!/usr/bin/env python3
"""朱雀（zhuque.in）每日游戏化动作：释放角色技能得灵石。

依据 references/zhuque.md：
  GET  /api/gaming/listGenshinCharacter        角色列表（含 next_time 冷却）
  POST /api/gaming/fireGenshinCharacterMagic   {all:1, resetModal:true} 批量释放
注意：技能 3/4 释放后不更新 next_time，所以只用 all:1 批量接口，不做遍历等待。
"""
import os  # 家目录展开（去敏时可移植化）
import json
import re

from camoufox.sync_api import Camoufox

API = 'https://zhuque.in'

with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True,
              user_data_dir=os.path.expanduser('~/.pt-sessions/zhuque-login-session')) as browser:
    page = browser.new_page()
    print('① 打开首页确认登录态…', flush=True)
    page.goto(API + '/index', wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(6000)
    t = re.sub(r'\s+', ' ', page.evaluate('() => (document.body && document.body.innerText) || ""'))
    logged = '退出' in t or '灵石系统' in t
    print('   登录态: %s' % ('✅ 已登录' if logged else '❌ 未登录'), flush=True)
    if not logged:
        raise SystemExit(1)

    csrf = page.evaluate("""() => {
        const m = document.querySelector('meta[name=\"x-csrf-token\"]');
        return m ? m.getAttribute('content') : '';
    }""")
    print('   CSRF: %s' % (csrf[:12] + '...' if csrf else '（未取到）'), flush=True)

    print('② 取角色列表…', flush=True)
    r1 = page.evaluate("""async (csrf) => {
        const r = await fetch('/api/gaming/listGenshinCharacter', {
            credentials: 'include',
            headers: csrf ? {'x-csrf-token': csrf} : {}
        });
        return await r.text();
    }""", csrf)
    try:
        j1 = json.loads(r1)
    except Exception:
        print('   解析失败: %s' % r1[:200], flush=True)
        raise SystemExit(1)
    d1 = j1.get('data') or {}
    chars = d1.get('characters') if isinstance(d1, dict) else (d1 or [])
    chars = chars or []
    print('   角色数: %d' % len(chars), flush=True)
    import time as _t
    ready = 0
    for c in chars:
        info = c.get('info') or {}
        nt = info.get('next_time') or 0
        left = int(nt) - int(_t.time())
        flag = '✓ 可释放' if left <= 0 else '冷却中 %.1fh' % (left / 3600.0)
        if left <= 0:
            ready += 1
        print('     %-16s rank=%s lv=%-3s magic=%s  %s' % (
            str(c.get('name'))[:16], c.get('rank'), info.get('level'), c.get('magic'), flag), flush=True)
    print('   可释放角色: %d / %d' % (ready, len(chars)), flush=True)

    print('③ 批量释放技能（all:1）…', flush=True)
    r2 = page.evaluate("""async (csrf) => {
        const h = {'Content-Type': 'application/json'};
        if (csrf) h['x-csrf-token'] = csrf;
        const r = await fetch('/api/gaming/fireGenshinCharacterMagic', {
            method: 'POST', credentials: 'include', headers: h,
            body: JSON.stringify({all: 1, resetModal: true})
        });
        return await r.text();
    }""", csrf)
    print('   返回: %s' % r2[:400], flush=True)

    print('④ 复查灵石与冷却…', flush=True)
    page.wait_for_timeout(3000)
    r3 = page.evaluate("""async (csrf) => {
        const h = csrf ? {'x-csrf-token': csrf} : {};
        const r = await fetch('/api/gaming/listGenshinCharacter', {credentials: 'include', headers: h});
        return await r.text();
    }""", csrf)
    try:
        j3 = json.loads(r3)
        d3 = j3.get('data') or {}
        cs = d3.get('characters') if isinstance(d3, dict) else (d3 or [])
        cs = cs or []
        cooling = [c for c in cs if (c.get('info') or {}).get('next_time', 0) > __import__('time').time()]
        print('   角色 %d 个，其中 %d 个仍在冷却' % (len(cs), len(cooling)), flush=True)
    except Exception:
        print('   复查解析失败', flush=True)

    t2 = re.sub(r'\s+', ' ', page.evaluate('() => (document.body && document.body.innerText) || ""'))
    m = re.search(r'灵石[^0-9]{0,12}([\d,\.]+)', t2)
    if m:
        print('   当前灵石: %s' % m.group(1), flush=True)
    page.screenshot(path='/tmp/zhuque_gaming_after.png')
