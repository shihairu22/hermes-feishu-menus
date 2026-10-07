#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重算两层校验和（内层 → 外层，顺序不可颠倒）。

- 内层 `assets/<插件>/SHA256SUMS`：只覆盖该插件的分发文件（保持原顺序）。
- 外层 `MANIFEST.sha256`：**自动发现** git 跟踪的全部文件（不再手工维护清单，
  新增文件不会再漏进 MANIFEST 导致漂移）。排除自身与不需要校验的元文件。
- 末尾自检：`sha256sum -c` 内层两份 + 外层。

用法：python3 scripts/regen-sums.py [--repo <目录>]
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

# 外层不纳入的文件：自身（会自指）、纯元信息、CI 配置
MANIFEST_EXCLUDE = {
    "MANIFEST.sha256",
    ".gitignore",
    "LICENSE",
}
MANIFEST_EXCLUDE_PREFIX = (".github/",)

INNER = {
    "feishu-menu-bridge": ["__init__.py", "keeper.py", "plugin.yaml", "skill_zh.json"],
    "feishu-model-picker": ["__init__.py", "keeper.py", "plugin.yaml"],
}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write(fp: Path, items) -> None:
    fp.write_text("".join(f"{h}  {p}\n" for h, p in items), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    a = ap.parse_args()
    repo = Path(a.repo)

    # ── 1) 内层 ──
    for plugin, files in INNER.items():
        d = repo / "assets" / plugin
        missing = [f for f in files if not (d / f).exists()]
        if missing:
            print(f"!! assets/{plugin} 缺文件：{missing}")
            return 2
        write(d / "SHA256SUMS", [(sha(d / f), f) for f in files])
        print(f"[内层] assets/{plugin}/SHA256SUMS：{len(files)} 项")

    # ── 2) 外层（自动发现 git 跟踪文件）──
    out = subprocess.run(["git", "-C", str(repo), "ls-files"],
                         capture_output=True, text=True, check=True).stdout.split()
    picked = sorted(
        f for f in out
        if f not in MANIFEST_EXCLUDE and not f.startswith(MANIFEST_EXCLUDE_PREFIX)
    )
    if not picked:
        print("!! git ls-files 为空 —— 是否还没 git add？")
        return 2
    write(repo / "MANIFEST.sha256", [(sha(repo / f), f"./{f}") for f in picked])
    print(f"[外层] MANIFEST.sha256：{len(picked)} 项（自动发现）")

    # ── 3) 自检 ──
    print("\n[自检]")
    rc = 0
    for plugin in INNER:
        r = subprocess.run(["sha256sum", "-c", "SHA256SUMS"],
                           cwd=repo / "assets" / plugin, capture_output=True, text=True)
        print(f"  assets/{plugin}/SHA256SUMS → exit={r.returncode}")
        rc |= r.returncode
    r = subprocess.run(["sha256sum", "-c", "MANIFEST.sha256"],
                       cwd=repo, capture_output=True, text=True)
    bad = [ln for ln in r.stdout.splitlines() if not ln.endswith(": OK")]
    print(f"  MANIFEST.sha256 → exit={r.returncode}，失败 {len(bad)} 项")
    if bad:
        print("\n".join(bad[:10]))
    rc |= r.returncode
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
