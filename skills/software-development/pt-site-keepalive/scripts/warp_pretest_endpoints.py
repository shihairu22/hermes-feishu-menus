#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修正版：带 external-controller，先验证中文名 API，再逐地区实测"""
import os  # 家目录展开（去敏时可移植化）
import re, glob, os, json, subprocess, time, urllib.request, urllib.parse, signal, http.client, yaml

W = os.path.expanduser("~/.warp"); S = os.path.expanduser("~/.hermes/cache/scratch"); T = f"{S}/pretest"
PER_REGION = 20; PROXY_PORT = 7998; API_PORT = 9099

rep = sorted(glob.glob(f"{W}/warpscout-report-*.txt"))[-1]
pat = re.compile(r"^(\d+\.\d+\.\d+\.\d+):(\d+)\s+(\d+)ms\s+(\d+)ms\s+(\d+)%\s+(\S+)\s+(SIN|LAX|AMS)\s+")
rows = [dict(ip=m.group(1), port=int(m.group(2)), tun=int(m.group(4)), loss=int(m.group(5)), node=m.group(7))
        for m in (pat.match(l.strip()) for l in open(rep, encoding="utf-8")) if m]
CN = {"SIN": "新加坡", "LAX": "洛杉矶", "AMS": "阿姆斯特丹"}
cand = {n: sorted([r for r in rows if r["loss"] == 0 and r["node"] == n], key=lambda x: x["tun"])[:PER_REGION] for n in CN}
print("=== 候选 ===", {CN[n]: len(cand[n]) for n in CN})

cfg = yaml.safe_load(open(f"{W}/nas_config_live.yaml", encoding="utf-8-sig"))
t = cfg["proxies"][0]
PK, IPV6, PUB, AWG = t["private-key"], t["ipv6"], t["peers"][0]["public-key"], t["amnezia-wg-option"]
def proxy(name, ip, port):
    return {"name": name, "type": "wireguard", "private-key": PK, "ip": "172.16.0.2", "ipv6": IPV6,
            "peers": [{"server": ip, "port": port, "public-key": PUB,
                       "allowed-ips": ["0.0.0.0/0", "::/0"], "persistent-keepalive": 25}],
            "amnezia-wg-option": AWG, "udp": True, "remote-dns-resolve": True,
            "dns": ["1.1.1.1", "1.0.0.1"], "mtu": 1280}
proxies, groups, mapping = [], [], {}
for n, cn in CN.items():
    names = []
    for i, r in enumerate(cand[n], 1):
        nm = f"{cn}-{i:02d}"; names.append(nm); mapping[nm] = r
        proxies.append(proxy(nm, r["ip"], r["port"]))
    groups.append({"name": cn, "type": "url-test", "url": "https://byr.pt/",
                   "interval": 120, "tolerance": 100, "lazy": False, "proxies": names})
test = {"mixed-port": PROXY_PORT, "external-controller": f"127.0.0.1:{API_PORT}",
        "mode": "rule", "log-level": "warning", "ipv6": True,
        "dns": {"enable": True, "ipv6": True, "nameserver": ["https://1.1.1.1/dns-query"],
                "proxy-server-nameserver": ["223.5.5.5"]},
        "proxies": proxies, "proxy-groups": groups, "rules": ["MATCH,DIRECT"]}
os.makedirs(T, exist_ok=True)
open(f"{T}/config.yaml", "w").write(yaml.safe_dump(test, allow_unicode=True, sort_keys=False))
print(f"=== 出站 {len(proxies)} 个，代理端口 {PROXY_PORT}，API 端口 {API_PORT} ===")

def raw_get(path, port=None):
    c = http.client.HTTPConnection("127.0.0.1", port or API_PORT, timeout=300)
    c.putrequest("GET", path, skip_accept_encoding=True); c.endheaders()
    r = c.getresponse(); b = r.read().decode("utf-8", "replace"); c.close()
    return r.status, b

proc = subprocess.Popen([f"{W}/mihomo", "-f", f"{T}/config.yaml", "-d", T],
                        stdout=open(f"{T}/mihomo3.log", "w"), stderr=subprocess.STDOUT)
results = {}
try:
    time.sleep(12)
    st, b = raw_get("/proxies")
    d = json.loads(b)
    print(f"\n=== 1. API 通了（HTTP {st}）===")
    cn_names = [k for k in d["proxies"] if not k.isascii()]
    print(f"  非 ASCII 名字 {len(cn_names)} 个；新加坡 组 type={d['proxies']['新加坡']['type']} 成员={len(d['proxies']['新加坡']['all'])}")

    print("\n=== 2. 中文组名 API 路径（两种编码）===")
    q = "?url=https%3A%2F%2Fbyr.pt%2F&timeout=8000"
    for label, path in [("百分号编码", "/group/" + urllib.parse.quote("新加坡") + "/delay" + q),
                        ("原始 UTF-8", "/group/新加坡/delay" + q)]:
        try:
            st, b = raw_get(path)
            n = len([k for k, v in json.loads(b).items() if isinstance(v, int) and v > 0]) if st == 200 else "-"
            print(f"  {label:10s} -> HTTP {st}  通过 {n}  {b[:120] if st != 200 else ''}")
        except Exception as e:
            print(f"  {label:10s} -> 异常 {e!r}")

    print("\n=== 3. 逐地区实测（用能通的编码）===")
    for n, cn in CN.items():
        for label, path in [("enc", "/group/" + urllib.parse.quote(cn) + "/delay" + q),
                            ("raw", "/group/" + cn + "/delay" + q)]:
            st, b = raw_get(path)
            if st == 200:
                dd = json.loads(b)
                ok = {k: v for k, v in dd.items() if isinstance(v, int) and v > 0}
                results[cn] = ok
                print(f"\n  【{cn}】通过 {len(ok)}/{len(dd)}  ({label})")
                for k, v in sorted(ok.items(), key=lambda x: x[1]):
                    print(f"     {k:12s} {v:5d}ms   {mapping[k]['ip']}:{mapping[k]['port']}")
                bad = [k for k in dd if k not in ok]
                if bad:
                    print(f"     未通过（删掉）: {[(k, mapping[k]['ip']) for k in bad]}")
                break
            else:
                print(f"  【{cn}】{label} -> HTTP {st}")
finally:
    proc.send_signal(signal.SIGTERM)
    try: proc.wait(timeout=10)
    except Exception: proc.kill()

json.dump({"keep": {cn: [k for k, _ in sorted(v.items(), key=lambda x: x[1])] for cn, v in results.items()},
           "detail": {cn: dict(v) for cn, v in results.items()}},
          open(f"{W}/warp_verified.json", "w"), ensure_ascii=False, indent=1)
print(f"\n=== 4. 通过数 { {cn: len(v) for cn, v in results.items()} }  合计 {sum(len(v) for v in results.values())} ===")
