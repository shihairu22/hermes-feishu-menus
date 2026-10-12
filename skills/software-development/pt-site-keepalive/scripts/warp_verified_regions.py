#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6：只装实测通过的端点，全中文名，按地区分组"""
import os  # 家目录展开（去敏时可移植化）
import subprocess, hashlib, re, yaml, glob, json, difflib

S = os.path.expanduser("~/.hermes/cache/scratch"); W = os.path.expanduser("~/.warp")
NAS = "nas"; BASE = "/path/to/mihomo/mihomo"
CN = {"SIN": "新加坡", "LAX": "洛杉矶", "AMS": "阿姆斯特丹"}

# ---------- 1. 候选映射（与实测脚本同逻辑）----------
rep = sorted(glob.glob(f"{W}/warpscout-report-*.txt"))[-1]
pat = re.compile(r"^(\d+\.\d+\.\d+\.\d+):(\d+)\s+(\d+)ms\s+(\d+)ms\s+(\d+)%\s+(\S+)\s+(SIN|LAX|AMS)\s+")
rows = [dict(ip=m.group(1), port=int(m.group(2)), tun=int(m.group(4)), loss=int(m.group(5)), node=m.group(7))
        for m in (pat.match(l.strip()) for l in open(rep, encoding="utf-8")) if m]
mapping = {}
for n, cn in CN.items():
    pool = sorted([r for r in rows if r["loss"] == 0 and r["node"] == n], key=lambda x: x["tun"])[:20]
    for i, r in enumerate(pool, 1):
        mapping[f"{cn}-{i:02d}"] = r

# ---------- 2. 实测通过名单 ----------
ver = json.load(open(f"{W}/warp_verified.json", encoding="utf-8"))
kept = {}
for cn, names in ver["keep"].items():
    # 按实测延迟排序，重编号 01..N
    ordered = sorted(names, key=lambda k: ver["detail"][cn].get(k, 99999))
    kept[cn] = [(f"{cn}-{i:02d}", mapping[k]) for i, k in enumerate(ordered, 1)]
print("=== 1. 实测通过的端点（重编号）===")
for cn, names in ver["keep"].items():
    ordered = sorted(names, key=lambda k: ver["detail"][cn].get(k, 99999))
    kept[cn] = [(f"{cn}-{i:02d}", mapping[k]) for i, k in enumerate(ordered, 1)]
    print(f"  {cn}: {len(kept[cn])} 个")
    for i, k in enumerate(ordered):
        nm, r = kept[cn][i]
        print(f"    {nm:12s} {r['ip']}:{r['port']:<5d} {ver['detail'][cn][k]}ms")

# ---------- 3. 拉线上配置 ----------
print("\n=== 2. 拉线上配置 ===")
subprocess.run(["scp", "-q", f"{NAS}:{BASE}/config.yaml", f"{S}/nas_cur.yaml"], check=True)
raw = open(f"{S}/nas_cur.yaml", "rb").read()
text = raw.decode("utf-8-sig"); lines = text.split("\n")
cfg = yaml.safe_load(text)
print(f"  {len(raw)} 字节 md5={hashlib.md5(raw).hexdigest()}")
print(f"  现有出站: {[p['name'] for p in cfg['proxies']]}")

tmpl = cfg["proxies"][0]
PK, IPV6, PUB, AWG = tmpl["private-key"], tmpl["ipv6"], tmpl["peers"][0]["public-key"], tmpl["amnezia-wg-option"]
def entry(name, ip, port):
    return f"""  - name: "{name}"
    type: wireguard
    private-key: {PK}
    ip: 172.16.0.2
    ipv6: {IPV6}
    peers:
      - server: {ip}
        port: {port}
        public-key: {PUB}
        allowed-ips: ['0.0.0.0/0', '::/0']
        persistent-keepalive: 25
    amnezia-wg-option:
      jc: {AWG['jc']}
      jmin: {AWG['jmin']}
      jmax: {AWG['jmax']}
      s1: {AWG['s1']}
      s2: {AWG['s2']}
      h1: {AWG['h1']}
      h2: {AWG['h2']}
      h3: {AWG['h3']}
      h4: {AWG['h4']}
      i1: {AWG['i1']}
    udp: true
    remote-dns-resolve: true
    dns: ['1.1.1.1', '1.0.0.1']
    mtu: 1280"""

new_proxies = ["proxies:"]
for cn, lst in kept.items():
    for nm, r in lst:
        new_proxies.append(entry(nm, r["ip"], r["port"]))
allnames = [nm for cn, lst in kept.items() for nm, _ in lst]

def ut(name, members):
    return [f'  - name: "{name}"', "    type: url-test", "    url: https://byr.pt/",
            "    interval: 120", "    tolerance: 100", "    lazy: false", "    proxies:"] + \
           [f'      - "{m}"' for m in members]

new_groups = ['  - name: "WARP"', "    type: select", "    proxies:", '      - "自动选最快"'] + \
             [f'      - "{cn}"' for cn in kept] + ['      - "DIRECT"']
new_groups += ut("自动选最快", allnames)
for cn, lst in kept.items():
    new_groups += ut(cn, [nm for nm, _ in lst])

# ---------- 4. 定位：旧 proxies 段 + 整个旧 WARP 家族 ----------
ps = next(i for i, l in enumerate(lines) if l.startswith("proxies:"))
pe = next(j for j in range(ps + 1, len(lines)) if lines[j].startswith("proxy-groups:"))
gi = next(i for i, l in enumerate(lines) if l.rstrip() in ('  - name: WARP', '  - name: "WARP"'))
FAM = {"WARP", "WARP-AUTO", "WARP-SIN", "WARP-LAX", "WARP-AMS"}
gj = len(lines)
for j in range(gi + 1, len(lines)):
    if lines[j].startswith("rules:"):
        gj = j; break
    if lines[j].startswith("  - name:"):
        nm = lines[j].split(":", 1)[1].strip().strip('"')
        if nm not in FAM:
            gj = j; break
print(f"\n=== 3. 替换区间 ===")
print(f"  proxies: L{ps+1}..L{pe}")
print(f"  旧 WARP 家族: L{gi+1}..L{gj}")
old_fam = [lines[k].split(":", 1)[1].strip().strip('"') for k in range(gi, gj) if lines[k].startswith("  - name:")]
print(f"  将移除的组: {old_fam}")

new = lines[:ps] + new_proxies + [""] + lines[pe:gi] + new_groups + lines[gj:]
out = "\n".join(new)
out_bytes = (b"\xef\xbb\xbf" + out.encode("utf-8")) if raw[:3] == b"\xef\xbb\xbf" else out.encode("utf-8")
open(f"{S}/nas_config_v6.yaml", "wb").write(out_bytes)
print(f"\n=== 4. 已写 nas_config_v6.yaml {len(out_bytes)} 字节 ===")

# ---------- 5. 自校验 ----------
chk = yaml.safe_load(out_bytes.decode("utf-8-sig"))
groups = {g["name"]: g for g in chk["proxy-groups"]}
names_now = [p["name"] for p in chk["proxies"]]
print("\n=== 5. 自校验 ===")
print(f"  出站 {len(names_now)}（原 {len(cfg['proxies'])}）")
print(f"  组 {len(chk['proxy-groups'])}（原 {len(cfg['proxy-groups'])}）")
print(f"  规则 {len(chk['rules'])}  差异行 = {len(list(difflib.unified_diff(cfg['rules'], chk['rules'], lineterm='')))}")
print(f"  组名: {sorted(groups)}")
for g in ["WARP", "自动选最快"] + list(kept):
    print(f"  {g:10s} type={groups[g]['type']:9s} 成员 {len(groups[g]['proxies'])}")
print(f"  byr 规则 = {[r for r in chk['rules'] if 'byr.pt' in r]}")
print(f"  V6代理 组仍在 = {'V6代理' in groups}")
print(f"  出站名全非 ASCII = {all(not n.isascii() for n in names_now)}")
print(f"  出站名无重复 = {len(names_now) == len(set(names_now))}")
assert len(names_now) == len(set(names_now))
assert 'V6代理' in groups
assert [r for r in chk['rules'] if 'byr.pt' in r] == ['DOMAIN-SUFFIX,byr.pt,WARP']
print("  ✓ 全部断言通过")
