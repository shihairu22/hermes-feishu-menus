#!/usr/bin/env python3
"""U2 验证码净化器 —— references/u2.md §2「三步净化」的脚本版（含斜线密度过滤）。

流程：
  ① 取非背景像素：背景 RGB(0,153,204)，|Δ|.sum() > 60 → 文字 + 干扰线 + 噪点
  ② 去长横段：同一行连续 >14 像素的段判为干扰线抹掉（字符宽约 12px，不会误伤）
  ③ 连通域过滤：只留 >=25 像素的块；宽度 >20 且密度 <0.2 的细长块判为
     斜线干扰一并剔除（横段规则只挡横线——对角线会幸存并穿越字符）

输出：逐字 ASCII 点阵（自己读）+ /tmp/u2_captcha_big.png（7× 放大黑字白底，
直接发用户代读最稳）。

用法：/usr/bin/python3 u2_captcha_clean.py /tmp/u2_captcha.png
解释器用系统 python3（PIL/numpy 在 /usr/bin/python3，camoufox venv 没有）。
"""
import sys
from collections import deque

import numpy as np
from PIL import Image

path = sys.argv[1]
a = np.array(Image.open(path).convert('RGB')).astype(int)
H, W, _ = a.shape
bg = np.array([0, 153, 204])
mask = np.abs(a - bg[None, None, :]).sum(axis=2) > 60

# ② 去长横段
for y in range(H):
    x = 0
    while x < W:
        if mask[y, x]:
            x2 = x
            while x2 < W and mask[y, x2]:
                x2 += 1
            if x2 - x > 14:
                mask[y, x:x2] = False
            x = x2
        else:
            x += 1

# ③ 连通域过滤（>=25 像素 + 斜线密度过滤）
lab = np.zeros((H, W), dtype=int)
keep = np.zeros_like(mask)
cur = 0
for y0 in range(H):
    for x0 in range(W):
        if mask[y0, x0] and lab[y0, x0] == 0:
            cur += 1
            q = deque([(y0, x0)])
            lab[y0, x0] = cur
            pix = []
            while q:
                y, x = q.popleft()
                pix.append((y, x))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and lab[yy, xx] == 0:
                            lab[yy, xx] = cur
                            q.append((yy, xx))
            if len(pix) < 25:
                continue
            ys_c = [p[0] for p in pix]
            xs_c = [p[1] for p in pix]
            w = max(xs_c) - min(xs_c) + 1
            h = max(ys_c) - min(ys_c) + 1
            density = len(pix) / float(w * h)
            if w > 20 and density < 0.2:
                print('  [剔除斜线] w=%d h=%d area=%d density=%.2f' % (w, h, len(pix), density))
                continue
            for y, x in pix:
                keep[y, x] = True

# 输出：逐字点阵 + 7× 放大图
ys = np.where(keep.any(axis=1))[0]
xs = np.where(keep.any(axis=0))[0]
print('kept=%d' % keep.sum())
if len(xs):
    y0, y1 = ys.min(), ys.max()
    sub = keep[y0:y1 + 1, :]
    cols = sub.any(axis=0)
    segs, start = [], None
    for x in range(W):
        if cols[x] and start is None:
            start = x
        elif not cols[x] and start is not None:
            segs.append((start, x - 1))
            start = None
    if start is not None:
        segs.append((start, W - 1))
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] <= 1:
            merged[-1] = (merged[-1][0], s[1])
        else:
            merged.append(list(s))
    print('segs=%d' % len(merged))
    for i, (x0, x1) in enumerate(merged):
        piece = sub[:, x0:x1 + 1]
        rows = np.where(piece.any(axis=1))[0]
        if len(rows) == 0:
            continue
        p = piece[rows.min():rows.max() + 1, :]
        print('--- char %d: x %d..%d (%dx%d) ---' % (i + 1, x0, x1, p.shape[1], p.shape[0]))
        for y in range(p.shape[0]):
            print('  ' + ''.join('#' if p[y, x] else '.' for x in range(p.shape[1])))
    im = Image.fromarray(np.where(sub, 0, 255).astype(np.uint8))
    big = im.resize((im.width * 7, im.height * 7), Image.NEAREST)
    big.save('/tmp/u2_captcha_big.png')
    print('saved /tmp/u2_captcha_big.png (%dx%d)' % (big.width, big.height))
else:
    print('no pixels kept')
