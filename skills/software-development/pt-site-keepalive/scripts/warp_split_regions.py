#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v4：把 WARP 按地区拆成独立策略组
WARP(select) -> WARP-AUTO / WARP-SIN / WARP-LAX / WARP-AMS
"""
import os  # 家目录展开（去敏时可移植化）
import subprocess, hashlib, yaml

S = os.path.expanduser("~/.hermes/cache/scratch")
NAS = "nas"
BASE = "/path/to/mihomo/mihomo"

# ---------- 1. 拉当前线上配置 ----------
print("=== 1. 拉取 NAS 当前配置 ===")
subprocess.run(["scp", "-q", f"{NAS}:{BASE}/config.yaml", f"{S}/nas_cur.yaml"], check=True)
raw = open(f"{S}/nas_cur.yaml", "rb").read()
print(f"  {len(raw)} 字节  md5={hashlib.md5(raw).hexdigest()}")
text = raw.decode("utf-8-sig")
lines = text.split("\n")
cfg = yaml.safe_load(text)
names = [p["name"] for p in cfg["proxies"]]
print(f"  出站 {len(names)} 个: {names}")

# ---------- 2. 按地区归类 ----------
regions = {}
for n in names:
    # WARP-SIN-1 / WARP-LAX-3 / WARP-AMS-2
    parts = n.split("-")
    reg = parts[1]
    regions.setdefault(reg, []).append(n)
print(f"  地区: { {k: len(v) for k, v in regions.items()} }")

# ---------- 3. 定位旧 WARP 组 ----------
gi = gj = None
for i, l in enumerate(lines):
    if l.rstrip() in ('  - name: WARP', '  - name: "WARP"'):
        gi = i
        break
assert gi is not None, "找不到 WARP 组"
for j in range(gi + 1, len(lines)):
    if lines[j].startswith("  - name:") or lines[j].startswith("rules:"):
        gj = j
        break
print(f"\n=== 2. 旧 WARP 组 L{gi+1}..L{gj} ===")
for n in range(gi, gj):
    print("  " + lines[n])

# ---------- 4. 生成新组 ----------
def ut(name, members):
    out = [f'  - name: "{name}"', "    type: url-test",
           "    url: https://byr.pt/", "    interval: 120",
           "    tolerance: 100", "    lazy: false", "    proxies:"]
    out += [f'      - "{m}"' for m in members]
    return out

order = [r for r in ("SIN", "LAX", "AMS") if r in regions] + [r for r in regions if r not in ("SIN", "LAX", "AMS")]
region_groups = [f"WARP-{r}" for r in order]

new_block = []
# 主入口：select，默认 WARP-AUTO（= 现在的行为）
new_block += ['  - name: "WARP"', "    type: select", "    proxies:"]
new_block += ['      - "WARP-AUTO"'] + [f'      - "{g}"' for g in region_groups] + ['      - "DIRECT"']
# AUTO = 全量
new_block += ut("WARP-AUTO", names)
# 各地区
for r in order:
    new_block += ut(f"WARP-{r}", regions[r])

new = lines[:gi] + new_block + lines[gj:]
out = "\n".join(new)
out_bytes = (b"\xef\xbb\xbf" + out.encode("utf-8")) if raw[:3] == b"\xef\xbb\xbf" else out.encode("utf-8")
open(f"{S}/nas_config_v4.yaml", "wb").write(out_bytes)
print(f"\n=== 3. 已写 nas_config_v4.yaml  {len(out_bytes)} 字节 ===")

# ---------- 5. 自校验 ----------
chk = yaml.safe_load(out_bytes.decode("utf-8-sig"))
groups = {g["name"]: g for g in chk["proxy-groups"]}
print("\n=== 4. 自校验 ===")
print(f"  出站数 = {len(chk['proxies'])}（应 {len(names)}）")
print(f"  组数 = {len(chk['proxy-groups'])}（原 {len(cfg['proxy-groups'])}）")
print(f"  规则数 = {len(chk['rules'])}（原 {len(cfg['rules'])}）")
for g in ["WARP"] + [f"WARP-{r}" for r in order] + ["WARP-AUTO"]:
    x = groups[g]
    print(f"  {g:12s} type={x['type']:9s} 成员 {len(x['proxies']):2d}  {x['proxies'] if len(x['proxies'])<=6 else x['proxies'][:4]+['...']}")
print(f"  byr 规则 = {[r for r in chk['rules'] if 'byr.pt' in r]}")
print(f"  V6代理 组仍在 = {'V6代理' in groups}")

# 逐行比对：除 WARP 组区间外，其余必须完全一致
import difflib
d = list(difflib.unified_diff(cfg["rules"], chk["rules"], lineterm=""))
print(f"\n  规则逐条比对差异行数 = {len(d)}")
print(f"  出站列表一致 = {[p['name'] for p in chk['proxies']] == names}")
