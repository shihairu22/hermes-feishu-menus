import os  # 家目录展开（去敏时可移植化）
import json, os
from camoufox.sync_api import Camoufox

OUT=os.path.expanduser('~/safeline-research/wikis/PigGo-wiki.json')
PAGES = [('站点规则','https://wiki.piggo.me/zh/%E7%AB%99%E7%82%B9%E8%A7%84%E5%88%99'),
         ('盒子及限速规则','https://wiki.piggo.me/zh/%E7%AB%99%E7%82%B9%E8%A7%84%E5%88%99/%E7%9B%92%E5%AD%90%E5%8F%8A%E9%99%90%E9%80%9F%E8%A7%84%E5%88%99')]

with Camoufox(headless=False, os="windows", humanize=True, persistent_context=True,
              user_data_dir=os.path.expanduser('~/.pt-sessions/piggo-login-session')) as b:
    p = b.new_page()
    print('=== ① 打开 wiki 并走 OAuth2 ===')
    p.goto('https://wiki.piggo.me/', wait_until='domcontentloaded', timeout=70000)
    p.wait_for_timeout(4000)
    print('  首页标题:', p.title()[:60])
    # 点「登录」
    for sel in ['a:has-text("登录")', 'button:has-text("登录")', 'a[href*="login"]']:
        try:
            el = p.query_selector(sel)
            if el:
                print('  找到登录入口:', sel); el.click(); break
        except Exception: pass
    p.wait_for_timeout(4000)
    print('  跳转后 URL:', p.url[:90])
    # 点 PIGo OAuth2
    for sel in ['a:has-text("PIGo")', 'button:has-text("PIGo")', 'text=PIGo OAuth2']:
        try:
            el = p.query_selector(sel)
            if el:
                print('  找到 OAuth2 入口:', sel); el.click(); break
        except Exception: pass
    p.wait_for_timeout(6000)
    print('  授权页 URL:', p.url[:110])
    print('  页面文字:', ' '.join(p.evaluate('() => document.body.innerText').split())[:300])
    # 找「授权/同意/Authorize」按钮
    for sel in ['button:has-text("授权")', 'button:has-text("同意")', 'a:has-text("授权")',
                'button:has-text("Authorize")', 'button[type=submit]']:
        try:
            el = p.query_selector(sel)
            if el:
                print('  点击授权按钮:', sel); el.click(); p.wait_for_timeout(6000); break
        except Exception: pass
    print('  授权后 URL:', p.url[:110])

    print()
    print('=== ② 抓规则页 ===')
    res = {}
    try: res = json.load(open(OUT))
    except Exception: pass
    for label, url in PAGES:
        try:
            p.goto(url, wait_until='domcontentloaded', timeout=70000)
            p.wait_for_timeout(5000)
            t = ' '.join(p.evaluate('() => document.body.innerText').split())
            print('  ══ %s ══ %s | %d 字' % (label, p.title()[:40], len(t)))
            print('     %s' % t[:600])
            res[label] = {'url': url, 'title': p.title()[:80], 'text': t}
        except Exception as e:
            print('  ══ %s ══ ✗ %s' % (label, str(e)[:80]))
    json.dump(res, open(OUT,'w'), ensure_ascii=False, indent=1)
    print()
    print('已落盘', OUT)
