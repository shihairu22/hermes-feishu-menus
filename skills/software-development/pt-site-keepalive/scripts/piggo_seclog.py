#!/usr/bin/env python3
"""PigGo 登录审计：异地登陆消息盒(box=202) + 个人资料页 IP 区块。

用途：用户问「看看我站点的登录 IP / 异地登陆消息是什么时间」时跑这个。
性质：只读。注意打开消息会将其标为已读（横幅计数递减，预期行为）。

运行（浏览器脚本，需 xvfb；cwd 不要是 /root）：
  cd /tmp && xvfb-run -a --server-args="-screen 0 1280x900x24" \
    ~/.pt-sessions/venv/bin/python \
    ~/.hermes/skills/software-development/pt-site-keepalive/scripts/piggo_seclog.py

输出：① box=202 每条消息的「你于 <时间> … IP/位置 … 上次登录 …」
      ② userdetails 的「最近动向 / 当前IP / BT客户端」区块。
判读要点见同目录 ../references/piggo.md 的「登录 IP / 异地登录审计」节。
"""
import os  # 家目录展开（去敏时可移植化）
import re
import time

from camoufox.sync_api import Camoufox

UD = os.path.expanduser('~/.pt-sessions/piggo-login-session')
BASE = 'https://piggo.me'
UID = 19717  # PTUSER


def textify(h):
    h = re.sub(r'<script[\s\S]*?</script>', ' ', h)
    h = re.sub(r'<style[\s\S]*?</style>', ' ', h)
    h = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', h)


def wait_ready(page, markers, budget=380):
    """SafeLine WAF 慢：轮询到页面出现任一标记（或超时）为止。"""
    end = time.time() + budget
    h = ''
    while time.time() < end:
        try:
            h = page.content()
        except Exception:
            h = ''
        if any(m in h for m in markers):
            return h
        page.wait_for_timeout(3500)
    return h


def main():
    with Camoufox(headless=False, os="windows", humanize=True,
                  persistent_context=True, user_data_dir=UD) as browser:
        page = browser.new_page()

        # ① 异地登陆消息盒
        page.goto(BASE + '/messages.php?box=202',
                  wait_until='domcontentloaded', timeout=180000)
        h = wait_ready(page, ['收件箱', '异地'], 380)
        print('>> 消息盒:', page.url)
        ids = []
        for m in re.finditer(r'messages\.php\?action=viewmessage&(?:amp;)?id=(\d+)', h):
            if m.group(1) not in ids:
                ids.append(m.group(1))
        print('消息条数:', len(ids))
        for mid in ids:
            page.goto(BASE + '/messages.php?action=viewmessage&id=' + mid,
                      wait_until='domcontentloaded', timeout=120000)
            h2 = wait_ready(page, ['你于', '异地'], 240)
            t = textify(h2)
            i = t.find('你于')
            if i >= 0:
                print('──', t[max(0, i - 80): i + 430])
            else:
                print('── (未找到正文) id=' + mid)
            print()

        # ② 个人资料页 IP 区块
        page.goto(BASE + '/userdetails.php?id=%d' % UID,
                  wait_until='domcontentloaded', timeout=180000)
        h3 = wait_ready(page, ['当前IP', '最近动向'], 300)
        t3 = textify(h3)
        i = t3.find('最近动向')
        print('>> 资料页 IP 区块:')
        if i >= 0:
            print(t3[i: i + 700])
        else:
            print('(未找到「最近动向」字段，页首 600 字：)')
            print(t3[:600])


if __name__ == '__main__':
    main()
