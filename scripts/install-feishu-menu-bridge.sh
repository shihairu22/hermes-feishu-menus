#!/usr/bin/env bash
# 一键安装「飞书菜单桥」插件（Hermes 本地插件）
# 用法：在本技能目录里运行  bash scripts/install-feishu-menu-bridge.sh
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ASSETS="$SKILL_DIR/assets/feishu-menu-bridge"
HERMES_DIR="${HERMES_HOME:-$HOME/.hermes}"
DST="$HERMES_DIR/plugins/feishu-menu-bridge"

for f in __init__.py keeper.py plugin.yaml skill_zh.json; do
  [ -f "$ASSETS/$f" ] || { echo "缺少 assets/feishu-menu-bridge/$f（请从技能包运行）"; exit 1; }
done

# SHA256SUMS 自校验：防止分发途中损坏 / 半拷贝
if [ -f "$ASSETS/SHA256SUMS" ]; then
  (cd "$ASSETS" && sha256sum -c SHA256SUMS >/dev/null) \
    || { echo "✗ assets 校验失败（SHA256SUMS 不匹配）—— 请勿安装，先核对技能包完整性"; exit 1; }
  echo "✓ assets SHA256SUMS 校验通过"
else
  echo "! 缺少 assets/feishu-menu-bridge/SHA256SUMS（无法校验完整性，继续）"
fi

mkdir -p "$DST"

# 覆盖前先比对：不存在→复制；与源相同→跳过；不同→先把旧文件备份成
# <目标文件>.bak-<YYYYmmdd_HHMMSS> 再覆盖。用 `if cmp -s ...` 这种安全写法，
# 避免 set -e 因 cmp 的非零返回码意外退出。
copy_asset() {
  local name="$1" src="$ASSETS/$1" dst="$DST/$1"
  if [ ! -e "$dst" ]; then
    cp -p "$src" "$dst"
    echo "  + $name（新建）"
  elif cmp -s "$src" "$dst"; then
    echo "  = $name 已是同一份，跳过"
  else
    local bak
    bak="$dst.bak-$(date +%Y%m%d_%H%M%S)"
    cp -p "$dst" "$bak"
    cp -p "$src" "$dst"
    echo "  ! $name 与包内不同：旧文件已备份到 $bak，并已覆盖"
  fi
}

for f in __init__.py keeper.py plugin.yaml skill_zh.json; do
  copy_asset "$f"
done
echo "✓ 插件已复制到 $DST（4 个文件：__init__.py + keeper.py + plugin.yaml + skill_zh.json）"

if command -v hermes >/dev/null 2>&1; then
  hermes plugins enable feishu-menu-bridge || echo "! 启用失败，请手动运行: hermes plugins enable feishu-menu-bridge"
else
  echo "! 未找到 hermes 命令：请确认 Hermes 在 PATH，或手动把 feishu-menu-bridge 加入 config.yaml 的 plugins.enabled"
fi

if [ -n "${HM_NO_RELOAD:-}" ]; then
  echo "· 已跳过网关重载（HM_NO_RELOAD 已设置，由上层统一重载）"
elif systemctl is-active --quiet hermes-gateway.service 2>/dev/null; then
  systemctl reload hermes-gateway.service && echo "✓ 已优雅重载网关（等 20~40 秒后验证）"
else
  echo "! 未检测到 hermes-gateway 服务：请按你的部署方式重载网关"
fi

echo
echo "验证："
echo "  journalctl -u hermes-gateway --since '-2 min' | grep FeishuMenuBridge   # 应有多行"
echo "  或看 ~/.hermes/logs/agent.log 里的 'hook installed ... (vN)' 行"
echo "  然后到飞书里点悬浮菜单的「📊面板」测试"
