#!/usr/bin/env python3
"""去噪版验证码点阵分割器：先按 8 邻域密度滤掉孤立噪点，再切列、逐字放大打印。

与 captcha_dotmatrix.py 的关系：散点噪点满图飞时，按列切分会出虚段
（空白噪点段 / 字间黏连），逐字点阵里也全是孤点。本脚本先把噪点滤掉再切分，
字符变成干净的 8~10px 笔画图，逐字判读几乎不会错。实测 Audiences / HDSky /
CHDBits 三张，与视觉模型独立给出完全一致的读数、全部一次通过。

用法：
    /usr/bin/python3 captcha_clean.py /tmp/xxx_captcha.png        # 默认 2 轮去噪
    /usr/bin/python3 captcha_clean.py /tmp/xxx_captcha.png 3      # 更狠的 3 轮

解释器：PIL/numpy 装在系统 python3（/usr/bin/python3）；camoufox venv 里没有。

判读要点：宽 1~3 像素的段基本都是噪点/装饰线，忽略；真字符宽约 7~10、高 10~13。
⚠️ 裁剪仲裁的坐标要以去噪后的切分为准（散点虚段会把真字符挤进错误区间）。
"""
import sys

from PIL import Image
import numpy as np


def load_mask(path):
    a = np.array(Image.open(path).convert('RGB')).astype(int)
    black = (a[:, :, 0] < 100) & (a[:, :, 1] < 100) & (a[:, :, 2] < 100)
    if black.sum() < 20:
        g = a.mean(axis=2)
        bg = np.percentile(g, 85, axis=0)
        black = (bg[None, :] - g) > 18
    return black


def denoise(m, passes=2):
    for _ in range(passes):
        p = np.pad(m, 1)
        nb = sum(
            p[i:i + m.shape[0], j:j + m.shape[1]]
            for i in range(3) for j in range(3)
        ) - m
        m = m & (nb >= 2)
    return m


def main():
    path = sys.argv[1]
    passes = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    black = load_mask(path)
    clean = denoise(black, passes)
    h, w = clean.shape
    inner = clean.copy()
    inner[:2, :] = False
    inner[-2:, :] = False
    inner[:, :2] = False
    inner[:, -2:] = False
    cols = inner.any(axis=0)
    segs, start = [], None
    for x in range(w):
        if cols[x] and start is None:
            start = x
        elif not cols[x] and start is not None:
            segs.append([start, x - 1])
            start = None
    if start is not None:
        segs.append([start, w - 1])
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] <= 2:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    print('size %dx%d  black=%d  cleaned=%d  segs=%d (passes=%d)'
          % (w, h, black.sum(), clean.sum(), len(merged), passes))
    for i, (x0, x1) in enumerate(merged):
        sub = inner[:, x0:x1 + 1]
        rows = np.where(sub.any(axis=1))[0]
        if len(rows) == 0:
            continue
        y0, y1 = rows.min(), rows.max()
        print('--- seg %d: x %d..%d w %d  y %d..%d h %d ---'
              % (i + 1, x0, x1, x1 - x0 + 1, y0, y1, y1 - y0 + 1))
        for y in range(y0, y1 + 1):
            print('  ' + ''.join('#' if sub[y, x] else '.' for x in range(x1 - x0 + 1)))


if __name__ == '__main__':
    main()
