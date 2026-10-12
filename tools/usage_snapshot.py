#!/usr/bin/env python3
"""用量快照：把每个会话的累计 tokens（含缓存读）追加一行到 usage_snapshots.jsonl。

为什么要它：Hermes 只在 sessions 行上存一个累计总数，没有逐日切片，
所以「今天用了多少」「每天总量」都算不出来。每 10 分钟记一次，
之后就能用两次快照的真实差值算出来——是实测，不是摊分。

口径：sessions 表 input+output+cache_read（与中转站一致；中转把缓存命中也算进总量）。
v2 起多记一个 cache 字段，插件据此把「今天」也算成含缓存口径。

只读 state.db，不联网，不发消息。保留 30 天。
"""
import datetime as dt
import json
import os
import sqlite3
import sys

HOME = os.environ.get('HERMES_HOME') or os.path.expanduser('~/.hermes')
DB = os.path.join(HOME, 'state.db')
OUT = os.path.join(HOME, 'usage_snapshots.jsonl')
KEEP_DAYS = 30
SCHEMA_V = 2


def main() -> int:
    conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    try:
        rows = conn.execute(
            "SELECT id, COALESCE(input_tokens,0)+COALESCE(output_tokens,0), "
            "       COALESCE(cache_read_tokens,0) "
            "FROM sessions "
            "WHERE COALESCE(input_tokens,0)+COALESCE(output_tokens,0)"
            "    + COALESCE(cache_read_tokens,0) > 0"
        ).fetchall()
    finally:
        conn.close()

    now = dt.datetime.now()
    rec = {
        'ts': now.isoformat(timespec='seconds'),
        'v': SCHEMA_V,
        'sessions': {r[0]: int(r[1]) for r in rows},
        'cache': {r[0]: int(r[2]) for r in rows},
    }
    line = json.dumps(rec, ensure_ascii=False, separators=(',', ':'))

    # 读旧内容 → 追加 → 裁剪超期行（保持原子写，避免读到的半行）
    old = []
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8') as f:
            old = [l for l in f if l.strip()]
    cutoff = (now - dt.timedelta(days=KEEP_DAYS)).isoformat(timespec='seconds')
    kept = []
    for l in old:
        try:
            if json.loads(l).get('ts', '') >= cutoff:
                kept.append(l)
        except ValueError:
            continue
    kept.append(line + '\n')

    tmp = OUT + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.writelines(kept)
    os.replace(tmp, OUT)

    io_total = sum(rec['sessions'].values())
    cache_total = sum(rec['cache'].values())
    print(f"{now:%Y-%m-%d %H:%M:%S} 快照 v{SCHEMA_V} {len(rows)} 个会话："
          f"输入+输出 {io_total:,} + 缓存读 {cache_total:,} = {io_total + cache_total:,} tokens；"
          f"文件 {len(kept)} 行，{os.path.getsize(OUT)} B")
    return 0


if __name__ == '__main__':
    sys.exit(main())
