#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本机 live 插件生成成可公开分发的 assets（单一来源 = live）。

用法：
  python3 scripts/sanitize-live-to-assets.py --check   # 只比对，不改（CI / 发版前用）
  python3 scripts/sanitize-live-to-assets.py --write    # 写入 assets/
  ... --live <目录> --repo <目录>                       # 覆盖路径（测试用）

设计原则
--------
1. **规则有名字、分两类**，绝不把「分发决策」混进去敏表：
     sanitize:  纯个人/本机标识 → 中性值（行为不变）
     overlay:   有意的分发版功能差异（**不是去敏**，必须逐条可审查）
2. **唯一锚点**：每条规则在源文件里必须恰好命中 1 次，否则抛异常、**一个字节都不写**。
3. **幂等**：重复跑结果一致（用探针判据，见 PROBE）。
4. 规则跑完后自动跑泄漏扫描，命中即失败。

live 是唯一真源；assets 是产物。改完 live 跑一条命令即可，不再人肉对齐两份。
"""
import argparse
import json
import re
import sys
from pathlib import Path

# ── 分发版只保留这些通用技能的中文描述（其余一律丢弃并打印清单）──────
# 这是「白名单」而非黑名单：新加的私人技能默认不外发，想外发就往这里加一条。
SKILL_ZH_ALLOW = [
    "codebase-inspection", "credential-hygiene", "dogfood", "github",
    "hermes-agent-skill-authoring", "inspecting-hermes-desktop-dom",
    "model-channel-validation", "node-inspect-debugger", "python-debugpy",
    "requesting-code-review", "safe-file-reorganization",
    "secure-browser-credential-flows", "simplify-code", "spike",
    "system-architecture-audit", "systematic-debugging", "test-driven-development",
    "airtable", "box", "document-to-action-items", "docx", "google-workspace", "maps",
    "meeting-action-items", "notion", "pdf", "powerpoint", "product-price-monitor",
    "weekly-review-planning", "xlsx",
    "claude-code", "codex", "computer-use", "hermes-agent", "opencode",
    "architecture-diagram", "ascii-video", "claude-design", "design-md", "humanizer",
    "manim-video", "p5js", "popular-web-designs", "songwriting-and-ai-music",
    "arxiv", "competitor-news-monitor", "grounded-citations", "llm-wiki",
    "apple-notes", "apple-reminders", "findmy", "imessage",
    "messaging-platform-operations", "xurl", "sdlc-review",
    "gif-search", "songsee", "youtube-content",
    "email-inbox-triage", "himalaya",
    "blocked-page-recovery", "browser-automation", "obsidian", "mcp-server-ops",
    "baoyu-infographic", "feishu-menus",
]

# ── 规则表 ──────────────────────────────────────────────────────────
# (插件名, 文件名, 规则名, old, new)
RULES = [
    # ===== feishu-menu-bridge/__init__.py =====
    ("feishu-menu-bridge", "__init__.py", "sanitize:persona-title",
     '"📊 艾莉娅 · 控制台"', '"📊 控制台"'),

    ("feishu-menu-bridge", "__init__.py", "sanitize:persona-note",
     "这里切的是内置人格预设；艾莉娅的人设来自 SOUL.md，不受影响。",
     "这里切的是内置人格预设；自定义人设（SOUL.md），不受影响。"),

    ("feishu-menu-bridge", "__init__.py", "sanitize:pt-docstring",
     '"""最近一轮 PT 签到记录（/root/.pt-sessions/state/checkin_runs.json）。"""',
     '"""最近一轮 PT 签到记录（$PT_SESSIONS_DIR/state/checkin_runs.json；默认 ~/.pt-sessions）。"""'),

    ("feishu-menu-bridge", "__init__.py", "sanitize:pt-dir",
     '_PT_DIR = os.environ.get("PT_SESSIONS_DIR") or "/root/.pt-sessions"',
     '_PT_DIR = os.environ.get("PT_SESSIONS_DIR") or os.path.expanduser("~/.pt-sessions")'),

    ("feishu-menu-bridge", "__init__.py", "sanitize:home-dir",
     '_HOME_DIR = os.environ.get("HERMES_HOME") or "/root/.hermes"',
     '_HOME_DIR = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")'),

    ("feishu-menu-bridge", "__init__.py", "sanitize:df-comment",
     "# 2026-10-04 审计修复：/root 不是独立挂载点时 df 会把同一分区打两遍（每个参数一行）——按设备去重。",
     "# 2026-10-04 审计修复：$HOME 不是独立挂载点时 df 会把同一分区打两遍（每个参数一行）——按设备去重。"),

    ("feishu-menu-bridge", "__init__.py", "sanitize:df-cmd",
     """_run("df -h / /root 2>/dev/null | tail -n +2 | awk '!seen[$1]++'")""",
     """_run("df -h / $HOME 2>/dev/null | tail -n +2 | awk '!seen[$1]++'")"""),

    ("feishu-menu-bridge", "__init__.py", "sanitize:cat-emoji",
     '"social-media": "💬", "software-development": "💻", "synology-nas-docker": "🗄",',
     '"social-media": "💬", "software-development": "💻",'),

    ("feishu-menu-bridge", "__init__.py", "sanitize:cat-zh",
     '"synology-nas-docker": "NAS", "web": "网页",',
     '"web": "网页",'),

    # ---- overlay：分发版有意差异（非去敏）----
    # 2026-10-07：PT 卡的三条 overlay（pt-note / pt-buttons / pt-docstring）已**全部撤掉**。
    # 原因：签到按钮改成**代码内能力门控**（live 的 `_pt_ready()`：装了 pt-site-keepalive
    # 技能才渲染、才可点）。没装技能的机器上按钮自然不出现，备注也自动换成数据来源说明——
    # 于是 live 与分发版**代码完全一致**，不再需要「分发版专用」的差异规则。
    # 教训：能用代码自适应的差异，不要藏进 overlay 表。

    # ===== feishu-menu-bridge/plugin.yaml =====
    ("feishu-menu-bridge", "plugin.yaml", "sanitize:author",
     'author: "Elia"', 'author: "Hermes Agent"'),
]

# 幂等探针：new 里唯一标识「已应用」的子串。
# 默认用 new；若 new **包含** old（插入型规则），必须另给探针，
# 否则复跑时 old 仍在 → 判据永远不成立 → 重复插入（实测踩过两次）。
# 删除型规则（new 为空）无法用「new 在不在」判断，改用「old 是否已消失」。
PROBE = {}

# 会分发出去的文件（未列出的 live 文件一律不打包）
PLUGINS = {
    "feishu-menu-bridge": ["__init__.py", "keeper.py", "plugin.yaml", "skill_zh.json"],
    "feishu-model-picker": ["__init__.py", "keeper.py", "plugin.yaml"],
}


def apply_rule(src: str, tag: str, name: str, old: str, new: str) -> str:
    """幂等应用一条规则。

    「已应用」的判据必须按规则形态选，否则会静默跳过或重复插入（两种都实测踩过）：

      · 删除型（new == ""）      → old 已消失
      · 插入型（old 是 new 的子串）→ 必须显式给 PROBE（old 仍在，不能用 old 判断）
      · 替换 / 截尾型（其余）     → new 已出现 **且** old 已消失
        —— 只看「new 已出现」是错的：若 new 恰是 old 的前缀（截尾型），
           改之前 new 就已经命中，规则会被静默跳过（实测踩过）。
    """
    if new == "":
        if old not in src:
            return src                       # 已删除
    elif old in new:
        probe = PROBE.get(name)
        if not probe:
            raise AssertionError(f"[{tag}/{name}] 插入型规则必须显式给 PROBE")
        if probe in src:
            return src                       # 已插入
    else:
        if new in src and old not in src:
            return src                       # 已替换 / 已截尾
    n = src.count(old)
    if n != 1:
        raise AssertionError(f"[{tag}/{name}] 锚点命中 {n} 次（要求恰好 1 次）")
    return src.replace(old, new)


def render_skill_zh(raw: str) -> str:
    """skill_zh.json：只保留白名单键，末尾补换行（与已发布 assets 逐字节一致）。"""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise AssertionError("skill_zh.json 顶层不是对象")
    dropped = [k for k in data if k not in SKILL_ZH_ALLOW]
    kept = {k: v for k, v in data.items() if k in SKILL_ZH_ALLOW}
    if dropped:
        print(f"    · 丢弃 {len(dropped)} 条私人技能描述：{', '.join(dropped[:6])}"
              + (" …" if len(dropped) > 6 else ""))
    return json.dumps(kept, ensure_ascii=False, indent=1) + "\n"


def generate(live_root: Path, out_root: Path, write: bool) -> int:
    changed, mismatched = [], []
    for plugin, files in PLUGINS.items():
        for fn in files:
            src_path = live_root / plugin / fn
            if not src_path.exists():
                print(f"  !! 缺 live 文件：{src_path}")
                return 2
            src = src_path.read_text(encoding="utf-8")

            if fn == "skill_zh.json":
                out = render_skill_zh(src)
            else:
                for p, f, name, old, new in RULES:
                    if p == plugin and f == fn:
                        src = apply_rule(src, plugin, name, old, new)
                out = src

            dst_path = out_root / plugin / fn
            if write:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                if not dst_path.exists() or dst_path.read_text(encoding="utf-8") != out:
                    dst_path.write_text(out, encoding="utf-8")
                    changed.append(f"{plugin}/{fn}")
            else:
                cur = dst_path.read_text(encoding="utf-8") if dst_path.exists() else None
                if cur != out:
                    mismatched.append(f"{plugin}/{fn}")
    if write:
        print(f"已写入 {len(changed)} 个文件" + (f"：{', '.join(changed)}" if changed else "（内容无变化）"))
    else:
        if mismatched:
            print("✗ 与 assets 不一致（说明有人手改了 assets，或规则不全）：")
            for m in mismatched:
                print(f"    {m}")
            return 1
        print("✓ 生成结果与 assets 逐字节一致")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只比对，不写")
    ap.add_argument("--write", action="store_true", help="写入 assets/")
    ap.add_argument("--live", default=str(Path.home() / ".hermes" / "plugins"))
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    a = ap.parse_args()
    if not (a.check or a.write):
        ap.error("请指定 --check 或 --write")
    out = Path(a.repo) / "assets"
    if a.write:
        out.mkdir(parents=True, exist_ok=True)
    return generate(Path(a.live), out, a.write)


if __name__ == "__main__":
    raise SystemExit(main())
