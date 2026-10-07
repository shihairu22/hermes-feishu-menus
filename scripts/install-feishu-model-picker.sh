#!/usr/bin/env bash
# 一键安装「飞书模型点选器」插件（Hermes 本地插件）
# 用法：在本技能目录里运行  bash scripts/install-feishu-model-picker.sh
#
# 注：与技能包原版相比只多了一处 —— 支持 HM_NO_RELOAD=1 跳过网关重载，
#     便于 scripts/install.sh 把两个插件装完后统一重载一次。
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ASSETS="$SKILL_DIR/assets/feishu-model-picker"
HERMES_DIR="${HERMES_HOME:-$HOME/.hermes}"
DST="$HERMES_DIR/plugins/feishu-model-picker"

for f in __init__.py keeper.py plugin.yaml; do
  [ -f "$ASSETS/$f" ] || { echo "缺少 assets/feishu-model-picker/$f（请从技能包运行）"; exit 1; }
done

# SHA256SUMS 自校验：防止分发途中损坏 / 半拷贝
if [ -f "$ASSETS/SHA256SUMS" ]; then
  (cd "$ASSETS" && sha256sum -c SHA256SUMS >/dev/null) \
    || { echo "✗ assets 校验失败（SHA256SUMS 不匹配）—— 请勿安装，先核对技能包完整性"; exit 1; }
  echo "✓ assets SHA256SUMS 校验通过"
else
  echo "! 缺少 assets/feishu-model-picker/SHA256SUMS（无法校验完整性，继续）"
fi

mkdir -p "$DST"
cp -f "$ASSETS/__init__.py" "$ASSETS/keeper.py" "$ASSETS/plugin.yaml" "$DST/"
echo "✓ 插件已复制到 $DST（3 个文件：__init__.py + keeper.py + plugin.yaml）"

if command -v hermes >/dev/null 2>&1; then
  hermes plugins enable feishu-model-picker || echo "! 启用失败，请手动运行: hermes plugins enable feishu-model-picker"
else
  echo "! 未找到 hermes 命令：请确认 Hermes 在 PATH，或手动把 feishu-model-picker 加入 config.yaml 的 plugins.enabled"
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
echo "  journalctl -u hermes-gateway --since '-2 min' | grep FeishuModelPicker   # 应有三行"
echo "  然后到飞书里发 /model 测试点选"
