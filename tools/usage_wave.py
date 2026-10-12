#!/usr/bin/env python3
"""用量波形数据生成器（原生图表版）＋ 独立波形卡。

现役「用量」卡顶部的波形块是飞书**原生图表**（由 feishu-menu-bridge 插件渲染），
它只吃数据 —— `state/usage_wave.json` 里的 vals / labels / total / ymax。
所以本文件**只算数据、只画原生图表，不渲染、不上传任何图片**（图片/GIF 那条链已弃用，未随包）。

用法：
  usage_wave.py refresh-native   读 10 分钟快照 → 算四档波形 → 写状态文件（现役，定时任务用这条）
  usage_wave.py refresh          同上（旧名，等价）
  usage_wave.py tap <档位>       切档位：写 current（用量卡的波形块按它重画）；
                                 建过独立波形卡时，同时原地更新那张卡的实体
  usage_wave.py card [档位]      打印独立波形卡的 JSON（调试 / 手动贴到别处）
  usage_wave.py send             刷新数据 → 创建卡片实体 → 发到 HERMES_WAVE_CHAT（可选，需自己设频道）
  （作为模块导入）get_runtime_state() → (token, chat_id)，pt-site-keepalive 签到脚本用

口径与图表文案/单位来自同目录 `wave_shared.py` —— 与插件共用同一份实现，不另写一套。
硬性约束：**只允许纯 stdlib**（插件在网关进程里加载 wave_shared，别把 PIL/numpy 拉进来）。
"""
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

# 波形口径的唯一实现（纯 stdlib）—— 与 feishu-menu-bridge 插件共用，改一处两边同变。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from wave_shared import (ORDER, UNIT_LABEL, chart_el as chart_el_shared,  # noqa: E402
                         fmt_k, head_content)

# 家目录口径必须与 feishu-menu-bridge 插件一致（HERMES_HOME 优先，其次 ~/.hermes）：
# 插件读 $HERMES_HOME/state/usage_wave.json，本脚本若写死 ~/.hermes，
# 非默认布局下波形块永远显示「暂无数据」。
HOME = os.environ.get('HERMES_HOME') or os.path.expanduser('~/.hermes')
STATE = os.path.join(HOME, 'state/usage_wave.json')
ENV = os.path.join(HOME, '.env')
SNAP = os.path.join(HOME, 'usage_snapshots.jsonl')

# 档位桶按**本机时区**切（含夏令时）；不写死偏移，换个时区部署也对。
TZ = dt.datetime.now().astimezone().tzinfo

# 飞书 Home chat_id 属身份信息，不写死在代码里，从环境变量取：
# 不设就只是「签到进度卡 / 独立波形卡不发」，签到本身不受影响。
CHAT = os.environ.get('HERMES_WAVE_CHAT', '')

API = 'https://open.feishu.cn/open-apis'


# ── 对外契约（record_checkin._feishu_ctx 依赖；改动需同步 pt-site-keepalive 技能）──
def get_runtime_state():
    """(token, chat_id)：签到脚本唯一入口。勿改名、勿改返回值顺序。"""
    return token(), CHAT


# ── 飞书 API（tenant_access_token / 卡片实体）────────────────────────
def _env():
    try:
        fh = open(ENV, encoding='utf-8', errors='ignore')
    except OSError:
        return {}
    out = {}
    with fh:
        for line in fh:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _req(url, payload=None, token=None, method='POST'):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header('Content-Type', 'application/json; charset=utf-8')
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            return json.loads(resp.read().decode('utf-8', 'ignore'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'ignore')
        try:
            return json.loads(body or '{}')
        except json.JSONDecodeError:
            return {'code': e.code, 'msg': body[:300]}
    except Exception as e:                      # 网络不通不该让签到脚本崩
        return {'code': -1, 'msg': str(e)[:200]}


def token(force=False):
    """带缓存的 tenant_access_token。

    每次现取要 ~150ms，而签到脚本要尽量快 —— token 有效期约 2 小时，
    缓存 90 分钟足够安全；真过期时调用方可用 force 重取。
    """
    st = {}
    if not force:
        try:
            st = json.load(open(STATE, encoding='utf-8'))
        except Exception:
            st = {}
        tc = st.get('tok') or {}
        if tc.get('v') and float(tc.get('exp', 0)) > time.time():
            return tc['v']
    e = _env()
    v = _req(API + '/auth/v3/tenant_access_token/internal',
             {'app_id': e.get('FEISHU_APP_ID', ''), 'app_secret': e.get('FEISHU_APP_SECRET', '')}
             ).get('tenant_access_token') or ''
    if v:
        st['tok'] = {'v': v, 'exp': time.time() + 5400}
        try:
            save_state(st)
        except Exception:
            pass
    return v


# ── 数据 ──────────────────────────────────────────────────────────
def _snap_series():
    """[(t, {sid: 累计 tokens})] 按时间升序。

    累计值 = sessions 表 input+output+cache_read（与面板卡同一口径，**含缓存读**）。
    文件由 usage_snapshot.py 每 10 分钟追加、保留 30 天；缺失/坏行跳过，不编数。
    """
    recs = []
    try:
        with open(SNAP, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                try:
                    t = dt.datetime.fromisoformat(str(r.get('ts') or ''))
                except (TypeError, ValueError):
                    continue
                t = t.replace(tzinfo=TZ) if t.tzinfo is None else t.astimezone(TZ)
                acc = {}
                for k, v in (r.get('sessions') or {}).items():
                    acc[k] = int(v or 0)
                for k, v in (r.get('cache') or {}).items():
                    acc[k] = acc.get(k, 0) + int(v or 0)
                recs.append((t, acc))
    except OSError:
        return []
    recs.sort(key=lambda x: x[0])
    return recs


def _snap_increments(recs):
    """逐窗正向增量 [(窗口结束时刻, 新增 tokens)]，供按桶求和。

    只累计每个会话的**正向**变化：会话被清理（从表里消失）不产生负值、也不会把
    别的会话的真实增长抵消掉 —— 这正是「末条累计 − 首条累计」算不对的根因
    （会话库清理过之后累计值会归零）。

    另：全库回填那种异常窗（大量会话同时跳变）用「30 × 非零窗口的 p95」做离群
    阈值，整窗丢弃，不编数。
    """
    out = []
    for i in range(1, len(recs)):
        t, cur = recs[i]
        prev = recs[i - 1][1]
        out.append((t, sum(max(0, cur.get(k, 0) - prev.get(k, 0))
                           for k in set(cur) | set(prev))))
    nz = sorted(v for _, v in out if v > 0)
    if len(nz) >= 20:
        p95 = nz[min(len(nz) - 1, int(len(nz) * 0.95) - 1)]
        thr = 30 * p95
        out = [(t, v) for t, v in out if v <= thr]
    return out


def nice_step(ymax, ticks=4):
    raw = max(ymax / ticks, 1e-6)
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag + 1e-9:
            return m * mag
    return 10 * mag


def load_ranges(now=None):
    recs = _snap_series()
    inc = _snap_increments(recs)
    now = now or dt.datetime.now(TZ)
    h = now.replace(minute=0, second=0, microsecond=0)
    d = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def cnt(s, e):
        """(s, e) 内新增的 token（含缓存读）= 落在该区间的快照增量之和，不摊分。

        没有快照覆盖的区间 → 0（还没数据，不编数）。
        """
        return sum(v for t, v in inc if s <= t < e)

    specs = {}
    b = [(h - dt.timedelta(hours=23 - i), h - dt.timedelta(hours=22 - i)) for i in range(24)]
    specs['24小时'] = {'vals': [cnt(s, e) for s, e in b],
                     'labels': [s.strftime('%H:00') for s, _ in b], 'label_every': 4}
    b = []
    for i in range(23, -1, -1):
        s = h - dt.timedelta(hours=i * 3 + 3)
        b.append((s, s + dt.timedelta(hours=3)))
    specs['3天'] = {'vals': [cnt(s, e) for s, e in b],
                   'labels': [s.strftime('%d日%H时') for s, _ in b], 'label_every': 4}
    b = [(d - dt.timedelta(days=i), d - dt.timedelta(days=i - 1)) for i in range(6, -1, -1)]
    specs['7天'] = {'vals': [cnt(s, e) for s, e in b],
                   'labels': [s.strftime('%m-%d') for s, _ in b], 'label_every': 1}
    b = [(d - dt.timedelta(days=i), d - dt.timedelta(days=i - 1)) for i in range(29, -1, -1)]
    specs['30天'] = {'vals': [cnt(s, e) for s, e in b],
                    'labels': [s.strftime('%m-%d') for s, _ in b], 'label_every': 5}
    for sp in specs.values():
        mx = max(sp['vals']) or 1
        st = nice_step(mx * 1.12)
        sp['ymax'] = math.ceil(mx * 1.12 / st) * st
        sp['total'] = sum(sp['vals'])
    return specs


def load_state():
    try:
        return json.load(open(STATE, encoding='utf-8'))
    except Exception:
        return {'ranges': {}, 'current': None}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def cmd_refresh_native():
    """只算数据、只写状态文件 —— **不渲染、不上传任何图片**。

    现役「用量」卡顶部的波形块是飞书**原生图表**（插件读 state 的 vals/labels/total），
    不需要图片。
    """
    n = len(_snap_series())
    specs = load_ranges()
    st = load_state()
    st.setdefault('ranges', {})
    for name in ORDER:
        sp = specs[name]
        st['ranges'][name] = {'total': sp['total'], 'ymax': sp['ymax'],
                              'vals': sp['vals'], 'labels': sp['labels'],
                              'label_every': sp['label_every']}
    if st.get('current') not in ORDER:
        st['current'] = ORDER[0]
    st['generated_at'] = dt.datetime.now(TZ).isoformat(timespec='seconds')
    save_state(st)
    print('原生波形数据已刷新 → %s' % STATE)
    for name in ORDER:
        print('  %-6s 合计 %-9s tokens  桶数 %d'
              % (name, fmt_k(specs[name]['total']), len(specs[name]['vals'])))
    if n < 2:
        print('  提示：快照只有 %d 条 —— 桶内增量要至少 2 条快照才有数。' % n)
        print('        先跑一次 usage_snapshot.py，10 分钟后再跑一次本命令。')
    return 0


# ── 独立波形卡（原生图表；不含图片动效）────────────────────────────
# 与插件侧「用量卡」共用 wave_shared 的口径；点档位的回调值同样是
# {"hermes_menu_wave": <档位>} —— 插件两个回调入口都能解码，行为与旧版一致。
def el_head(rng, total):
    return {'tag': 'markdown', 'element_id': 'md_head', 'content': head_content(rng, total)}


def el_chart(st, rng):
    info = (st.get('ranges') or {}).get(rng) or {}
    return chart_el_shared(rng, info.get('vals') or [], info.get('labels') or [], 'wave_img')


def el_btns(rng):
    """档位下拉。选项值 = 插件动作 JSON；飞书 select_static 把所选值放进 action.option。"""
    opts = []
    for name in ORDER:
        label = str(name) + ('　— 当前' if name == rng else '')
        opts.append({'text': {'tag': 'plain_text', 'content': label},
                     'value': json.dumps({'hermes_menu_wave': name}, ensure_ascii=False)})
    return {'tag': 'select_static', 'element_id': 'btns', 'width': 'fill',
            'placeholder': {'tag': 'plain_text', 'content': '切换档位（当前 %s）' % rng},
            'options': opts}


def card_json(st, rng):
    info = (st.get('ranges') or {}).get(rng) or {}
    return {
        'schema': '2.0',
        'config': {'update_multi': True, 'summary': {'content': '用量波形 · %s' % rng}},
        'header': {'title': {'tag': 'plain_text', 'content': '🌊 用量波形 · %s' % UNIT_LABEL},
                   'template': 'turquoise',
                   'subtitle': {'tag': 'plain_text', 'content': '点档位即切换（静止时是原生图表）'}},
        'body': {'elements': [
            el_head(rng, info.get('total', '?')),
            el_chart(st, rng),
            el_btns(rng),
            {'tag': 'markdown', 'element_id': 'md_foot',
             'content': '静止时是原生图表（点数据点看数值）；点档位切到新档位。'
                        '数据每 10 分钟由 `usage_wave.py refresh-native` 刷新。'},
        ]},
    }


# token 失效类错误码：重取一次再试
_TOKEN_ERRS = (99991661, 99991663, 99991664, 99991668)


def batch_update(card_id, els, tok, seq):
    """一次请求改多个组件（组件级 PUT 三次约 1.2s，批量约 0.4s，点按才不发卡）。"""
    actions = [{'action': 'update_element',
                'params': {'element_id': e['element_id'], 'element': e}} for e in els]
    r = _req(API + '/cardkit/v1/cards/%s/batch_update' % card_id,
             {'uuid': os.urandom(8).hex(), 'sequence': seq,
              'actions': json.dumps(actions, ensure_ascii=False)}, tok)
    return r.get('code'), (r.get('msg') or '')


def _card_els(st, rng):
    info = (st.get('ranges') or {}).get(rng) or {}
    return [el_head(rng, info.get('total', '?')), el_chart(st, rng), el_btns(rng)]


def cmd_tap(rng):
    """切档位。

    ① 状态文件的 current 必须改 —— 插件点「用量卡」那块波形时，走的是
       「重建用量卡」这条路，卡片内容按 current 重画；不改 current 就是点了没反应。
    ② 若建过独立波形卡（state 里有 card_id），顺手把那张卡的实体原地更新。
       实体更新失败**不算失败**（用量卡那条路已经能用了），只在输出里说明。
    """
    if rng not in ORDER:
        print('未知档位：%s（可选：%s）' % (rng, ' / '.join(ORDER)))
        return 2
    st = load_state()
    st['current'] = rng
    note = ''
    cid = str(st.get('card_id') or '')
    if cid:
        tok = token()
        if not tok:
            note = '独立波形卡未更新（拿不到 tenant_access_token）'
        else:
            seq = int(st.get('sequence') or 0) + 1
            code, msg = batch_update(cid, _card_els(st, rng), tok, seq)
            if code in _TOKEN_ERRS:
                code, msg = batch_update(cid, _card_els(st, rng), token(force=True), seq)
            if code == 0:
                st['sequence'] = seq
                note = '独立波形卡已原地更新'
            else:
                note = '独立波形卡更新失败 code=%s msg=%s' % (code, msg[:120])
    st['updated_at'] = dt.datetime.now(TZ).isoformat(timespec='seconds')
    save_state(st)
    print('档位 → %s（用量卡的波形块会按新档位重画）%s'
          % (rng, ('；' + note) if note else ''))
    return 0


def cmd_card(rng=None):
    st = load_state()
    rng = rng if rng in ORDER else (st.get('current') or ORDER[0])
    if not (st.get('ranges') or {}):
        print('状态文件里还没有波形数据 —— 先跑一次 refresh-native。')
        return 1
    print(json.dumps(card_json(st, rng), ensure_ascii=False, indent=1))
    return 0


def cmd_send():
    """创建卡片实体并发到 HERMES_WAVE_CHAT（可选功能：想让飞书会话里常驻一张波形卡再用）。"""
    if not CHAT:
        print('没设 HERMES_WAVE_CHAT（飞书会话 id）——先设好再发，例如：')
        print('  export HERMES_WAVE_CHAT=oc_你的频道id     # 也可以写进 $HERMES_HOME/.env')
        return 2
    cmd_refresh_native()
    st = load_state()
    tok = token()
    if not tok:
        print('拿不到 tenant_access_token —— 检查 $HERMES_HOME/.env 的 FEISHU_APP_ID / FEISHU_APP_SECRET。')
        return 1
    rng = st.get('current') if st.get('current') in ORDER else ORDER[0]
    r = _req(API + '/cardkit/v1/cards',
             {'type': 'card_json', 'data': json.dumps(card_json(st, rng), ensure_ascii=False)}, tok)
    cid = (r.get('data') or {}).get('card_id') or ''
    if not cid:
        print('建卡片实体失败 code=%s msg=%s' % (r.get('code'), str(r.get('msg'))[:150]))
        print('  提示：卡片实体要应用开通 cardkit:card:write（开放平台 → 权限管理）。')
        return 1
    s = _req(API + '/im/v1/messages?receive_id_type=chat_id',
             {'receive_id': CHAT, 'msg_type': 'interactive',
              'content': json.dumps({'type': 'card', 'data': {'card_id': cid}}),
              'uuid': os.urandom(8).hex()}, tok)
    st['card_id'] = cid
    st['message_id'] = (s.get('data') or {}).get('message_id', '')
    st['sequence'] = 1
    save_state(st)
    if s.get('code') != 0:
        print('卡片实体建好了（%s），但消息没投递出去 code=%s msg=%s'
              % (cid, s.get('code'), str(s.get('msg'))[:150]))
        return 1
    print('独立波形卡已发送：实体 %s　消息 %s' % (cid, st['message_id']))
    return 0


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'refresh-native'
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd in ('refresh-native', 'refresh'):
        sys.exit(cmd_refresh_native())
    elif cmd == 'tap':
        sys.exit(cmd_tap(str(arg or '')))
    elif cmd == 'card':
        sys.exit(cmd_card(arg))
    elif cmd == 'send':
        sys.exit(cmd_send())
    else:
        print(__doc__)
