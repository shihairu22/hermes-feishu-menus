#!/bin/bash
set -u
cd $HOME/.hermes/cache/scratch
echo "=== 开始扫描（awg 协议 + 隧道内耐久性检测）==="
date
timeout 560 ./warpscout scan -proto awg -tun-ping -jt 16 > scan_new.out 2>&1
echo "warpscout exit=$?"
date
echo ""
echo "=== 扫描结果（去掉进度行）==="
grep -vE "^\s+[0-9]+/[0-9]+$" scan_new.out | tail -60
