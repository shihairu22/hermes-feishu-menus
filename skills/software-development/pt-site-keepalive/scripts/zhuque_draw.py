#!/usr/bin/env python3
"""朱雀抽卡 —— 循环抽到集齐（或触发安全阀）。

策略：
  · 每轮 10 抽（连抽十次），常驻池（可出所有四星与五星）
  · 停止条件（任一命中）：
      ① 116 个角色全部拥有
      ② 灵石余额 < FLOOR（默认 5000 万，避免过度消耗）
      ③ 累计抽数 ≥ MAX_DRAWS（默认 3000，约 300 万灵石）
  · 每轮打印进度；结束打印完整汇总
"""
import json
import os

from camoufox.sync_api import Camoufox

PROF = os.path.expanduser('~/.pt-sessions/zhuque-login-session')
FLOOR = float(os.environ.get('ZQ_FLOOR', '50000000'))
MAX_DRAWS = int(os.environ.get('ZQ_MAX_DRAWS', '3000'))
POOL = os.environ.get('ZQ_POOL', 'normal')
PER = 10

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
        owned = {c['id'] for c in chars if (c.get('info') or {}).get('level')}
        return d, chars, owned

    d0, chars0, owned0 = snap()
    names = {c['id']: c.get('name') for c in chars0}
    ranks = {c['id']: c.get('rank') for c in chars0}
    total = len(chars0)
    b0, dm0 = d0.get('bonus'), d0.get('diamond')
    print('=' * 60)
    print('朱雀抽卡 —— 抽到集齐')
    print('=' * 60)
    print('[起始] 余额 %.2f  碎片 %s  已拥有 %d/%d' % (b0, dm0, len(owned0), total), flush=True)
    print('       停止条件：集齐 / 余额<%.0f / 累计 %d 抽' % (FLOOR, MAX_DRAWS), flush=True)
    print()

    drawn = 0
    rnd = 0
    new_all = set()
    while True:
        if len(owned0 | new_all) >= total:
            print('\n★ 已集齐全部 %d 个角色，停止抽卡' % total, flush=True)
            break
        if drawn >= MAX_DRAWS:
            print('\n★ 已达最大抽数 %d，停止' % MAX_DRAWS, flush=True)
            break
        rnd += 1
        st, j2 = api('/api/gaming/drawGenshinCharacter', 'POST',
                     {'count': PER, 'type': POOL})
        dd = j2.get('data') if isinstance(j2, dict) else {}
        if not dd:
            print('[%3d] 抽卡异常: %s | %s' % (rnd, st, str(j2)[:200]), flush=True)
            break
        drawn += PER
        res = dd.get('result') or []
        bal = dd.get('bonus')
        got = [r for r in res if r.get('character')]
        line = []
        for r in got:
            cid = r['character']
            tag = '★新' if cid not in owned0 and cid not in new_all else '重复'
            if tag == '★新':
                new_all.add(cid)
            line.append('%s(%s%s)' % (names.get(cid, '?'), r.get('rank'), tag))
        print('[%3d] 抽%d次 累计%-5d | 余额 %.0f | %s' % (
            rnd, PER, drawn, bal if isinstance(bal, (int, float)) else 0,
            ' '.join(line) if line else '（全是数据提升）'), flush=True)
        if isinstance(bal, (int, float)) and bal < FLOOR:
            print('\n★ 余额已低于安全线 %.0f，停止抽卡' % FLOOR, flush=True)
            break

    d1, chars1, owned1 = snap()
    allnew = sorted((owned0 | new_all) - owned0)
    print()
    print('=' * 60)
    print('[结束] 累计抽 %d 次' % drawn)
    print('       余额 %.2f → %.2f（共花 %.0f）' % (b0, d1.get('bonus'), b0 - d1.get('bonus')))
    print('       碎片 %s → %s' % (dm0, d1.get('diamond')))
    print('       已拥有 %d → %d / %d' % (len(owned0), len(owned1), total))
    print('       新获得 %d 个：' % len(allnew))
    for cid in allnew:
        print('         ★ %-16s rank=%s' % (str(names.get(cid, cid))[:16], ranks.get(cid)), flush=True)
    still = [c.get('name') for c in chars1 if c['id'] not in owned1]
    print('       仍未拥有 %d 个：%s' % (len(still), still))
    print('=' * 60)
