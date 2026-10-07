#!/usr/bin/env bash
# assets ⇄ live 一致性对账（两个插件都查）；exit 1 = 漂移（打印 assets=/live= 两侧哈希）
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_DIR="${HERMES_HOME:-$HOME/.hermes}"
rc=0

check_plugin() {  # $1=插件名  其余=文件名
  local name="$1"; shift
  local A="$SKILL_DIR/assets/$name"
  local L="$HERMES_DIR/plugins/$name"
  echo "── $name ──"
  if [ ! -d "$L" ]; then echo "  MISSING live: $L"; rc=1; return; fi
  local f ha hl
  for f in "$@"; do
    if [ ! -f "$A/$f" ]; then echo "  MISSING assets/$name/$f"; rc=1; continue; fi
    ha=$(sha256sum "$A/$f" | cut -d' ' -f1)
    hl=$(sha256sum "$L/$f" | cut -d' ' -f1)
    if [[ "$ha" == "$hl" ]]; then echo "  OK    $f  $ha"
    else echo "  DRIFT $f  assets=$ha  live=$hl"; rc=1; fi
  done
  # SHA256SUMS 自校验（防分发途中损坏/半拷贝）
  if [[ -f "$A/SHA256SUMS" ]]; then
    (cd "$A" && sha256sum -c SHA256SUMS >/dev/null 2>&1) || { echo "  SHA256SUMS MISMATCH"; rc=1; }
  else
    echo "  MISSING SHA256SUMS"; rc=1
  fi
}

check_plugin feishu-model-picker __init__.py keeper.py plugin.yaml
check_plugin feishu-menu-bridge  __init__.py keeper.py plugin.yaml skill_zh.json

# 语义护栏（model-picker）：assets 必须含 PATCH 修复、不得再出现 PUT 老路
A="$SKILL_DIR/assets/feishu-model-picker"
grep -q 'PatchMessageRequest' "$A/__init__.py" || { echo "MISSING PATCH fix in assets"; rc=1; }
if grep -q '_build_update_message_body' "$A/__init__.py"; then echo "STALE PUT path in assets"; rc=1; fi

exit $rc
