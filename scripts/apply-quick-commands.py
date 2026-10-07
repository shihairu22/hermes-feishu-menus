#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 quick_commands.yaml 合并进 Hermes 的 config.yaml。

设计取舍
--------
* **文本级、块内合并**：只改 `quick_commands:` 这一块，文件其余字节原样保留。
  不做 YAML 全量 round-trip —— 那会重排键序、丢注释、改动你其它配置的排版。
* **幂等**：已存在的键默认不覆盖（要覆盖加 --force）。
* **先备份**：写之前复制一份 config.yaml.bak-<时间戳>。
* **可复核**：写完调 `hermes config get quick_commands` 回读打印。

用法：
    python3 scripts/apply-quick-commands.py            # 合并（幂等）
    python3 scripts/apply-quick-commands.py --dry-run  # 只看会加什么
    python3 scripts/apply-quick-commands.py --force    # 已存在的键也用本包的值覆盖
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
SRC = SKILL_DIR / "quick_commands.yaml"
HERMES_DIR = pathlib.Path(os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"))
CFG = HERMES_DIR / "config.yaml"

HEADER_RE = re.compile(r"^quick_commands:\s*$", re.MULTILINE)
ENTRY_RE = re.compile(r"^  (\S[^:]*):")


def parse_entries(text: str) -> "list[tuple[str, str]]":
    """把 quick_commands.yaml 拆成有序的 (键, 该键的完整 YAML 片段)。"""
    lines = text.splitlines()
    entries: "list[tuple[str, str]]" = []
    cur_key = None
    cur_buf: "list[str]" = []
    for ln in lines:
        m = ENTRY_RE.match(ln)
        if m:
            if cur_key is not None:
                entries.append((cur_key, "\n".join(cur_buf).rstrip()))
            cur_key = m.group(1)
            cur_buf = [ln]
        elif cur_key is not None:
            cur_buf.append(ln)
    if cur_key is not None:
        entries.append((cur_key, "\n".join(cur_buf).rstrip()))
    return entries


def block_bounds(lines: "list[str]", start: int) -> int:
    """给定 `quick_commands:` 所在行号，返回块结束行号（不含）。

    块的组成：其后所有「空行 / 缩进行 / 顶格注释行」；遇到第一个顶格非注释行即结束。
    """
    i = start + 1
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "" or ln[:1] in (" ", "\t") or ln.lstrip().startswith("#"):
            i += 1
            continue
        break
    return i


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not SRC.is_file():
        print("✗ 找不到 quick_commands.yaml（请从技能包根目录运行）")
        return 1
    if not CFG.is_file():
        print("✗ 找不到 %s —— 设 HERMES_HOME 指向你的 Hermes 目录" % CFG)
        return 1

    entries = parse_entries(SRC.read_text(encoding="utf-8"))
    if not entries:
        print("✗ quick_commands.yaml 里没解析出任何条目")
        return 1

    raw = CFG.read_text(encoding="utf-8")
    had_trailing_nl = raw.endswith("\n")
    lines = raw.splitlines()

    m = HEADER_RE.search(raw)
    if m is None:
        # 没有这一块：整块追加到文件末尾
        add = entries
        new_lines = lines + ["", "quick_commands:"] + [e[1] for e in add]
        existing = set()
    else:
        start = raw[: m.start()].count("\n")
        end = block_bounds(lines, start)
        block = lines[start + 1 : end]
        existing = {mm.group(1) for mm in (ENTRY_RE.match(x) for x in block) if mm}
        add = [(k, t) for (k, t) in entries if args.force or k not in existing]
        new_lines = lines[:end] + [t for _k, t in add] + lines[end:]

    skipped = [k for k, _ in entries if k in existing and not args.force]
    print("== quick_commands 合并 ==")
    print("  目标文件 : %s" % CFG)
    print("  本包条目 : %d" % len(entries))
    print("  已存在跳过: %d %s" % (len(skipped), ("（" + "、".join(skipped[:12]) + ("…" if len(skipped) > 12 else "") + "）") if skipped else ""))
    print("  本次新增 : %d %s" % (len(add), ("（" + "、".join(k for k, _ in add[:12]) + ("…" if len(add) > 12 else "") + "）") if add else ""))

    if not add and not args.force:
        print("  → 无需改动（幂等）")
        return 0
    if args.dry_run:
        print("  --dry-run：未写入。将要新增的片段：")
        for _k, t in add:
            print("  " + t.replace("\n", "\n  "))
        return 0

    bak = CFG.with_name("config.yaml.bak-%s" % time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(CFG, bak)
    out = "\n".join(new_lines) + ("\n" if had_trailing_nl else "")
    CFG.write_text(out, encoding="utf-8")
    print("  备份     : %s" % bak)
    print("  已写入   : %s" % CFG)

    if shutil.which("hermes"):
        chk = subprocess.run(["hermes", "config", "get", "quick_commands"],
                             capture_output=True, text=True)
        n = len(re.findall(r"^\S[^:]*:$", chk.stdout, re.MULTILINE))
        if chk.returncode == 0 and n:
            print("  回读复核 : hermes config get quick_commands → %d 条 ✓" % n)
        else:
            print("  ! 回读复核异常（rc=%s）：%s" % (chk.returncode, (chk.stderr or chk.stdout).strip()[:200]))
            print("    配置已备份，可手工比对：diff %s %s" % (bak, CFG))
            return 1
    else:
        print("  ! PATH 里没有 hermes，跳过回读复核")
    return 0


if __name__ == "__main__":
    sys.exit(main())
