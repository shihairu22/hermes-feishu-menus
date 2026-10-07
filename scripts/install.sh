#!/usr/bin/env bash
# 一键本地安装：两个插件 + 中文快捷命令
# 用法：在本技能目录里运行  bash scripts/install.sh
#
# 这一步**不需要扫码、不需要人工**。扫码只发生在下一步（铺控制台悬浮菜单）。
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_DIR="${HERMES_HOME:-$HOME/.hermes}"

echo "== Hermes 飞书菜单包 · 本地安装 =="
echo "  技能目录  : $SKILL_DIR"
echo "  Hermes 目录: $HERMES_DIR"
echo

# ── 体检 ─────────────────────────────────────────────────────────
miss=0
command -v python3 >/dev/null 2>&1 || { echo "✗ 缺少 python3（脚本只用标准库，装个 3.11+ 即可）"; miss=1; }
if [ ! -d "$HERMES_DIR" ]; then
  echo "✗ 未找到 $HERMES_DIR —— Hermes 装好了吗？装在别处就设 HERMES_HOME 再跑"
  miss=1
fi
command -v hermes >/dev/null 2>&1 \
  || echo "! PATH 里没有 hermes：插件文件照样会拷，但需要你自己启用（hermes plugins enable ...）"
[ "$miss" = 0 ] || { echo; echo "体检未通过，已中止。"; exit 1; }
echo "✓ 体检通过"
echo

export HM_NO_RELOAD=1     # 两个子脚本各自不重载，最后统一重载一次

echo "── [1/3] 安装插件 feishu-menu-bridge（悬浮菜单 → 卡片菜单的桥）──"
bash "$SKILL_DIR/scripts/install-feishu-menu-bridge.sh"
echo
echo "── [2/3] 安装插件 feishu-model-picker（/model 点选器）──"
bash "$SKILL_DIR/scripts/install-feishu-model-picker.sh"
echo
echo "── [3/3] 写入中文快捷命令 quick_commands ──"
python3 "$SKILL_DIR/scripts/apply-quick-commands.py"
echo

if systemctl is-active --quiet hermes-gateway.service 2>/dev/null; then
  systemctl reload hermes-gateway.service && echo "✓ 已优雅重载网关（等 20~40 秒后验证）"
else
  echo "! 未检测到 hermes-gateway 服务：请按你的部署方式重启/重载网关"
fi

echo
echo "== 本地部分完成 =="
echo "接下来："
echo "  1) 重启网关让插件真正加载：systemctl restart hermes-gateway（或你的部署方式）"
echo "  2) 到飞书里给机器人发 /model —— 出交互卡片即点选器已生效"
echo "  3) 铺控制台悬浮菜单（需要扫码一次）：见 SETUP.md「第二步」"
