#!/usr/bin/env python3
"""⚠️ 已作废（2026-09-28）—— 当前等级上限是 79，不是 90！

保留此文件仅作历史记录。任何目标 > 79 的调用都会返回 400 LEVEL_IS_90。
升到 79 请用 scripts/zhuque_train.py（ZQ_TARGET=79）。
朱雀角色升级的真实情况见 references/zhuque.md「二、升级接口」章节。
"""
"""朱雀角色升级到满级（90）—— 带重试的稳健版（已作废）。

关键：`trainGenshinCharacter` 的 `level` 参数是「**提升级数**」不是目标等级！
      → 要升到 90，应传 `level = 90 - 当前等级`。
      越界会返回 `400 LEVEL_IS_90`。

流程：
  ① 读当前状态 → 取最低等级 → 计算 delta
  ② 循环调用批量 {resetModal:false, level:delta}，失败重试
  ③ 复查等级分布，直到全部 90
"""
import json
import os
import time

from camoufox.sync_api import Camoufox

PROF = os.path.expanduser('~/.pt-sessions/zhuque-login-session')
TARGET = int(os.environ.get('ZQ_MAX_LV', '90'))
MAX_ROUNDS = 8

with Camoufox(headless=False, os="windows", humanize=True, persistent_context=True,
              user_data_dir=PROF) as browser:
    page = browser.new_page()
    page.goto('https://zhuque.in/index', wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(8000)
    csrf = page.evaluate("""() => { const m=document.querySelector('meta[name="x-csrf-token"]');
                                    return m ? m.getAttribute('content') : ''; }""")

    def api(path, method='GET', body=None, tries=3):
        for k in range(tries):
            try:
                r = page.evaluate("""async (a) => {
                    const h = {'Content-Type': 'application/json'};
                    if (a.csrf) h['x-csrf-token'] = a.csrf;
                    const r = await fetch(a.path, {method: a.method, credentials: 'include',
                                                   headers: h,
                                                   body: a.body ? JSON.stringify(a.body) : undefined});
                    return r.status + '|' + (await r.text());
                }""", {'path': path, 'method': method, 'body': body, 'csrf': csrf})
                st, _, txt = r.partition('|')
                try:
                    return int(st), json.loads(txt)
                except Exception:
                    return st, txt
            except Exception as exc:
                print('     （网络异常，第 %d 次重试: %s）' % (k + 1, str(exc)[:60]), flush=True)
                time.sleep(4)
        return 0, 'NETWORK_FAIL'

    def snap():
        st, j = api('/api/gaming/listGenshinCharacter')
        d = j.get('data') if isinstance(j, dict) else {}
        d = d or {}
        owned = [c for c in (d.get('characters') or []) if (c.get('info') or {}).get('level')]
        return d, owned

    d0, o0 = snap()
    print('=' * 62)
    print('朱雀角色升级 → 满级 %d' % TARGET)
    print('=' * 62)
    lv0 = {}
    for c in o0:
        L = (c.get('info') or {}).get('level')
        lv0[L] = lv0.get(L, 0) + 1
    print('[起始] 余额 %.2f | 等级分布 %s' % (d0.get('bonus'), dict(sorted(lv0.items()))), flush=True)

    for rnd in range(1, MAX_ROUNDS + 1):
        d1, o1 = snap()
        low = [c for c in o1 if ((c.get('info') or {}).get('level') or 0) < TARGET]
        if not low:
            print('\n★ 全部已达 %d 级 ✓' % TARGET)
            break
        cur_min = min((c.get('info') or {}).get('level') or 0 for c in low)
        delta = TARGET - cur_min
        print('\n[第 %d 轮] 仍有 %d 个低于 %d（最低 %d 级）→ 批量提升 %d 级' % (
            rnd, len(low), TARGET, cur_min, delta), flush=True)
        st, j = api('/api/gaming/trainGenshinCharacter', 'POST',
                    {'resetModal': False, 'level': delta})
        print('  返回 %s | %s' % (st, str(j)[:200]), flush=True)
        d2, o2 = snap()
        lv2 = {}
        for c in o2:
            L = (c.get('info') or {}).get('level')
            lv2[L] = lv2.get(L, 0) + 1
        print('  余额 %.2f（本轮花 %.0f）| 等级分布 %s' % (
            d2.get('bonus'), d1.get('bonus') - d2.get('bonus'),
            dict(sorted(lv2.items()))), flush=True)
        if st != 200:
            print('  ✗ 本轮失败，继续重试'); time.sleep(3)

    d9, o9 = snap()
    lv9 = {}
    for c in o9:
        L = (c.get('info') or {}).get('level')
        lv9[L] = lv9.get(L, 0) + 1
    print()
    print('=' * 62)
    print('[结束] 余额 %.2f（共花 %.0f）' % (d9.get('bonus'), d0.get('bonus') - d9.get('bonus')))
    print('       等级分布 %s' % dict(sorted(lv9.items())))
    r9 = {}
    for c in o9:
        x = (c.get('info') or {}).get('ratio')
        r9[x] = r9.get(x, 0) + 1
    print('       削减倍率分布 %s' % r9)
    tot = sum((11000 if ((c.get('info') or {}).get('level') or 0) >= 90
               else 200 + 120 * max(0, ((c.get('info') or {}).get('level') or 0) - 1))
              * ((c.get('info') or {}).get('ratio') if isinstance((c.get('info') or {}).get('ratio'), (int, float)) else 1.0)
              for c in o9)
    print('       全部释放一轮收益 %.0f 灵石' % tot)
    print('=' * 62)
