#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""U2 签到图像题（showup.php）绿点定位。

用法：/usr/bin/python3 u2_dot_locate.py /tmp/u2_puzzle.png

判定：圆点 = 实心绿圆（实测约 57px、填充率 ≈0.77）。扫描条件：
  g > r+25 且 g > b+25 且 g > 110；连通域 ≥30px、近方形（长宽差≤6）、fill≥0.6。
输出圆点坐标与所在侧（LEFT/RIGHT，按中心 x 与图像半宽比较）。
定侧后：只把「圆点所在侧」的封面特征连同 4 个候选作品名交给视觉模型辨认；
两块封面都可能本来就是候选项，不要绕过圆点按画风猜（50/50 硬赌）。
时限：题目 120 秒（图上水印 VALID BEFORE <HH:MM:SS> CST 可直接读出截止点）。
"""
import sys
from collections import deque

import numpy as np
from PIL import Image

path = sys.argv[1]
a = np.array(Image.open(path).convert('RGB')).astype(int)
h, w, _ = a.shape
r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
gm = (g > r + 25) & (g > b + 25) & (g > 110)

lab = np.zeros((h, w), dtype=int)
res = []
for y in range(h):
    for x in range(w):
        if gm[y, x] and lab[y, x] == 0:
            q = deque([(y, x)]); lab[y, x] = 1; pix = []
            while q:
                yy, xx = q.popleft(); pix.append((yy, xx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        k = (yy + dy, xx + dx)
                        if 0 <= k[0] < h and 0 <= k[1] < w and gm[k[0], k[1]] and lab[k[0], k[1]] == 0:
                            lab[k[0], k[1]] = 1; q.append(k)
            n = len(pix)
            if n < 30:
                continue
            ys = [p[0] for p in pix]; xs = [p[1] for p in pix]
            ww = max(xs) - min(xs) + 1; hh = max(ys) - min(ys) + 1
            fill = n / float(ww * hh)
            res.append((n, min(xs), min(ys), ww, hh, fill))
res.sort(reverse=True)
if not res:
    print('NO_GREEN_DOT — 没找到绿色块：确认拿的是整张题图（不是缩略图），或圆点换了颜色')
    sys.exit(1)
n, x0, y0, ww, hh, fill = res[0]
cx = x0 + ww // 2
side = 'LEFT' if cx < w // 2 else 'RIGHT'
shape = 'ROUNDISH' if abs(ww - hh) <= 6 and fill >= 0.6 else 'NOT-ROUND(复核)'
print('DOT n=%d box=(%d,%d)-(%d,%d) %dx%d fill=%.2f center_x=%d/%d side=%s %s' % (
    n, x0, y0, x0 + ww - 1, y0 + hh - 1, ww, hh, fill, cx, w, side, shape))
for t in res[1:4]:
    print('  runner-up: n=%d %dx%d fill=%.2f' % (t[0], t[3], t[4], t[5]))
