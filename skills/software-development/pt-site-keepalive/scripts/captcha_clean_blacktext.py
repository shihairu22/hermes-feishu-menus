#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""黑字验证码净化器（HDU / PTHOME 类：纯黑文字 + 彩色噪点，可能带黑色边框）。

用法：/usr/bin/python3 captcha_clean_blacktext.py <png> [hdu|pthome]
  hdu（默认）—— 文字纯黑：mask = (R<100)&(G<100)&(B<100)
  pthome     —— 浅灰底 + 纯黑文字：mask = sum(RGB)<200

步骤：
  ① 按模式做黑白阈值分割；
  ② 剔除「触碰图像边缘」的连通域 —— 同时去掉 PTHOME 那种四周黑边框
     （边框会把列投影连成一整段，导致逐字切分失败）；
  ③ 逐字切分、逐字打印点阵（列间隙切分）；
  ④ 输出 6× NEAREST 放大黑字白底图 <同名>_big.png（给视觉模型或用户代读）。

注意：HDU 的验证码存服务端 memcached、提交窗口以秒计 —— 本脚本要跟
「轮询等图出现」合并进同一次调用跑完，紧接着写答案，不要在窗口内加复核回合。
"""
import re
import sys
from collections import deque

import numpy as np
from PIL import Image

path = sys.argv[1]
mode = (sys.argv[2] if len(sys.argv) > 2 else 'hdu').lower()
MIN_SIZE = 12 if mode == 'hdu' else 3

a = np.array(Image.open(path).convert('RGB')).astype(int)
H, W, _ = a.shape
r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
if mode == 'pthome':
    mask = a.sum(axis=2) < 200
else:
    mask = (r < 100) & (g < 100) & (b < 100)
print('mode=%s size %dx%d  black=%d' % (mode, W, H, int(mask.sum())))

lab = np.zeros((H, W), dtype=int)
keep = np.zeros_like(mask)
comps = 0
for y0 in range(H):
    for x0 in range(W):
        if mask[y0, x0] and lab[y0, x0] == 0:
            comps += 1
            q = deque([(y0, x0)]); lab[y0, x0] = comps; pix = []
            while q:
                y, x = q.popleft(); pix.append((y, x))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and lab[yy, xx] == 0:
                            lab[yy, xx] = comps; q.append((yy, xx))
            ys = [p[0] for p in pix]; xs = [p[1] for p in pix]
            if min(xs) == 0 or max(xs) == W - 1 or min(ys) == 0 or max(ys) == H - 1:
                continue            # 贴边 = 边框/干扰，丢弃
            if len(pix) < MIN_SIZE:
                continue            # 过小 = 噪点碎块
            for y, x in pix:
                keep[y, x] = True

ys = np.where(keep.any(axis=1))[0]
xs = np.where(keep.any(axis=0))[0]
print('kept=%d' % keep.sum())
if len(xs):
    sub = keep[:, xs.min():xs.max() + 1]
    cols = sub.any(axis=0)
    segs, start = [], None
    for x in range(sub.shape[1]):
        if cols[x] and start is None:
            start = x
        elif not cols[x] and start is not None:
            segs.append((start, x - 1)); start = None
    if start is not None:
        segs.append((start, sub.shape[1] - 1))
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] <= 2:
            merged[-1] = (merged[-1][0], s[1])
        else:
            merged.append(list(s))
    print('segs=%d' % len(merged))
    for i, (sx0, sx1) in enumerate(merged):
        piece = sub[:, sx0:sx1 + 1]
        rows = np.where(piece.any(axis=1))[0]
        p = piece[rows.min():rows.max() + 1, :]
        print('--- char %d (%dx%d) ---' % (i + 1, p.shape[1], p.shape[0]))
        for y in range(p.shape[0]):
            print(''.join('#' if p[y, x] else '.' for x in range(p.shape[1])))
    im = Image.fromarray(np.where(sub, 0, 255).astype(np.uint8))
    big = im.resize((im.width * 6, im.height * 6), Image.NEAREST)
    big_path = re.sub(r'\.png$', '_big.png', path)
    big.save(big_path)
    print('saved %s (%dx%d)' % (big_path, big.width, big.height))
else:
    print('no pixels kept — 检查模式是否选对（hdu/pthome）')
