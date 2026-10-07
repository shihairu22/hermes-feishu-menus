#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 menu.json / 版本信息填进控制台 JS 片段，输出可直接粘贴执行的代码。

用法：
    python3 scripts/build-console-snippet.py apply      # 铺菜单片段
    python3 scripts/build-console-snippet.py publish    # 建版本+发布片段
    python3 scripts/build-console-snippet.py publish --changelog "同步悬浮菜单" --version 1.2.3

不填 --version 就自动取历史最大版本 +1。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SKILL_DIR = HERE.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["apply", "publish"])
    ap.add_argument("--version", default="")
    ap.add_argument("--changelog", default="同步悬浮菜单结构")
    args = ap.parse_args()

    if args.which == "apply":
        tpl = (HERE / "console-apply-menu.js").read_text(encoding="utf-8")
        menu = json.loads((SKILL_DIR / "menu.json").read_text(encoding="utf-8"))
        # 控制台接口只吃 {menu:{...}} 里的那三个字段
        payload = {
            "botMenuEnable": menu.get("botMenuEnable", True),
            "botMenuDisplayStrategy": menu.get("botMenuDisplayStrategy", 3),
            "botMenuConfig": menu["botMenuConfig"],
        }
        # 只替换第一次出现（注释里若也出现同名 token，不应被塞进一大坨 JSON）
        out = tpl.replace("__MENU_JSON__", json.dumps(payload, ensure_ascii=False, indent=1), 1)
    else:
        tpl = (HERE / "console-publish.js").read_text(encoding="utf-8")
        out = (tpl.replace("__VERSION__", args.version or "__VERSION__", 1)
                  .replace("__CHANGELOG__", args.changelog.replace("'", "\\'"), 1))

    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
