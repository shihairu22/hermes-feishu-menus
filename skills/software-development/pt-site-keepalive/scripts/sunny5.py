import os  # 家目录展开（去敏时可移植化）
import json, os
from camoufox.sync_api import Camoufox
OUT=os.path.expanduser('~/safeline-research/wikis/more-sites.json')
cookies=[]
for line in open(os.path.expanduser('~/.pt-sessions/state/sunnypt_cookies.txt')):
    if line.startswith('#') or not line.strip(): continue
    f=line.rstrip('\n').split('\t')
    if len(f)>=7: cookies.append({'name':f[5],'value':f[6],'domain':f[0],'path':f[2],'secure':f[3].upper()=='TRUE'})
with Camoufox(headless=False, os="windows", humanize=True) as b:
    ctx=b.new_context()
    for c in cookies:
        for dom in (c['domain'], '.'+c['domain']):
            try: ctx.add_cookies([{'name':c['name'],'value':c['value'],'domain':dom,'path':c['path'],'secure':c['secure']}])
            except Exception: pass
    p=ctx.new_page()
    p.goto('https://sunnypt.top/site/posts', wait_until='networkidle', timeout=60000); p.wait_for_timeout(5000)
    links=p.evaluate('''() => Array.from(document.querySelectorAll('a')).map(a=>({h:a.href,t:(a.innerText||'').trim()})).filter(x=>x.h&&x.h.includes('/site/'))''')
    seen=set(); targets=[]
    for l in links:
        if l['h'] in seen: continue
        seen.add(l['h']); targets.append(l)
    print('=== 公告区链接 ===')
    for l in targets: print('  %-20s %s' % (l['t'][:18], l['h'].replace('https://sunnypt.top','')))
    out=json.load(open(OUT)) if os.path.exists(OUT) else {}
    for l in targets:
        try:
            p.goto(l['h'], wait_until='networkidle', timeout=60000); p.wait_for_timeout(4500)
            t=' '.join(p.evaluate('() => document.body.innerText').split())
            print(); print('  ══ %s ══ %d 字' % (l['t'][:20], len(t)))
            print('     %s' % t[:1200])
            if len(t) > 200:
                out['SunnyPT:'+(l['t'][:20] or l['h'][-20:])]={'url':l['h'],'text':t}
        except Exception as e: print('  ✗ %s' % str(e)[:60])
    json.dump(out, open(OUT,'w'), ensure_ascii=False, indent=1)
    print(); print('已落盘（%d 条）' % len(out))
