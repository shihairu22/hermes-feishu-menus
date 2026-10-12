#!/usr/bin/env python3
"""TorrentLeech（TL）登录保活 —— 例行第 18 站。

用法：python3 tl_login.py           # 登录 + 验证 + 抓账号数据
      python3 tl_login.py --check   # 只检查 hosts / 连通性，不登录

要点：TL 无每日签到，例行只做登录（刷新 Last visit）。登录无验证码/无 2FA，
所以直接 curl 即可，不需要 Camoufox。凭据从本机 M-Team 的 .env 读取，不打印。
"""
import os
import re
import shutil
import subprocess
import sys

ENV = os.path.expanduser('~/.pt-sessions/.env')
COOKIE = os.path.expanduser('~/.pt-sessions/state/tl_cookies.txt')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
BASE = 'https://www.torrentleech.org'
HOSTS_ENTRIES = [
    '172.66.134.33 www.torrentleech.org',
    '172.66.134.33 torrentleech.org',
    '172.66.134.33 wiki.torrentleech.org',
]
FALLBACK_IPS = ['172.66.134.33', '172.66.137.109']


def load_cred():
    cred = {}
    if os.path.exists(ENV):
        for line in open(ENV):
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                cred[k.strip()] = v.strip()
    return cred.get('MTEAM_USERNAME') or cred.get('MTEAM_USER'), cred.get('MTEAM_PASSWORD') or cred.get('MTEAM_PASS')


def ensure_hosts():
    """DNS 被污染，必须靠 hosts。缺哪条补哪条（需要 root）。

    ⚠️ 副作用：会**修改系统文件 /etc/hosts**（追加 TL 的 3 条记录）。
    写入前先备份一份到 /etc/hosts.bak-tl-login，便于回滚。
    """
    cur = open('/etc/hosts').read() if os.path.exists('/etc/hosts') else ''
    missing = [e for e in HOSTS_ENTRIES if e.split()[1] not in cur]
    if missing:
        try:
            shutil.copy2('/etc/hosts', '/etc/hosts.bak-tl-login')
        except OSError:
            pass
        with open('/etc/hosts', 'a') as f:
            f.write('\n' + '\n'.join(missing) + '\n')
        print('[hosts] 已备份到 /etc/hosts.bak-tl-login 并补充 %d 条 TL 记录' % len(missing))
    else:
        print('[hosts] 已就绪')


def curl(args, timeout=30):
    cmd = ['curl', '-s', '-L', '--max-time', str(timeout), '-A', UA,
           '-c', COOKIE, '-b', COOKIE] + args
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def reachable():
    for ip in FALLBACK_IPS:
        r = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', '12',
                            '--resolve', 'www.torrentleech.org:443:' + ip, BASE + '/'],
                           capture_output=True, text=True)
        if r.stdout.strip() == '200':
            return ip
    return None


def text_of(html):
    t = re.sub(r'<script.*?</script>', ' ', html, flags=re.S | re.I)
    t = re.sub(r'<style.*?</style>', ' ', t, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', t))


def main():
    ensure_hosts()
    ip = reachable()
    print('[连通性] %s' % ('OK（%s）' % ip if ip else '失败：hosts 里的 IP 可能已变，需重新找 CF 真实 IP'))
    if not ip or '--check' in sys.argv:
        return 0 if ip else 1

    user, pw = load_cred()
    if not user or not pw:
        print('[错误] 未从 %s 读到凭据' % ENV)
        return 1
    if os.path.exists(COOKIE):
        os.remove(COOKIE)

    curl([BASE + '/user/account/login/', '-o', '/dev/null'])
    curl(['-X', 'POST', BASE + '/user/account/login/',
          '--data-urlencode', 'username=' + user,
          '--data-urlencode', 'password=' + pw,
          '-H', 'Referer: ' + BASE + '/user/account/login/',
          '-H', 'Origin: ' + BASE,
          '-H', 'Content-Type: application/x-www-form-urlencoded', '-o', '/dev/null'])

    home = curl([BASE + '/'])
    h = home.lower()
    logged_in = (user.lower() in h) and ('/user/account/logout' in h) and ('name="login-form"' not in h)
    if not logged_in:
        print('[结果] 登录失败（可能密码变更、账号被封或被限流）')
        err = re.findall(r'(?i)(incorrect|invalid|wrong|disabled|banned|too many)[^<>]{0,120}', text_of(home))
        if err:
            print('[服务端提示]', err[:3])
        return 1

    profile = text_of(curl([BASE + '/profile/' + user + '/']))
    def grab(pat, default='?'):
        m = re.search(pat, profile, re.I)
        return m.group(1).strip() if m else default

    stats = {
        'class': grab(r'Class\s+(\w[\w ]{0,20}?)\s+Registration'),
        'ratio': grab(r'ratio:\s*([\d.]+)'),
        'uploaded': grab(r'uploaded:\s*([\d.]+ \w+)'),
        'downloaded': grab(r'downloaded:\s*([\d.]+ \w+)'),
        'points': grab(r'TL Points:\s*([\d,\.]+)'),
        'last_visit': grab(r'Last visit\s*(.{0,80}?)\s*Invitations'),
    }
    print('[结果] 登录成功 ✅ Last visit 已刷新')
    for k, v in stats.items():
        print('   %-12s %s' % (k, v))
    print('[备注] TL 无每日签到，本步即全部保活动作；积分靠做种/成就获取')
    return 0


if __name__ == '__main__':
    sys.exit(main())
