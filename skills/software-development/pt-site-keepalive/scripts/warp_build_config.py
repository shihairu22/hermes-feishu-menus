#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 NAS mihomo 配置里的 WARP 端点换成 13 个扫描验证过的（0% 丢包）"""
import os  # 家目录展开（去敏时可移植化）
import subprocess, hashlib, sys

S = os.path.expanduser("~/.hermes/cache/scratch")

# ---------- 0. 从 NAS 拉最新配置 ----------
print("=== 0. 拉取 NAS 当前配置 ===")
subprocess.run(["scp", "-q", "nas:/path/to/mihomo/mihomo/config.yaml", f"{S}/nas_cur.yaml"], check=True)
raw = open(f"{S}/nas_cur.yaml", "rb").read()
md5 = hashlib.md5(raw).hexdigest()
_bom = raw[:3] == b"\xef\xbb\xbf"
print(f"  字节 {len(raw)}  md5 {md5}  BOM={_bom}")
# 只确认这是「上一轮改过的版本」：含 WARP 组 + byr 规则指向 WARP
_chk = raw.decode("utf-8-sig")
assert "- name: WARP" in _chk or '- name: "WARP"' in _chk, "NAS 配置里没有 WARP 组 —— 不是预期版本，停下"
assert "DOMAIN-SUFFIX,byr.pt,WARP" in _chk, "byr 规则未指向 WARP —— 不是预期版本，停下"
print("  ✓ 确认是上一轮改过的版本（含 WARP 组 + byr→WARP 规则）")

text = raw.decode("utf-8-sig")
lines = text.split("\n")

# ---------- 1. 从 warp_final.yaml 取模板字段（不打印私钥）----------
import yaml
wf = yaml.safe_load(open(f"{S}/warp_final.yaml", encoding="utf-8-sig"))
tmpl = wf["proxies"][0]
PK = tmpl["private-key"]
IPV6 = tmpl["ipv6"]
AWG = tmpl["amnezia-wg-option"]
PUB = tmpl["peers"][0]["public-key"]
print(f"  模板: private-key 长度={len(PK)}  ipv6={IPV6}  public-key={PUB[:16]}...")

# ---------- 2. 新端点表（来自 warpscout 扫描，0% 丢包）----------
ENDPOINTS = [
    ("WARP-SIN-1", "8.39.125.28",     1701),
    ("WARP-SIN-2", "8.35.211.163",     500),
    ("WARP-LAX-1", "8.34.70.101",     1701),
    ("WARP-LAX-2", "162.159.192.242",  500),
    ("WARP-LAX-3", "8.39.204.242",     500),
    ("WARP-LAX-4", "8.34.146.209",     500),
    ("WARP-LAX-5", "8.47.69.125",     1701),
    ("WARP-LAX-6", "8.39.214.2",       500),
    ("WARP-AMS-1", "188.114.99.92",   4500),
    ("WARP-AMS-2", "188.114.96.186",   500),
    ("WARP-AMS-3", "188.114.98.194",   500),
    ("WARP-AMS-4", "188.114.97.85",   1701),
    ("WARP-LAX-7", "8.6.112.47",      1701),
]
print(f"  新端点 {len(ENDPOINTS)} 个")

def entry(name, server, port):
    return f"""  - name: "{name}"
    type: wireguard
    private-key: {PK}
    ip: 172.16.0.2
    ipv6: {IPV6}
    peers:
      - server: {server}
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

# ---------- 3. 定位 proxies: 段 ----------
ps = pe = None
for i, l in enumerate(lines):
    if l.startswith("proxies:"):
        ps = i
        break
assert ps is not None, "找不到顶层 proxies:"
for j in range(ps + 1, len(lines)):
    if lines[j].startswith("proxy-groups:"):
        pe = j
        break
assert pe is not None, "找不到 proxy-groups:"
print(f"\n=== 1. 现有 proxies: 段 L{ps+1}..L{pe} （{pe-ps-1} 行）===")
print(f"  现有端点: {[l.split('server:')[1].strip() for l in lines[ps:pe] if 'server:' in l]}")

# ---------- 4. 定位 WARP 组 ----------
gi = None
for i, l in enumerate(lines):
    if l.rstrip() == "  - name: WARP" or l.rstrip() == '  - name: "WARP"':
        gi = i
        break
assert gi is not None, "找不到 WARP 组"
gj = len(lines)
for j in range(gi + 1, len(lines)):
    if lines[j].startswith("  - name:") or lines[j].startswith("rules:"):
        gj = j
        break
print(f"\n=== 2. WARP 组 L{gi+1}..L{gj} ===")
for n in range(gi, gj):
    print(f"  L{n+1}: {lines[n]}")

# ---------- 5. 构建 ----------
names = [e[0] for e in ENDPOINTS]
new_proxies = ["proxies:"] + [entry(*e) for e in ENDPOINTS]

# 组装：proxies 段之前 + 新 proxies 段 + proxy-groups 到 WARP 组之间 + 新组体 + 其余
new_group = []
for l in lines[gi:gj]:
    st = l.strip()
    if st.startswith("- WARP-") or st.startswith('- "WARP-'):
        continue                     # 丢掉旧的节点列表项
    new_group.append(l)
# 在组内的 proxies: 行后插入新名字
out_group = []
indent = "      "
inserted = False
for idx, l in enumerate(new_group):
    out_group.append(l)
    if l.strip().startswith("proxies:") and not inserted:
        for nm in names:
            out_group.append(f'{indent}- "{nm}"')
        inserted = True
assert inserted, "WARP 组里没有 proxies: 行 —— 结构变了，停下"

new = lines[:ps] + new_proxies + [""] + lines[pe:gi] + out_group + lines[gj:]
out = "\n".join(new)
if raw[:3] == b'\xef\xbb\xbf':
    out_bytes = b'\xef\xbb\xbf' + out.encode("utf-8")
else:
    out_bytes = out.encode("utf-8")
open(f"{S}/nas_config_v3.yaml", "wb").write(out_bytes)
print(f"\n=== 3. 已写 nas_config_v3.yaml  {len(out_bytes)} 字节  行数 {len(lines)} -> {len(new)} ===")

# ---------- 6. 自校验 ----------
chk = yaml.safe_load(out_bytes.decode("utf-8-sig"))
print("\n=== 4. 自校验 ===")
print(f"  proxies 数 = {len(chk.get('proxies', []))}")
print(f"  组数 = {len(chk.get('proxy-groups', []))}（原 73）")
g = [x for x in chk["proxy-groups"] if x.get("name") == "WARP"][0]
print(f"  WARP 组: type={g.get('type')} url={g.get('url')} interval={g.get('interval')} tolerance={g.get('tolerance')}")
print(f"  WARP 组 proxies 数 = {len(g.get('proxies', []))}")
print(f"  rules 数 = {len(chk.get('rules', []))}（原 127）")
byr = [r for r in chk["rules"] if "byr.pt" in r]
print(f"  byr 规则 = {byr}")
print(f"  V6代理 组存在 = {any(x.get('name')=='V6代理' for x in chk['proxy-groups'])}")
