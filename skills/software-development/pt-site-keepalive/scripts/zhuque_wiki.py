#!/usr/bin/env python3
"""读朱雀的「规则与常见问题」(/api/site/ruleAndFaq) —— 相当于它的 wiki。

只读：带会话 + x-csrf-token 请求，把正文落盘。
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

    def api(path, method='GET', body=None):
        return page.evaluate("""async (a) => {
            const h = {'Content-Type': 'application/json'};
            if (a.csrf) h['x-csrf-token'] = a.csrf;
            const r = await fetch(a.path, {method: a.method, credentials: 'include', headers: h,
                                           body: a.body ? JSON.stringify(a.body) : undefined});
            return r.status + '|' + (await r.text());
        }""", {'path': path, 'method': method, 'body': body, 'csrf': csrf})

    print('\n=== /api/site/ruleAndFaq ===', flush=True)
    r = api('/api/site/ruleAndFaq')
    open(os.path.expanduser('~/safeline-research/zhuque_ruleandfaq.json'), 'w', encoding='utf-8').write(r)
    print('  返回长度: %d' % len(r), flush=True)
    body = r.split('|', 1)[1] if '|' in r else r
    try:
        j = json.loads(body)
        data = j.get('data')
        if isinstance(data, dict):
            items = data.get('list') or data.get('items') or data
        else:
            items = data
        if isinstance(items, list):
            print('  条目数: %d' % len(items), flush=True)
            for i, it in enumerate(items[:40]):
                if isinstance(it, dict):
                    title = it.get('title') or it.get('name') or it.get('question') or ''
                    content = it.get('content') or it.get('answer') or it.get('text') or ''
                    content = re.sub(r'<[^>]+>', ' ', str(content))
                    content = re.sub(r'\s+', ' ', content).strip()
                    print('\n  [%d] %s' % (i + 1, title), flush=True)
                    print('      %s' % content[:500], flush=True)
                else:
                    print('  [%d] %s' % (i + 1, str(it)[:300]), flush=True)
        else:
            txt = re.sub(r'<[^>]+>', ' ', json.dumps(data, ensure_ascii=False))
            print('  %s' % re.sub(r'\s+', ' ', txt)[:2500], flush=True)
    except Exception as exc:
        print('  解析失败(%s)，原文前 2000 字：' % exc, flush=True)
        print(body[:2000], flush=True)
