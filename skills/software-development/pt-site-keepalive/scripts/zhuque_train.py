#!/usr/bin/env python3
"""朱雀角色升级 —— 把新抽到的角色从 lv=1 升到目标等级。

策略：
  ① 先试站点原生的「一键升级」批量接口：POST {resetModal:false, level:目标}
  ② 校验是否生效；若未生效，退回逐个接口：POST {id, resetModal:false, level:目标}
  ③ 全程打印余额与等级变化
"""
import json
import os

from camoufox.sync_api import Camoufox

PROF = os.path.expanduser('~/.pt-sessions/zhuque-login-session')
TARGET = int(os.environ.get('ZQ_TARGET', '79'))

with Camoufox(headless=False, os="windows", humanize=True, persistent_context=True,
              user_data_dir=PROF) as browser:
    page = browser.new_page()
    page.goto('https://zhuque.in/index', wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(7000)
    csrf = page.evaluate("""() => { const m=document.querySelector('meta[name="x-csrf-token"]');
                                    return m ? m.getAttribute('content') : ''; }""")

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

    def snap():
        st, j = api('/api/gaming/listGenshinCharacter')
        d = j.get('data') or {}
        chars = d.get('characters') or []
        owned = [c for c in chars if (c.get('info') or {}).get('level')]
        return d, owned

    d0, owned0 = snap()
    low = [c for c in owned0 if (c.get('info') or {}).get('level', 0) < TARGET]
    print('=' * 60)
    print('朱雀角色升级 → 目标 lv=%d' % TARGET)
    print('=' * 60)
    print('[起始] 余额 %.2f | 已拥有 %d 个 | 低于 %d 级的有 %d 个' % (
        d0.get('bonus'), len(owned0), TARGET, len(low)), flush=True)
    for c in low:
        print('   id=%-4s %-18s lv=%-3s needExp=%s' % (
            c['id'], str(c.get('name'))[:18], (c.get('info') or {}).get('level'), c.get('needExp')), flush=True)
    if not low:
        print('  无需升级，退出')
        raise SystemExit(0)

    print()
    print('=== ① 试批量：POST {resetModal:false, level:%d} ===' % TARGET, flush=True)
    st, j = api('/api/gaming/trainGenshinCharacter', 'POST',
                {'resetModal': False, 'level': TARGET})
    print('  返回: %s | %s' % (st, str(j)[:200]), flush=True)
    d1, owned1 = snap()
    still = [c for c in owned1 if (c.get('info') or {}).get('level', 0) < TARGET]
    print('  批量后：仍低于 %d 级的有 %d 个 | 余额 %.2f' % (TARGET, len(still), d1.get('bonus')), flush=True)

    if still:
        print()
        print('=== ② 批量无效，改为逐个升级 ===', flush=True)
        for c in still:
            st, j = api('/api/gaming/trainGenshinCharacter', 'POST',
                        {'id': c['id'], 'resetModal': False, 'level': TARGET})
            d2, owned2 = snap()
            now = next((x for x in owned2 if x['id'] == c['id']), None)
            lv = (now.get('info') or {}).get('level') if now else '?'
            print('   id=%-4s %-18s → %s | lv=%s | 余额 %.0f | %s' % (
                c['id'], str(c.get('name'))[:18], st, lv, d2.get('bonus'), str(j)[:80]), flush=True)

    d3, owned3 = snap()
    print()
    print('=' * 60)
    print('[结束] 余额 %.2f（共花 %.0f）' % (d3.get('bonus'), d0.get('bonus') - d3.get('bonus')))
    dist = {}
    for c in owned3:
        l = (c.get('info') or {}).get('level')
        dist[l] = dist.get(l, 0) + 1
    print('       等级分布: %s' % dict(sorted(dist.items())))
    below = [c for c in owned3 if (c.get('info') or {}).get('level', 0) < TARGET]
    print('       仍低于 %d 级: %d 个' % (TARGET, len(below)))
    print('=' * 60)
