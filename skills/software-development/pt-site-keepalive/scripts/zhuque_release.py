#!/usr/bin/env python3
"""朱雀每日释放技能 —— 带「buff 错开」逻辑的最优释放。

策略（依据 references/zhuque.md 第五节实测计算）：
  ① magic=2 的角色释放后给「持续 1 天的灵石加成」（lv79 = +49%，满级 +55%），
     冷却约 85 小时。**必须错开释放**，否则加成只覆盖 24h/85h。
     → 本脚本用状态文件记录上次 buff 释放时间，距上次 ≥13 小时才放下一个。
     → **并且先放 buff，再放其余角色**，让加成效覆盖后续释放。
  ② magic=1 的角色按「已就绪」全部释放。
  ③ magic=3/4（行秋/班尼特）不需要自己释放（它们作用于绑定角色）。

用法：
  MTEAM_NO_DELAY=1 <venv>/bin/python zhuque_release.py          # 正常执行
  ZQ_DRY=1 ... zhuque_release.py                                 # 只读，不实际释放
"""
import json
import os
import time

from camoufox.sync_api import Camoufox

PROF = os.path.expanduser('~/.pt-sessions/zhuque-login-session')
STATE = os.path.expanduser('~/.pt-sessions/state/zhuque_buff_state.json')
BUFF_GAP_H = float(os.environ.get('ZQ_BUFF_GAP_H', '13'))   # buff 角色最小间隔（小时）
DRY = os.environ.get('ZQ_DRY', '0') == '1'
NOW = int(time.time())


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, 'w'), ensure_ascii=False, indent=1)


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
        return d, (d.get('characters') or [])

    d0, chars = snap()
    owned = [c for c in chars if (c.get('info') or {}).get('level')]
    print('=' * 62)
    print('朱雀释放技能 —— buff 错开模式%s' % ('（演练，不实际释放）' if DRY else ''))
    print('=' * 62)
    print('[起始] 余额 %.2f | 已拥有 %d 个角色' % (d0.get('bonus'), len(owned)), flush=True)

    st_state = load_state()
    last_buff = st_state.get('last_buff_release', 0)
    gap_h = (NOW - last_buff) / 3600 if last_buff else 9999
    print('       上次 buff 释放: %s（%.1f 小时前）' % (
        time.strftime('%Y-%m-%d %H:%M', time.localtime(last_buff)) if last_buff else '无记录',
        gap_h if last_buff else 0), flush=True)

    def ready(c):
        return ((c.get('info') or {}).get('next_time') or 0) <= NOW

    buffs = [c for c in owned if c.get('magic') == 2 and ready(c)]
    others = [c for c in owned if c.get('magic') == 1 and ready(c)]
    print('       就绪：buff 角色 %d 个 / 普通角色 %d 个' % (len(buffs), len(others)), flush=True)

    # ---- ① 先放一个 buff（错开）----
    if buffs and gap_h >= BUFF_GAP_H:
        pick = sorted(buffs, key=lambda c: c['id'])[0]
        print()
        print('[① ] 释放 buff 角色：%s (id=%s)' % (pick.get('name'), pick['id']), flush=True)
        if DRY:
            print('     （演练模式，跳过）')
        else:
            st, j = api('/api/gaming/fireGenshinCharacterMagic', 'POST',
                        {'id': pick['id'], 'resetModal': True})
            print('     返回 %s | %s' % (st, str(j)[:200]), flush=True)
            if isinstance(j, dict) and j.get('status') == 200:
                st_state['last_buff_release'] = NOW
                st_state.setdefault('history', []).append({'t': NOW, 'id': pick['id'],
                                                           'name': pick.get('name'), 'kind': 'buff'})
                save_state(st_state)
                print('     ✓ 已记录，下次 buff 释放最早在 %.0f 小时后' % BUFF_GAP_H)
    elif buffs:
        print()
        print('[① ] buff 角色有 %d 个就绪，但距上次仅 %.1fh（需 ≥%.0fh），本次跳过 ✓ 保持错开'
              % (len(buffs), gap_h, BUFF_GAP_H), flush=True)
    else:
        print()
        print('[① ] 暂无就绪的 buff 角色', flush=True)

    # ---- ② 再放其余角色 ----
    print()
    print('[② ] 释放其余就绪角色（%d 个）…' % len(others), flush=True)
    if others:
        if DRY:
            print('     （演练模式，跳过）')
        else:
            st, j = api('/api/gaming/fireGenshinCharacterMagic', 'POST',
                        {'all': 1, 'resetModal': True})
            print('     批量返回 %s | %s' % (st, str(j)[:200]), flush=True)
    else:
        print('     无就绪角色', flush=True)

    d1, chars1 = snap()
    owned1 = [c for c in chars1 if (c.get('info') or {}).get('level')]
    nready = len([c for c in owned1 if ((c.get('info') or {}).get('next_time') or 0) <= NOW])
    print()
    print('[结束] 余额 %.2f（本次 +%.0f）| 仍在冷却 %d 个' % (
        d1.get('bonus'), d1.get('bonus') - d0.get('bonus'), len(owned1) - nready), flush=True)
    print('=' * 62)
