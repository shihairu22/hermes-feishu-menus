#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""应用 v6：备份 → 容器内 mihomo -t 校验 → 热重载 → 验证"""
import os  # 家目录展开（去敏时可移植化）
import subprocess, time, json, hashlib, urllib.request, urllib.parse, yaml, sys

S = os.path.expanduser("~/.hermes/cache/scratch"); NAS = "nas"
BASE = "/path/to/mihomo/mihomo"; INSIDE = os.path.expanduser("~/.config/mihomo")
API = "http://127.0.0.1:9090"
TS = time.strftime("%Y%m%d-%H%M%S")

def sh(cmd, **kw):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def api(path, method="GET", body=None, secret=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Authorization", f"Bearer {secret}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, r.read().decode("utf-8", "replace")

cur = open(f"{S}/nas_cur.yaml", "rb").read()
secret = yaml.safe_load(cur.decode("utf-8-sig"))["secret"]
new = open(f"{S}/nas_config_v6.yaml", "rb").read()
print(f"新配置 {len(new)} 字节 md5={hashlib.md5(new).hexdigest()}")

# ---------- 0. 容器 ----------
rc, out, _ = sh(f"ssh {NAS} \"/usr/local/bin/docker ps --format '{{{{.Names}}}}|{{{{.Image}}}}|{{{{.Status}}}}' | grep -i mihomo\"")
print(f"\n=== 0. 容器 ===\n  {out}")
cname = out.split("|")[0] if out else "mihomo"

# ---------- 1. 备份 ----------
bak = f"{BASE}/config.yaml.bak-{TS}"
rc, out, err = sh(f"ssh {NAS} \"cp {BASE}/config.yaml {bak} && md5sum {bak} && ls -la {bak}\"")
print(f"\n=== 1. 备份 -> {bak} ===\n  {out}\n  rc={rc} {err[:200]}")

# ---------- 2. 上传为 .new ----------
rc, out, err = sh(f"scp -q {S}/nas_config_v6.yaml {NAS}:{BASE}/config.yaml.new && ssh {NAS} 'md5sum {BASE}/config.yaml.new'")
print(f"\n=== 2. 上传 config.yaml.new ===\n  {out}  rc={rc} {err[:200]}")

# ---------- 3. 容器内校验 ----------
print("\n=== 3. 容器内 mihomo -t 校验 ===")
ok = False
for binp in ["/mihomo"]:
    rc, out, err = sh(f"ssh {NAS} \"/usr/local/bin/docker exec {cname} {binp} -t -f {INSIDE}/config.yaml.new\"")
    tail = (out + "\n" + err).strip().split("\n")
    print(f"  [{binp}] rc={rc}  {tail[-1][:200] if tail else ''}")
    if rc == 0:
        ok = True; break
print(f"  校验结果: {'通过' if ok else '失败'}")
if not ok:
    print("  ✗ 中止，未改动线上配置"); sys.exit(1)

# ---------- 4. 就位 + 热重载 ----------
rc, out, err = sh(f"ssh {NAS} \"mv {BASE}/config.yaml.new {BASE}/config.yaml && md5sum {BASE}/config.yaml\"")
print(f"\n=== 4. 就位 ===\n  {out}")
st, body = api("/configs?force=true", "PUT", {"path": "", "payload": ""}, secret)
print(f"\n=== 5. 热重载 -> HTTP {st} ===")
time.sleep(6)

# ---------- 5. 验证 ----------
st, body = api("/proxies/WARP", secret=secret)
d = json.loads(body)
print(f"\n=== 6. WARP 组 ===")
print(f"  type={d['type']}  now={d['now']}  候选={d['all']}")
st, body = api("/proxies/" + urllib.parse.quote("自动选最快"), secret=secret)
d2 = json.loads(body)
print(f"  自动选最快: {len(d2['all'])} 成员  now={d2['now']}")

st, body = api("/proxies/WARP", "PUT", {"name": "自动选最快"}, secret)
print(f"\n=== 7. 设为 自动选最快 -> HTTP {st} ===")

for g in ["自动选最快", "新加坡", "洛杉矶", "阿姆斯特丹"]:
    q = "/group/" + urllib.parse.quote(g) + "/delay?url=https%3A%2F%2Fbyr.pt%2F&timeout=10000"
    try:
        st, body = api(q, secret=secret)
        dd = json.loads(body)
        good = {k: v for k, v in dd.items() if isinstance(v, int) and v > 0}
        print(f"  【{g}】{len(good)}/{len(dd)} 通  最快 {min(good.values()) if good else '-'}ms")
    except Exception as e:
        print(f"  【{g}】异常 {e!r}")

print("\n=== 8. 端到端 ===")
for label, cmd in [
    ("经代理 byr.pt", f"curl -s -o /dev/null -w '%{{http_code}} %{{time_total}}s' -x http://127.0.0.1:7890 https://byr.pt/"),
    ("直连  byr.pt",  f"curl -s -o /dev/null -w '%{{http_code}} %{{time_total}}s' --noproxy '*' https://byr.pt/"),
    ("经代理 google", f"curl -s -o /dev/null -w '%{{http_code}} %{{time_total}}s' -x http://127.0.0.1:7890 https://www.google.com/generate_204"),
    ("经代理 github", f"curl -s -o /dev/null -w '%{{http_code}} %{{time_total}}s' -x http://127.0.0.1:7890 https://github.com/"),
]:
    rc, out, err = sh(cmd)
    print(f"  {label}: {out or err[:120]}")

rc, out, _ = sh(f"ssh {NAS} \"/usr/local/bin/docker ps --format '{{{{.Names}}}} {{{{.Status}}}}' | grep -i mihomo\"")
print(f"\n=== 9. 容器状态（应仍为 Up，未重启）===\n  {out}")
