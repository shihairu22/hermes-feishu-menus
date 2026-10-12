#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CnLang 验证码读取：逐列背景减除的 ASCII 点阵 + 6 倍放大图
用法: python cnlang_cap_read.py <png路径>
"""
import sys

import numpy as np
from PIL import Image

p = sys.argv[1]
im = Image.open(p).convert("L")
W, H = im.size
a = np.array(im, dtype=np.int16)
bgs = np.percentile(a, 85, axis=0).astype(np.int16)
diff = bgs[None, :] - a

print("size = %dx%d" % (W, H))
for y in range(H):
    row = []
    for x in range(W):
        d = diff[y, x]
        row.append("#" if d > 30 else ("+" if d > 14 else ("." if d > 6 else " ")))
    print("".join(row))

big = p.replace(".png", "_x6.png")
im.resize((W * 6, H * 6), Image.NEAREST).save(big)
print("saved:", big)
