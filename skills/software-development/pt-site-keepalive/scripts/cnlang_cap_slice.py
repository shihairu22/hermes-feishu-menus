#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按列切片打印验证码点阵（带列标尺），用于逐字判形"""
import sys

import numpy as np
from PIL import Image

p = sys.argv[1]
im = Image.open(p).convert("L")
a = np.array(im, dtype=np.int16)

slices = [(10, 33), (33, 52), (52, 76), (74, 100)]
for x1, x2 in slices:
    seg = a[:, x1:x2]
    bgs = np.percentile(seg, 85, axis=0).astype(np.int16)
    diff = bgs[None, :] - seg
    h, w = diff.shape
    print("===== 切片 cols %d-%d =====" % (x1, x2))
    ruler = ""
    for i in range(w):
        c = x1 + i
        ruler += str(c // 10 % 10) if c % 10 == 0 else " "
    print(ruler)
    for y in range(h):
        row = []
        for x in range(w):
            d = diff[y, x]
            row.append("#" if d > 30 else ("+" if d > 14 else ("." if d > 6 else " ")))
        print("".join(row))
    print()
