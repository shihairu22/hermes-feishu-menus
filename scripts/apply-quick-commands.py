#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 quick_commands.yaml 合并进 Hermes 的 config.yaml。

设计取舍
--------
* **文本级、块内合并**：只改 `quick_commands:` 这一块，文件其余字节原样保留。
  不做 YAML 全量 round-trip —— 那会重排键序、丢注释、改动你其它配置的排版。
* **行尾保留**：按原文件每行自带的行尾（LF / CRLF）逐行写回，不归一整个文件行尾。
* **幂等**：已存在的键默认不覆盖（要覆盖加 --force）。
* **覆盖不重复**：--force 时先删掉同名键的整段旧块再插入新块，保证每个键只出现一次。
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


def strip_nl(s: str) -> str:
    """去掉行尾换行符（\\r\\n / \\n / \\r），只留行内容。"""
    if s.endswith("\r\n"):
        return s[:-2]
    if s.endswith("\n") or s.endswith("\r"):
        return s[:-1]
    return s


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
        ln = strip_nl(lines[i])
        if ln.strip() == "" or ln[:1] in (" ", "\t") or ln.lstrip().startswith("#"):
            i += 1
            continue
        break
    return i


def block_segments(block: "list[str]") -> "list[tuple[str, int, int]]":
    """把块内每一段（一个键行 + 它的续行）标出 [起, 止) 行号。

    键行判定沿用 parse_entries 用的同一个 ENTRY_RE，口径保持一致。
    """
    segs: "list[tuple[str, int, int]]" = []
    cur: "tuple[str, int] | None" = None
    for i, ln in enumerate(block):
        m = ENTRY_RE.match(strip_nl(ln))
        if m:
            if cur is not None:
                segs.append((cur[0], cur[1], i))
            cur = (m.group(1), i)
    if cur is not None:
        segs.append((cur[0], cur[1], len(block)))
    return segs


def render_entry(text: str, nl: str) -> "list[str]":
    """把一条条目片段（内部以 \\n 分隔）渲染成带指定行尾的行列表。"""
    return [p + nl for p in text.split("\n")]


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

    # 用二进制读/写：Path.read_text 默认开 universal newlines，会在读入时就把
    # \r\n 归一成 \n；只有字节级读写才能真正做到「其余行字节不变」。
    raw = CFG.read_bytes().decode("utf-8")
    had_trailing_nl = raw.endswith("\n")
    # keepends：每行连同自己的行尾（\n 或 \r\n）一起取出，写回时原样拼接 ——
    # 这样只改动块内需要改的行，其余行字节不变、也不归一整个文件的行尾。
    lines = raw.splitlines(keepends=True)
    nl_default = "\r\n" if "\r\n" in raw else "\n"

    m = HEADER_RE.search(raw)
    if m is None:
        # 没有这一块：整块追加到文件末尾
        add = entries
        existing = set()
        tail: "list[str]" = []
        if lines and not lines[-1].endswith(("\n", "\r")):
            tail.append(nl_default)          # 末行无行尾时先补一个，避免与新增内容粘连
        tail.append(nl_default)              # 空行
        tail.append("quick_commands:" + nl_default)
        for _k, t in add:
            tail.extend(render_entry(t, nl_default))
        new_lines = lines + tail
    else:
        start = raw[: m.start()].count("\n")
        end = block_bounds(lines, start)
        block = lines[start + 1 : end]
        existing = {mm.group(1) for mm in (ENTRY_RE.match(strip_nl(x)) for x in block) if mm}
        add = [(k, t) for (k, t) in entries if args.force or k not in existing]
        # 新增条目的行尾沿用 `quick_commands:` 头行
        hdr_ending = lines[start][len(strip_nl(lines[start])):]
        entry_nl = hdr_ending if hdr_ending else nl_default
        if args.force:
            # 覆盖：先删掉「本次要覆盖」的同名键的整段旧块，再追加新块，
            # 避免同名键被插两份、写出重复键的 YAML。
            overwrite = {k for k, _ in add}
            drop = set()
            for k, s, e in block_segments(block):
                if k in overwrite:
                    drop.update(range(s, e))
            new_block = [block[i] for i in range(len(block)) if i not in drop]
            for _k, t in add:
                new_block.extend(render_entry(t, entry_nl))
        else:
            new_block = list(block)
            for _k, t in add:
                new_block.extend(render_entry(t, entry_nl))
        new_lines = lines[: start + 1] + new_block + lines[end:]

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

    out = "".join(new_lines)
    # 保持原文件的「末尾是否带换行」状态不变
    if had_trailing_nl:
        if not out.endswith("\n"):
            out += nl_default
    else:
        if out.endswith("\r\n"):
            out = out[:-2]
        elif out.endswith("\n"):
            out = out[:-1]

    bak = CFG.with_name("config.yaml.bak-%s" % time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(CFG, bak)
    CFG.write_bytes(out.encode("utf-8"))
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
