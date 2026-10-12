#!/usr/bin/env python3
"""朱雀「释放技能」收益最大化分析。

抓取每个角色的：等级 / 冷却(next_time) / 累计投入(cost) / 累计收益(profit) /
削减倍率(ratio) / 技能类型(magic)，据此计算：
  ① 当前每个角色的实际释放收益（含削减）
  ② 全账号每轮「全部释放」的总收益
  ③ 冷却分布 → 每天能释放几轮
  ④ 升级能否把削减倍率「修回来」（成本上升 → 比值下降 → 倍率提高）
"""
import os  # 家目录展开（去敏时可移植化）
import json
import time

from camoufox.sync_api import Camoufox

PROF = os.path.expanduser('~/.pt-sessions/zhuque-login-session')
NOW = int(time.time())

with Camoufox(headless=False, os="windows", humanize=True, persistent_context=True,
              user_data_dir=PROF) as browser:
    page = browser.new_page()
    page.goto('https://zhuque.in/index', wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(7000)
    csrf = page.evaluate("""() => { const m=document.querySelector('meta[name="x-csrf-token"]');
                                    return m ? m.getAttribute('content') : ''; }""")
    r = page.evaluate("""async (csrf) => {
        const r = await fetch('/api/gaming/listGenshinCharacter',
                              {credentials: 'include', headers: {'x-csrf-token': csrf}});
        return await r.text();
    }""", csrf)
    d = json.loads(r).get('data') or {}
    chars = d.get('characters') or []
    owned = [c for c in chars if (c.get('info') or {}).get('level')]
    print('余额 %.2f | 碎片 %s | 已拥有 %d 个角色' % (d.get('bonus'), d.get('diamond'), len(owned)))
    json.dump(owned, open(os.path.expanduser('~/safeline-research/zhuque_chars_full.json'), 'w'),
              ensure_ascii=False, indent=1)

    # ---- 逐个角色计算 ----
    rows = []
    for c in owned:
        info = c.get('info') or {}
        lv = info.get('level') or 0
        cost = info.get('cost') or 0
        profit = info.get('profit') or 0
        nt = info.get('next_time') or 0
        ratio = info.get('ratio')
        magic = c.get('magic')
        # 释放基础收益：200 + 120*(lv-1)，满级 11000
        base = 11000 if lv >= 90 else 200 + 120 * max(0, lv - 1)
        # 削减倍率：站点返回的 ratio（0.1=10%）
        mult = ratio if isinstance(ratio, (int, float)) else 1.0
        rows.append({'id': c['id'], 'name': c.get('name'), 'lv': lv, 'magic': magic,
                     'cost': cost, 'profit': profit, 'ratio': mult,
                     'base': base, 'eff': base * mult,
                     'cd_left': nt - NOW, 'needExp': c.get('needExp')})

    print()
    print('=== ① 技能类型分布 ===')
    dist = {}
    for r_ in rows:
        dist[r_['magic']] = dist.get(r_['magic'], 0) + 1
    print('  magic 类型: %s' % dist)
    print('  （wiki：1/2 类为提升数据型；3/4 类为持续增益型并需绑定）')

    print()
    print('=== ② 削减倍率分布 ===')
    dd = {}
    for r_ in rows:
        dd[r_['ratio']] = dd.get(r_['ratio'], 0) + 1
    print('  %s' % dict(sorted(dd.items(), key=lambda x: (x[0] is None, x[0]))))

    print()
    print('=== ③ 当前实际释放收益（前 10 高）===')
    for r_ in sorted(rows, key=lambda x: -x['eff'])[:10]:
        print('  %-18s lv=%-3s base=%-6d ×%.2f = %-8.0f | profit/cost=%.2f | 冷却 %.1fh' % (
            str(r_['name'])[:18], r_['lv'], r_['base'], r_['ratio'], r_['eff'],
            (r_['profit'] / r_['cost']) if r_['cost'] else 0, r_['cd_left'] / 3600), flush=True)

    total_eff = sum(r_['eff'] for r_ in rows)
    print()
    print('=== ④ 全部释放一次的总收益 ===')
    print('  名义合计 %d 灵石 → 实际（含削减）%.0f 灵石' % (
        sum(r_['base'] for r_ in rows), total_eff))
    print('  平均削减到 %.1f%%' % (100 * total_eff / sum(r_['base'] for r_ in rows)))

    print()
    print('=== ⑤ 冷却分布（决定每天能释放几轮）===')
    ready = [r_ for r_ in rows if r_['cd_left'] <= 0]
    print('  现在可释放: %d 个' % len(ready))
    buckets = {}
    for r_ in rows:
        h = r_['cd_left'] / 3600
        k = ('已就绪' if h <= 0 else '0-6h' if h <= 6 else '6-12h' if h <= 12
             else '12-24h' if h <= 24 else '24-48h' if h <= 48 else '>48h')
        buckets[k] = buckets.get(k, 0) + 1
    for k in ('已就绪', '0-6h', '6-12h', '12-24h', '24-48h', '>48h'):
        if k in buckets:
            print('    %-8s %d 个' % (k, buckets[k]))
    if ready:
        print('  可释放角色的收益合计: %.0f' % sum(r_['eff'] for r_ in ready))

    print()
    print('=== ⑥ 升级能否把削减倍率修回来（以 10% 档为例）===')
    for r_ in sorted([x for x in rows if x['ratio'] <= 0.1], key=lambda x: -x['profit'])[:3]:
        print('  %-16s lv=%s cost=%d profit=%d 比值=%.2f 倍率=%.0f%%' % (
            str(r_['name'])[:16], r_['lv'], r_['cost'], r_['profit'],
            r_['profit'] / r_['cost'] if r_['cost'] else 0, r_['ratio'] * 100))
        for add in (500000, 1000000, 2000000):
            newcost = r_['cost'] + add
            ratio = r_['profit'] / newcost if newcost else 0
            mult = 1.0 if ratio <= 1.5 else 0.5 if ratio <= 2.5 else 0.25 if ratio <= 3.5 else 0.1
            gain = r_['base'] * mult - r_['eff']
            print('     再投入 %-9d → 比值 %.2f → 倍率 %3.0f%% → 每次多 %+6.0f 灵石 | 回本需 %s 次' % (
                add, ratio, mult * 100, gain,
                ('%.0f' % (add / gain)) if gain > 0 else '∞'), flush=True)
