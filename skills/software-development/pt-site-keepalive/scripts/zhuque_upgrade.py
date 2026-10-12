#!/usr/bin/env python3
"""朱雀角色升级 —— 分阶段：先读状态，再只升 1 级做验证。

阶段 A（只读）：灵石余额 + 16 个未升级角色的现状
阶段 B（写）：只对第 1 个未升级角色执行 +1 级，前后对比余额
"""
import json
import os
import sys

from camoufox.sync_api import Camoufox

PROF = os.path.expanduser('~/.pt-sessions/zhuque-login-session')
STAGE = os.environ.get('ZQ_STAGE', 'A')          # A=只读, B=升一级, C=批量
TARGET = int(os.environ.get('ZQ_TARGET', '0'))   # C 阶段的目标等级

with Camoufox(headless=False, os="windows", humanize=True, persistent_context=True,
              user_data_dir=PROF) as browser:
    page = browser.new_page()
    page.goto('https://zhuque.in/index', wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(7000)
    csrf = page.evaluate("""() => { const m = document.querySelector('meta[name="x-csrf-token"]');
                                    return m ? m.getAttribute('content') : ''; }""")
    print('CSRF: %s' % (csrf[:12] + '…' if csrf else '（未取到）'), flush=True)

    def api(path, method='GET', body=None):
        r = page.evaluate("""async (a) => {
            const h = {'Content-Type': 'application/json'};
            if (a.csrf) h['x-csrf-token'] = a.csrf;
            const r = await fetch(a.path, {method: a.method, credentials: 'include', headers: h,
                                           body: a.body ? JSON.stringify(a.body) : undefined});
            return r.status + '|' + (await r.text());
        }""", {'path': path, 'method': method, 'body': body, 'csrf': csrf})
        st, _, txt = r.partition('|')
        try:
            return int(st), json.loads(txt)
        except Exception:
            return st, txt

    # ---- 状态 ----
    st, j = api('/api/gaming/listGenshinCharacter')
    chars = (j.get('data') or {}).get('characters') if isinstance(j.get('data'), dict) else None
    chars = chars or []
    idle = [c for c in chars if not (c.get('info') or {}).get('level')]
    print('[A] 角色 %d 个，其中未升级 %d 个' % (len(chars), len(idle)), flush=True)

    st, j2 = api('/api/user/getMainInfo')
    print('[A] getMainInfo 完整内容:', flush=True)
    print(json.dumps(j2, ensure_ascii=False, indent=1)[:2000], flush=True)
    print()
    for probe in ('/api/user/getBonusCalc', '/api/user/getMenu', '/api/site/status'):
        st, jp = api(probe)
        print('[A] %s → %s' % (probe, str(jp)[:600]), flush=True)
        print()

    print()
    print('=== 未升级角色清单 ===')
    for c in idle:
        print('  id=%-4s %-22s rank=%s' % (c.get('id'), str(c.get('name'))[:22], c.get('rank')), flush=True)

    if STAGE == 'A':
        print('\n（只读阶段结束。设 ZQ_STAGE=B 可对第 1 个执行 +1 级验证）', flush=True)
        raise SystemExit(0)

    # ---- 阶段 B：只升一个 1 级 ----
    first = idle[0]
    print()
    print('=== 阶段 B：对 id=%s（%s）执行 +1 级 ===' % (first['id'], first.get('name')), flush=True)
    st, j3 = api('/api/gaming/trainGenshinCharacter', 'POST',
                 {'id': first['id'], 'resetModal': False})
    print('  返回: %s | %s' % (st, str(j3)[:300]), flush=True)

    st, j4 = api('/api/gaming/listGenshinCharacter')
    ch4 = (j4.get('data') or {}).get('characters') if isinstance(j4.get('data'), dict) else []
    now = next((c for c in (ch4 or []) if c.get('id') == first['id']), None)
    if now:
        info = now.get('info') or {}
        print('  升级后: level=%s cost=%s profit=%s' % (
            info.get('level'), info.get('cost'), info.get('profit')), flush=True)
    st, j5 = api('/api/user/getMainInfo')
    print('  升级后 getMainInfo: %s' % (str(j5)[:300]), flush=True)
