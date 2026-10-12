#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""应用 v3 配置：备份 -> 校验 -> 热重载 -> 验证"""
import os  # 家目录展开（去敏时可移植化）
import subprocess, hashlib, time, json, urllib.request, yaml, datetime, sys

S = os.path.expanduser("~/.hermes/cache/scratch")
NAS = "nas"
BASE = "/path/to/mihomo/mihomo"
CTL = "http://127.0.0.1:9090"

raw_old = open(f"{S}/nas_cur.yaml", "rb").read()
cfg_old = yaml.safe_load(raw_old.decode("utf-8-sig"))
secret = cfg_old.get("secret", "")
print(f"=== 0. API secret 长度={len(secret)}  external-controller={cfg_old.get('external-controller')} ===")

def api(method, path, body=None, timeout=20):
    req = urllib.request.Request(CTL + path, method=method)
    if secret:
        req.add_header("Authorization", f"Bearer {secret}")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, repr(e)

# ---------- 1. 校验新配置 ----------
print("\n=== 1. 本地 mihomo -t 校验 ===")
r = subprocess.run([f"{S}/mihomo", "-t", "-f", f"{S}/nas_config_v3.yaml", "-d", S],
                   capture_output=True, text=True, timeout=120)
print("exit", r.returncode)
tail = (r.stdout + r.stderr).strip().split("\n")
for l in tail[-12:]:
    print("   ", l)
assert r.returncode == 0, "本地 mihomo -t 校验失败，中止"

# ---------- 2. 上传临时副本，容器内再校验 ----------
print("\n=== 2. 上传临时副本 + 容器内校验 ===")
subprocess.run(["scp", "-q", f"{S}/nas_config_v3.yaml", f"{NAS}:{BASE}/config_v3_test.yaml"], check=True)
for cand in ["mihomo", "/mihomo", "/usr/local/bin/mihomo"]:
    r2 = subprocess.run(["ssh", NAS,
        f"docker exec mihomo {cand} -t -d /root/.config/mihomo -f /root/.config/mihomo/config_v3_test.yaml 2>&1 | tail -6"],
        capture_output=True, text=True, timeout=180)
    out = (r2.stdout + r2.stderr).strip()
    if "not found" in out or "executable file not found" in out or "no such file" in out.lower():
        print(f"   {cand}: 不在容器里，换下一个")
        continue
    print(f"   容器内用 {cand}:")
    for l in out.split("\n")[-8:]:
        print("     ", l)
    break

# ---------- 3. 备份当前配置 ----------
ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
bak = f"{BASE}/config.yaml.bak-{ts}"
print(f"\n=== 3. 备份当前配置 -> config.yaml.bak-{ts} ===")
r3 = subprocess.run(["ssh", NAS, f"cp -a {BASE}/config.yaml {bak} && md5sum {bak} {BASE}/config.yaml"],
                    capture_output=True, text=True)
print(r3.stdout.strip() or r3.stderr.strip())
assert r3.returncode == 0, "备份失败，中止"

# ---------- 4. 覆盖 + 热重载 ----------
print("\n=== 4. 覆盖 config.yaml + 热重载 ===")
subprocess.run(["scp", "-q", f"{S}/nas_config_v3.yaml", f"{NAS}:{BASE}/config.yaml"], check=True)
r4 = subprocess.run(["ssh", NAS, f"md5sum {BASE}/config.yaml"], capture_output=True, text=True)
print("   新文件:", r4.stdout.strip())
print("   预期  :", hashlib.md5(open(f'{S}/nas_config_v3.yaml','rb').read()).hexdigest())

st, body = api("PUT", "/configs?force=true", {"path": os.path.expanduser("~/.config/mihomo/config.yaml")}, timeout=60)
print(f"   热重载 HTTP {st}  body={body[:200]}")
assert st in (200, 204), "热重载失败 —— 需回滚"

# ---------- 5. 验证 ----------
print("\n=== 5. 等待 10s 后验证 ===")
time.sleep(10)
st, body = api("GET", "/proxies/WARP")
if st == 200:
    d = json.loads(body)
    print(f"   WARP 组 now={d.get('now')}  alive={d.get('alive')}  成员数={len(d.get('all', []))}")
    print(f"   成员: {d.get('all')}")
else:
    print("   /proxies/WARP ->", st, body[:200])

print("\n   逐节点测速（经 byr.pt 健康检查，超时 6s）...")
st, body = api("GET", "/group/WARP/delay?url=https%3A%2F%2Fbyr.pt%2F&timeout=6000", timeout=180)
if st == 200:
    d = json.loads(body)
    ok = {k: v for k, v in d.items() if isinstance(v, int) and v > 0}
    bad = [k for k, v in d.items() if not (isinstance(v, int) and v > 0)]
    print(f"   通过 {len(ok)}/{len(d)}:")
    for k, v in sorted(ok.items(), key=lambda x: x[1]):
        print(f"      {k:14s} {v} ms")
    print(f"   失败: {bad}")
else:
    print("   delay ->", st, body[:200])

print("\n=== 6. 经代理实测 ===")
for url in ["https://byr.pt/", "https://www.google.com/generate_204", "https://github.com/"]:
    r6 = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code} %{time_total}s",
                         "--max-time", "20", "-x", "http://127.0.0.1:7890", url],
                        capture_output=True, text=True)
    print(f"   {url:42s} -> {r6.stdout.strip()}")
