#!/usr/bin/env python3
"""把本机技能的说明翻译成中文，写进 $HERMES_HOME/state/skill_zh_auto.json。

为什么需要它
------------
技能卡优先显示中文说明：先查插件自带的静态表 ``skill_zh.json``（只覆盖通用技能），
再查自动翻译缓存。**你自己装的技能不在静态表里**，卡片只能显示 SKILL.md 原文
（可能是英文）。这个脚本用**你自己配置的模型**把这些补齐 —— 跑一次，之后一直复用。

用法
----
    python3 skill_zh_autofill.py              # 译全部缺中文的
    python3 skill_zh_autofill.py --limit 20   # 只译 20 条（先试水）
    python3 skill_zh_autofill.py --dry-run    # 只列要译哪些，不调用模型
    python3 skill_zh_autofill.py --stats      # 只看还剩多少条没译

说明
----
* **幂等**：静态表与缓存里已有的不再送模型；失败不会破坏已有缓存。
* **成本**：约 250 token/条（走你自己的中转额度）。95 个技能大约 2.5 万 token。
* 不跑这个脚本也行 —— 技能卡每次打开会自动补译 20 条，几轮下来也会补齐。
* 想强制重译某条：把它从 ``state/skill_zh_auto.json`` 里删掉再跑一次。
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path


def _home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))


def _load_plugin():
    """加载已安装的 feishu-menu-bridge（复用它的扫描/翻译/写盘逻辑，避免两处实现漂移）。"""
    p = _home() / "plugins" / "feishu-menu-bridge" / "__init__.py"
    if not p.exists():
        sys.exit("找不到插件：%s\n请先运行 install.sh 安装 feishu-menu-bridge。" % p)
    spec = importlib.util.spec_from_file_location("fmb_skill_zh_autofill", p)
    if spec is None or spec.loader is None:
        sys.exit("无法加载插件模块：%s" % p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fmb_skill_zh_autofill"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description="把本机技能说明翻译成中文（写入技能卡的中文缓存）")
    ap.add_argument("--limit", type=int, default=None, help="最多译多少条（默认全部）")
    ap.add_argument("--batch", type=int, default=20, help="每次请求送模型多少条（默认 20）")
    ap.add_argument("--dry-run", action="store_true", help="只列出要译哪些，不调用模型")
    ap.add_argument("--stats", action="store_true", help="只报告还剩多少条没中文化")
    args = ap.parse_args()

    m = _load_plugin()
    base, key, model = m._llm_endpoint()
    cache = _home() / "state" / "skill_zh_auto.json"

    if args.stats:
        print("技能总数   : %d" % len(m._skills_flat()))
        print("待中文化   : %d 条" % m._skill_zh_missing())
        print("缓存文件   : %s%s" % (cache, "" if cache.exists() else "（还不存在）"))
        print("模型接入点 : %s" % ("已就绪（%s）" % model if key else "未配置（缺 base_url / 密钥）"))
        return 0

    if not key and not args.dry_run:
        print("模型接入点未就绪：config.yaml 缺 base_url，或环境变量/`%s` 里没有 HERMES_RELAY_API_KEY。"
              % (_home() / ".env"), file=sys.stderr)
        print("技能卡会继续显示 SKILL.md 原文，不影响其他功能。", file=sys.stderr)
        return 2

    if args.dry_run:
        known, auto = m._skill_zh_map(), m._skill_zh_auto_map()
        todo = []
        for r in m._skills_flat():
            if r["name"] in known or r["name"] in auto:
                continue
            d = m._skill_desc(r["path"])
            if not d or m._is_chinese(d):
                continue
            todo.append((r["name"], d))
        if args.limit:
            todo = todo[:args.limit]
        print("需要翻译 %d 条：" % len(todo))
        for n, d in todo:
            print("  %-30s %s" % (n, d[:70]))
        return 0

    print("模型：%s" % model)
    print("缓存：%s" % cache)
    print("开始翻译（每批 %d 条）…" % args.batch)
    stats = m.skill_zh_autofill(limit=args.limit, batch=args.batch)
    print("候选 %d 条 → 成功 %d、失败 %d" % (stats["candidates"], stats["translated"], stats["failed"]))
    print("还剩 %d 条没中文化。" % m._skill_zh_missing())
    if stats["failed"]:
        print("失败的会保留原文；稍后重跑本脚本或打开技能卡即可重试。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
