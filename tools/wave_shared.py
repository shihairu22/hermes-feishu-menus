"""用量波形的共享口径 —— feishu-menu-bridge 插件与 usage_wave.py 共用一份。

2026-10-04 审计 P2：波形渲染此前有两套（插件的 _wave_block 与 usage_wave.py 的
chart_el/el_btns/head_content），文案/单位/档位改一处忘一处。这里收敛成唯一实现。

2026-10-07：口径由「轮次」改为 **token 用量**（用户要求）。数据源 = usage_snapshots.jsonl
的 10 分钟累计快照差值（sessions 表 input+output+cache_read，与面板卡同一口径，含缓存读）。

硬性约束：**只允许纯 stdlib** —— 插件在网关进程里加载本文件，绝不能把 PIL 拉进去。
"""

ORDER = ('24小时', '3天', '7天', '30天')

#: 单位文案的「量词」——口径改了就改这里一处，两边同变。
UNIT = 'tokens'
UNIT_LABEL = 'Token'


def fmt_k(v):
    """≥1e9 用 B、≥1e6 用 M、≥1000 用 k（2412345 → 2.4M），<1000 原样。

    非数值原样回字符串：调用方可能传 '?'（档位还没算出合计），不能在这里炸。
    """
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    for div, suf in ((1e9, 'B'), (1e6, 'M'), (1e3, 'k')):
        if abs(v) >= div:
            return ('%.1f' % (v / div)).rstrip('0').rstrip('.') + suf
    return '%g' % round(v)


def chart_units(vals):
    """按峰值决定 (除数, 单位文案)：百万换 M、上千换 k，刻度才不挤成 1000000。"""
    m = max(vals) if vals else 0
    if m >= 1e6:
        return 1e6, 'M ' + UNIT
    if m >= 1e3:
        return 1e3, 'k ' + UNIT
    return 1.0, UNIT


def head_content(rng, total, prefix=''):
    """卡片抬头正文（插件传自己的前缀，usage_wave 留空 —— 两边共用同一句口径）。"""
    return (prefix + '当前 **%s**　·　合计 **%s** %s\n'
            '口径：每个时间桶内新增的 token（输入+输出+缓存读，10 分钟快照的真实差值，不摊分）'
            % (rng, fmt_k(total), UNIT))


def chart_el(rng, vals, labels, element_id='wave_img'):
    """飞书原生图表元素（静止态）。element_id 由调用方给：两边槽位 id 不同。"""
    div, unit = chart_units(vals)
    return {
        'tag': 'chart', 'element_id': element_id, 'height': '210px', 'preview': True,
        'color_theme': 'brand',
        'chart_spec': {
            'type': 'line',
            'title': {'text': '用量走势 · %s（单位：%s）' % (UNIT_LABEL, unit)},
            'data': {'values': [{'bucket': lb, 'tokens': round(v / div, 2)}
                                for lb, v in zip(labels, vals)]},
            'xField': 'bucket',
            'yField': 'tokens',
            'point': {'visible': True},
        },
    }


def range_labels(rng):
    """四档按钮的标签（选中项带 ● 前缀）—— 容器由各自平台侧去搭。"""
    return [('● ' if n == rng else '') + n for n in ORDER]
