import html, json, os, re, time, urllib.request
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36'
def txt(h):
    h=re.sub(r'(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>',' ',h)
    h=re.sub(r'(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>','\n',h)
    h=re.sub(r'(?s)<[^>]+>',' ',h); h=html.unescape(h)
    h=re.sub(r'[ \t\u00a0]+',' ',h); return re.sub(r'\n\s*\n+','\n',h).strip()
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent':UA}), timeout=40) as x:
        return x.read().decode('utf-8','ignore')
def gql(base, q):
    req=urllib.request.Request(base+'/graphql', data=json.dumps({'query':q}).encode(),
        headers={'Content-Type':'application/json','User-Agent':UA})
    with urllib.request.urlopen(req, timeout=35) as x: return json.loads(x.read().decode())

out=json.load(open('wikis/more-sites.json')) if os.path.exists('wikis/more-sites.json') else {}

for name, base in [('DiscFan','https://wiki.discfan.net'), ('PigGo','https://wiki.piggo.me')]:
    print(); print('===== %s wiki（%s）=====' % (name, base))
    try:
        d=gql(base, '{pages{list{id,path,title,locale}}}')
        lst=(d.get('data') or {}).get('pages',{}).get('list') or []
        if not lst:
            print('  ✗ 页面列表为空:', json.dumps(d, ensure_ascii=False)[:200]); continue
        seen=set(); pages=[]
        for p in lst:
            if p['path'] in seen: continue
            seen.add(p['path']); pages.append(p)
        print('  共 %d 页' % len(pages))
        ok=0
        for i,p in enumerate(pages,1):
            loc = p.get('locale') or 'zh'
            for cand in ['/'+loc+'/'+p['path'], '/'+p['path']]:
                try:
                    t=txt(get(base+cand))
                    if len(t) > 60 and 'Login' not in t[:40]:
                        out['%s-wiki:%s'%(name,p['path'])]={'url':base+cand,'title':p.get('title'),'text':t}
                        print('   [%2d/%d] %-34s %d 字' % (i,len(pages),p['path'][:32],len(t)))
                        ok+=1; break
                except Exception as e:
                    continue
            time.sleep(0.2)
        print('  → 成功 %d / %d 页' % (ok, len(pages)))
    except Exception as e:
        print('  ✗', str(e)[:100])

json.dump(out, open('wikis/more-sites.json','w'), ensure_ascii=False, indent=1)
print(); print('已落盘（%d 条）' % len(out))
