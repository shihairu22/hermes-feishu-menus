#!/usr/bin/env python3
"""验证码点阵分割器：按列切出单字，再逐字放大打印点阵。

配合 references/captcha-reading.md 使用。整图点阵在长验证码上容易数错列，
先按列切分再逐字打印，与视觉模型交叉判读明显更稳。

用法：
    /usr/bin/python3 captcha_dotmatrix.py /tmp/xxx_captcha.png            # auto：纯黑文字，纯黑过少时退回逐列背景估计
    /usr/bin/python3 captcha_dotmatrix.py /tmp/xxx_captcha.png lowsat     # 低饱和深色像素净化（HDSky 签到层那类彩色噪点图）

解释器：PIL/numpy 装在系统 python3（/usr/bin/python3）；camoufox venv 里没有。

判读要点：
  - 宽 1~3 像素的段基本都是噪点/装饰线，忽略；真字符宽约 7~10、高 10~13。
  - 字符段高明显偏大（如 13~14）时可能含噪点行，按主体行读。
  - C 与 G：右侧中段完全空白 = C；右侧中段有竖笔（底部内折成横）= G。
  - 只用纯黑像素（RGB 均 <100）；纯黑过少时自动退回逐列背景估计。
"""
import sys

from PIL import Image
import numpy as np


def load_mask(path, mode='auto'):
    a = np.array(Image.open(path).convert('RGB')).astype(int)
    if mode == 'lowsat':
        # 低饱和深色像素：文字是深色低饱和，噪点是高饱和彩色/浅色（HDSky 签到层实测口径）
        mx, mn = a.max(axis=2), a.min(axis=2)
        return a, (mx < 170) & ((mx - mn) < 70)
    black = (a[:, :, 0] < 100) & (a[:, :, 1] < 100) & (a[:, :, 2] < 100)
    if black.sum() < 20:
        g = a.mean(axis=2)
        bg = np.percentile(g, 85, axis=0)
        black = (bg[None, :] - g) > 18
    return a, black


def split_columns(mask):
    h, w = mask.shape
    inner = mask.copy()
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
    return inner, merged


def main():
    path = sys.argv[1]
    mode = sys.argv[2].lower() if len(sys.argv) > 2 else 'auto'
    a, black = load_mask(path, mode)
    h, w = black.shape
    inner, segs = split_columns(black)
    print('图片 %s  尺寸 %dx%d  mode=%s  命中像素 %d  候选字符段 %d'
          % (path, w, h, mode, black.sum(), len(segs)))
    for i, (x0, x1) in enumerate(segs):
        sub = inner[:, x0:x1 + 1]
        rows = np.where(sub.any(axis=1))[0]
        if len(rows) == 0:
            continue
        y0, y1 = rows.min(), rows.max()
        print('--- 字符 %d: x %d..%d 宽 %d, y %d..%d 高 %d ---'
              % (i + 1, x0, x1, x1 - x0 + 1, y0, y1, y1 - y0 + 1))
        for y in range(y0, y1 + 1):
            print('    ' + ''.join('#' if sub[y, x] else '.' for x in range(x1 - x0 + 1)))


if __name__ == '__main__':
    main()
