#!/usr/bin/env bash
# assets 一致性对账：assets 必须 == 生成器(live) 的输出（单一来源 = live）。
#
# 为什么不再直接比对 assets 与 live：assets 是**产物**（去敏 + 分发覆盖），
# 与 live 本来就不该逐字节相同。旧判据「assets 必须等于 live」在新架构下会永久
# 报 DRIFT —— 是判据错了，不是文件错了。
#
# exit 0 = 一致；exit 1 = 有人手改了 assets，或改了 live 没重生成。
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_DIR="${HERMES_HOME:-$HOME/.hermes}"
LIVE="${FMB_LIVE_DIR:-$HERMES_DIR/plugins}"

rc=0

echo "── 生成器对账（assets ← live）──"
if [ ! -d "$LIVE" ]; then
  echo "  跳过：找不到 live 目录 $LIVE（这项核对只在作者本机做）"
else
  python3 "$SKILL_DIR/scripts/sanitize-live-to-assets.py" --check \
    --live "$LIVE" --repo "$SKILL_DIR" || rc=1
fi

echo
echo "── 两层校验和自检 ──"
for d in feishu-menu-bridge feishu-model-picker; do
  A="$SKILL_DIR/assets/$d"
  if [ -f "$A/SHA256SUMS" ]; then
    (cd "$A" && sha256sum -c SHA256SUMS >/dev/null 2>&1) \
      && echo "  OK    assets/$d/SHA256SUMS" \
      || { echo "  FAIL  assets/$d/SHA256SUMS（内容与哈希不符，需重算）"; rc=1; }
  else
    echo "  MISSING assets/$d/SHA256SUMS"; rc=1
  fi
done
if [ -f "$SKILL_DIR/MANIFEST.sha256" ]; then
  (cd "$SKILL_DIR" && sha256sum -c MANIFEST.sha256 >/dev/null 2>&1) \
    && echo "  OK    MANIFEST.sha256" \
    || { echo "  FAIL  MANIFEST.sha256（重算顺序：先内层 SHA256SUMS，再外层）"; rc=1; }
else
  echo "  MISSING MANIFEST.sha256"; rc=1
fi

echo
echo "── 语义护栏 ──"
A="$SKILL_DIR/assets/feishu-model-picker"
grep -q 'PatchMessageRequest' "$A/__init__.py" || { echo "  FAIL  缺 PATCH 修复"; rc=1; }
if grep -q '_build_update_message_body' "$A/__init__.py"; then
  echo "  FAIL  仍是老 PUT 路径"; rc=1
fi
[ "$rc" = 0 ] && echo "  OK"

exit $rc
