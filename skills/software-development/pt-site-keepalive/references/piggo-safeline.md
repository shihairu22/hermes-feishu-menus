# PigGo 的两层防护：Cloudflare + SafeLine（雷池）

> 2026-09-27 源码级探测。结论：**浏览器能过，不需要绕过；卡住是误判**。

## 一、结论先行

**Camoufox 实际上能通过 SafeLine 验证** —— 抓包实测它成功拿到了 JWT：

```
POST https://challenge.rivers.chaitin.cn/challenge/v2/api/verify
  → {"message":"ok","code":200,"data":{"jwt":"eyJhbG..."}}
```

所以 PigGo 登录失败**不是 WAF 问题**，而是：

1. `Client Verifying` 阶段本身慢（PoW 计算 + 多次网络往返），**实测到 NEED_2FA 需约 9~20 分钟**；
2. 而 `... | tail -N` 会**完全缓冲输出**，过程看不见 → 被误判为「卡死」→ 被提前杀掉。

★ **教训：PigGo 不能凭「十几分钟无输出」就杀掉。** 判断进度只看两处：
`/tmp/nx_piggo_captcha*.png` 或 `/tmp/nx_piggo_2fa.txt` 是否出现；
`cookies.sqlite` 报 `database is locked` 反而是「浏览器正在正常工作」的正面信号。

## 二、两层防护的结构

| 层 | 位置 | 浏览器能否过 |
|---|---|---|
| 第 1 层 Cloudflare | `piggo.me` 首页 | ✅ Camoufox 能过（纯 requests 会得 403「Just a moment...」）|
| 第 2 层 SafeLine 人机验证 | `challenge.rivers.chaitin.cn`（**外部域名**）| ✅ 能过（JS + WASM 算 PoW）|

## 三、SafeLine 挑战 v2 的完整链路（浏览器抓包）

```
GET  challenge/v2/challenge.css      # 遮罩层样式（#sl-bg / #sl-box）
GET  challenge/v2/calc.js            # 挑战主逻辑
GET  challenge/v2/calc.wasm          # ★ 关键：用 WebAssembly 算令牌

POST challenge/v2/api/issue
     {"client_id":"<32位hex>_5","level":1}
  →  {"message":"ok","code":200,"data":{"data":[48,41,89,...],"issue_id":"6X8rWAgkyAMsaFXP"}}

POST challenge/v2/api/verify
     {"issue_id":"...","result":[52,16,7,2],"serials":[],
      "client":{"userAgent":"Mozilla/5.0 ... Firefox/152.0","platform":"Win32",
                "language":"en-US,en","vendor":"","screen":[0,0],
                "visitorId":"","score":0,"target":[]}}
  →  {"message":"ok","code":200,"data":{"jwt":"eyJhbG..."}}
```

拿到 JWT 后写入 cookie `sl-challenge-jwt`（+ `sl-challenge-server`）即放行。

## 四、公开的纯 Python 绕过方案（备查，本次未采用）

来源：`github.com/xj2268-TA/SafeLine-bypass`（第三方 PoC，未验证在本站是否有效）

```python
def calc(data):
    t, n, total = 1, len(data), sum(data)
    r = (6 + n + total) % 6 + 6
    for _ in range(r): t *= 6
    if t < 6666: t *= n
    if t > 0x3F940AA: t //= n
    for idx, val in enumerate(data):
        t += pow(val, 3); t ^= idx; t ^= val + idx
    result = []
    while t > 0: result.insert(0, t & 63); t >>= 6
    return result
```

流程：GET 首页拿 `SafeLineChallenge("<client_id>")` → issue → calc → verify → 带 jwt 重试。

⚠️ **为什么本次没走这条路**：① 纯 requests 会被**第 1 层 Cloudflare 挡在 403**，
要先用浏览器过 CF 才能碰 SafeLine；② 浏览器已验证能自然过 SafeLine；
③ 官方前端用的是 `calc.wasm`，Python 版 calc 是否等价未验证。

## 五、探测脚本

- `probe_piggo_waf.py` — 浏览器过 CF 后抓 SafeLine 全部请求/响应（只读）
- `test_piggo_challenge.py` — 纯 requests 走公开 PoC 算法（会被 CF 拦，仅作验证）

## 六、算法完整还原（2026-10-03 完成，实测验证 ✓）

**calc.wasm（911B）已完整反汇编读出，并与官方行为三路互验通过**：官方 wasm 直跑 == 反汇编复刻 == 公开 PoC == 浏览器真实提交；304 例合成数据 + 1 组真实 issue/verify 配对，全对。

### 归档原件（`assets/piggo-safeline/`）
`calc.wasm`（官方原件 911B）· `calc.js`（2999B）· `calc.wat`（全量反汇编）· `pair.json`（真实配对）· `calc_impls.py`（复刻实现+自测）· `calc_run.js`（node 直跑 wasm）· `verify_pair.py`（终验）· `walkthrough.py`（案例逐步）

### 还原出的算法（等价伪码）

```python
def calc(data):                    # data = issue 返回的整数数组（实测值域可达 0..98）
    n = len(data)
    total = sum(data)
    r = (6 + n + total) % 6 + 6    # r ∈ [6,11]
    T = 6 ** r
    if T < 6666:     T *= n        # 死分支：6^6=46656>6666，实际永不触发
    if T > 66666666: T //= n       # 实际仅 r=11 触发（6^11=362797056）
    for i, v in enumerate(data):
        T = (T + v**3)             # 32 位环回（wasm i32 / JS ToInt32 双证据）
        T ^= i
        T ^= (v + i)
    result = []
    while T > 0:
        result.insert(0, T & 63)   # 6-bit 一组、MSB 在前 → verify 提交的 result
        T >>= 6
    return result
```

### 关键细节
- **worker 调用协议**：`reset()` → 每个数据 `arg(v)` → `k = calc()`（返回位数）→ `ret()` × k。内存：输入 @1040（计数 @1024）、输出栈 @5136（计数 @1028）；`ret` 为 LIFO 弹出 → 数字天然 MSB 在前。
- **wasm 优化**：×6^r 拆成 (r & ~7) 次 ×6^8(=1679616) + (r & 7) 次单乘；`T<6666` 分支用「预存的 6^(r-1) 与 1111 无符号比较 + select」等价变形；求和 4 路展开。
- **calc.js 内嵌纯 JS 兜底**（无 WebAssembly 时用），与公开 PoC 逐行对应——即 PoC 是这份官方 JS 的 Python 直译；本次独立反汇编验证 + 边界语义确认。
- **语义差异区**：仅当挑战数据极大（≈ >8000 项、中间值溢 2^31）时三实现可能分叉；真实挑战 n=15~几十，完全一致。
- 真实案例（2026-10-03）：n=15, total=765, r=6, T0=46656 → 迭代后 T=4106484 → `[15,42,35,52]` == 浏览器实际提交。
