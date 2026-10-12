#!/usr/bin/env python3
"""#6 朱雀角色升级策略研究：抓全部角色的经济数据，算升级 ROI。

只读：GET /api/gaming/listGenshinCharacter（必须带 x-csrf-token）。
"""
import os  # 家目录展开（去敏时可移植化）
import json
import re

from camoufox.sync_api import Camoufox

PROF = os.path.expanduser('~/.pt-sessions/zhuque-login-session')

with Camoufox(headless=False, os="windows", humanize=True, persistent_context=True,
              user_data_dir=PROF) as browser:
    page = browser.new_page()
    page.goto('https://zhuque.in/index', wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(7000)
    csrf = page.evaluate("""() => { const m = document.querySelector('meta[name="x-csrf-token"]');
                                    return m ? m.getAttribute('content') : ''; }""")
    print('CSRF: %s' % (csrf[:12] + '…' if csrf else '（未取到）'), flush=True)
    raw = page.evaluate("""async (csrf) => {
        const h = csrf ? {'x-csrf-token': csrf} : {};
        const r = await fetch('/api/gaming/listGenshinCharacter', {credentials:'include', headers:h});
        return await r.text();
    }""", csrf)
    try:
        j = json.loads(raw)
    except Exception:
        print('解析失败: %s' % raw[:200]); raise SystemExit(1)
    d = j.get('data') or {}
    chars = d.get('characters') if isinstance(d, dict) else (d or [])
    chars = chars or []
    print('角色总数: %d' % len(chars), flush=True)
    json.dump(chars, open(os.path.expanduser('~/safeline-research/zhuque_chars.json'), 'w'),
              ensure_ascii=False, indent=1)
    print('已落盘 zhuque_chars.json', flush=True)

    # 经济分析
    rows = []
    for c in chars:
        info = c.get('info') or {}
        lv = info.get('level')
        cost = info.get('cost') or 0
        profit = info.get('profit') or 0
        rows.append({'name': c.get('name'), 'rank': c.get('rank'), 'lv': lv,
                     'cost': cost, 'profit': profit,
                     'roi': (profit / cost) if cost else None})
    print()
    print('=== 已升级角色（有 level）===')
    for r in sorted([x for x in rows if x['lv']], key=lambda x: -(x['roi'] or 0))[:25]:
        print('  %-22s rank=%s lv=%-3s cost=%-9d profit=%-10d ROI=%.2f' % (
            str(r['name'])[:22], r['rank'], r['lv'], r['cost'], r['profit'], r['roi'] or 0), flush=True)
    up = [x for x in rows if x['lv']]
    print()
    print('  已升级: %d / %d' % (len(up), len(rows)))
    if up:
        print('  平均 ROI: %.2f' % (sum(x['roi'] for x in up) / len(up)))
        print('  总投入: %d  总产出: %d' % (sum(x['cost'] for x in up), sum(x['profit'] for x in up)))
    print()
    print('=== 各等级分布 ===')
    import collections
    for lv, n in sorted(collections.Counter(x['lv'] for x in rows if x['lv']).items()):
        print('  lv=%-3s : %d 个' % (lv, n))
