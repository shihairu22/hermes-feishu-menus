#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""泄漏扫描：确保分发包里没有本机 / 个人 / 凭据痕迹。

用法：
  python3 scripts/scan-leaks.py            # 扫工作区（git 跟踪的文件）
  python3 scripts/scan-leaks.py --history  # 连 git 全历史一起扫
  LEAK_EXTRA_PATTERNS='api.example.cn<换行>1234567890' python3 scripts/scan-leaks.py

设计要点
--------
1. **本脚本本身不含任何秘密**（它是公开文件）。默认只放**结构性**模式
   （飞书 ID 形状、Bearer/私钥/ticket、家目录绝对路径、另一套 agent 系统的名字等）。
   真正私有的值（自建中转站域名、聊天 ID 之类）通过环境变量 `LEAK_EXTRA_PATTERNS`
   或 gitignore 的 `.leak-patterns` 文件注入 —— 绝不写进仓库。
2. **绝不回显命中内容**：只报 `文件:行号:规则名`，避免扫描输出本身变成新的泄漏源。
3. 允许清单：公开归属（仓库 URL / LICENSE 里的作者名）不算泄漏。
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# ── 结构性模式（安全，可公开）────────────────────────────────────────
# name -> 正则
PATTERNS = {
    "feishu-open-id": r"\b(?:oc|ou|om)_[0-9a-f]{12,}\b",
    "bearer-token": r"Bearer\s+[A-Za-z0-9._\-]{20,}",
    "ws-ticket": r"\b(?:access_key|ticket)=[A-Za-z0-9\-]{8,}",
    "private-key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "home-abs-path": r"(?<![A-Za-z0-9_])/root/",
    "persona-name": r"艾莉娅|爱莉娅|\bElia\b",
    "other-agent-system": r"openclaw|OpenClaw|小龙虾",
    "private-infra": r"群晖|synology|Synology|mihomo|warp-cli|cloudflared",
    "private-lan": r"\b10\.0\.0\.\d{1,3}\b",
    "cred-file": r"cookies\.sqlite|_cookies\.txt|creds-backup",
}

# 这些文件里出现「作者名」是公开归属（仓库 URL、许可证），不算泄漏。
ALLOW_FILES = {
    "LICENSE", "README.md",
}
ALLOW_PATTERNS_IN = {
    "LICENSE": {"author-handle"},
    "README.md": {"author-handle"},
}

# 公开归属用的作者名（GitHub handle）。出现在其它文件里才算可疑。
AUTHOR_HANDLE = r"shihairu"

# 二进制 / 不该扫的路径
SKIP_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2",
               ".ttf", ".zip", ".gz", ".pyc", ".so", ".bin", ".mp4", ".mp3")

# 本扫描器自身 + 去敏生成器：它们的模式表/规则表**就是**这些字面量的来源，必然自匹配。
#
# 为什么这样处理是安全的：
#   · scan-leaks.py 只放**结构性**模式（飞书 ID 形状、Bearer/私钥形状等），
#     真实私有值走 LEAK_EXTRA_PATTERNS 环境变量或 gitignore 的 .leak-patterns；
#   · sanitize-live-to-assets.py 的规则表里出现的私有字面量（家目录、人设名、
#     私人技能分类名）是**去敏的来源**——不写它就无从替换。这些内容
#     SANITIZED.md 里已逐条公开披露，不属于「新增泄漏」。
#   · 两者都不含任何凭据（chat id / 中转站域名 / token 一律不在仓库里）。
#
# 需要连它们一起审查时：`--strict`（会列出上述已知披露项）。
SOURCE_SKIP = {"scripts/scan-leaks.py", "scripts/sanitize-live-to-assets.py"}


def extra_patterns() -> dict:
    """私有模式：环境变量 + gitignore 的 .leak-patterns（不进仓库）。"""
    out = {}
    raw = os.environ.get("LEAK_EXTRA_PATTERNS", "")
    fp = Path(__file__).resolve().parent.parent / ".leak-patterns"
    if fp.exists():
        raw += "\n" + fp.read_text(encoding="utf-8")
    for i, line in enumerate(l.strip() for l in raw.splitlines()):
        if not line or line.startswith("#"):
            continue
        out[f"private-{i}"] = re.escape(line)
    return out


def scan_text(name: str, text: str, pats: dict, label: str) -> list:
    hits = []
    allow = ALLOW_PATTERNS_IN.get(name, set())
    for rule, rx in pats.items():
        if rule in allow:
            continue
        for m in re.finditer(rx, text, re.I):
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{label}:{line}:{rule}")     # 绝不带命中内容
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", action="store_true", help="连 git 全历史一起扫")
    ap.add_argument("--strict", action="store_true",
                    help="连去敏生成器/扫描器自身一起扫（会列出已知公开披露项）")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    a = ap.parse_args()
    repo = Path(a.repo)
    os.chdir(repo)

    pats = dict(PATTERNS)
    pats["author-handle"] = AUTHOR_HANDLE
    pats.update(extra_patterns())

    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                           check=True).stdout.split()
    files = [f for f in files if not f.endswith(SKIP_SUFFIX)]
    if not a.strict:
        files = [f for f in files if f not in SOURCE_SKIP]

    hits = []
    for f in files:
        p = repo / f
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits += scan_text(f, text, pats, f)

    if a.history:
        revs = subprocess.run(["git", "rev-list", "--all"], capture_output=True,
                              text=True).stdout.split()
        for r in revs:
            for f in subprocess.run(["git", "ls-tree", "-r", "--name-only", r],
                                    capture_output=True, text=True).stdout.split():
                if f.endswith(SKIP_SUFFIX):
                    continue
                blob = subprocess.run(["git", "show", f"{r}:{f}"], capture_output=True,
                                      text=True).stdout
                hits += scan_text(f, blob, pats, f"history:{r[:8]}:{f}")

    print(f"扫描 {len(files)} 个跟踪文件" + ("（含全历史）" if a.history else "")
          + f"，模式 {len(pats)} 条")
    if hits:
        print(f"\n✗ 命中 {len(hits)} 处（只报位置，不回显内容）：")
        for h in hits[:60]:
            print("   " + h)
        if len(hits) > 60:
            print(f"   … 另有 {len(hits) - 60} 处")
        return 1
    print("✓ 无泄漏")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
