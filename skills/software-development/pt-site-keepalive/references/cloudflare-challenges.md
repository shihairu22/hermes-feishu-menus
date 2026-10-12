# Cloudflare 挑战：查什么、怎么判定、何时止损

适用：登录/签到被 Cloudflare 挡住时，先按本文定位层级，再决定是否值得继续。

## ★ 实测：TLS 指纹对 CF 挑战**无效**（2026-09-27，PigGo）

用 `curl_cffi`（能完全模拟真实浏览器的 TLS/JA3 指纹）测同一个站：

```
impersonate=firefox133 / firefox135 / chrome124 / chrome131 / safari17_0
  → 全部 HTTP 403 + 挑战页（与普通 curl 一样）
```

**结论：CF 挑战拦的不是 TLS 指纹，而是「必须执行 JS」这件事。**
所以伪造 TLS/HTTP 头这条路不通，**唯一解是真浏览器**（Camoufox 实测能过）。

### 三层判定表（PigGo 实测）

| 客户端 | TLS 指纹 | 能跑 JS | 结果 |
|---|---|---|---|
| requests / curl | ❌ | ❌ | 403 挑战页 |
| curl_cffi（5 种浏览器指纹）| ✅ 完全模拟 | ❌ | **403 挑战页** |
| Camoufox（Firefox 内核）| ✅ 真实 | ✅ | **✅ 过 CF** |

### 判定脚本

`scripts/probe_cloudflare.py` —— 一次测出：挑战类型（`cf-mitigated` 头）、
挑战特征（`Just a moment` / `cf_chl` / `challenge-platform`）、出口机房（CF-RAY 后缀）、
以及 curl_cffi 各指纹的表现。

## 挑战层级

| 层级 | 现象 | 说明 |
|---|---|---|
| 托管式 Managed Challenge | 页面自动过（1~10 秒） | 浏览器环境合格就放行，无需交互 |
| 交互式 Interactive Challenge | 弹 Turnstile「请验证您是真人」复选框 | 需要真人点一下 |
| 路径级规则 | **只有某个路径**被挑战，首页/登录页正常 | 站点有意为之（签到、发帖等敏感功能） |
| 纯 JS 拦截页 | 标题「请稍候… / Just a moment...」，无复选框、永不自动过 | 环境或 IP 信誉不达标，或站点规则更严 |

**关键判据**：用 `curl` 带正常 UA 探「首页」和「目标路径」。首页 200 无挑战 + 目标路径 403 且响应头含 `cf-mitigated: challenge` → **路径级规则**。此时换浏览器、换点击方式、换 UA 都不会有用——**但先别止损，跑一轮「编码变体探测」**（见本文《路径级规则可能有缝》专节：字面匹配的规则用百分号编码即可穿透）。

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0"
for u in "https://site/" "https://site/<目标路径>"; do
  code=$(curl -s -o /tmp/pb.html -D /tmp/ph.txt -w "%{http_code}" -A "$UA" --max-time 20 -L "$u")
  grep -i '^cf-mitigated' /tmp/ph.txt | tr -d '\r'
  grep -qiE 'Just a moment|security verification|正在进行安全验证|cf_chl' /tmp/pb.html && echo "$u → CF挑战" || echo "$u → 无挑战 ($code)"
done
```

## ★ 被动 JSD 层：GET 放行、POST 可能被挑战（2026-09-30，TTG 实测）

- 页面正常返回、内容完整，却在 HTML 里内嵌 `challenge-platform/scripts/jsd/main.js` —— 这是 **CF JavaScript Detections（遥测）**：**既不能据此判「无挑战」，也不能据此判「被墙」**。
- 判定有无实际拦截的唯一可靠办法：**拿一次带会话的 POST 实测** —— 若响应无应用层结果、且**不产生任何会话 cookie**（随后 GET 目标页仍回登录页），即 POST 被 JSD 挑战拦下；这类拦截通常**不消耗站点自身的失败次数**（请求未达应用层）。
- 被 JSD 拦 POST 的站（TTG 实例，额度仅 6 次）：立即止步、保持浏览器流程；**GET 可达性不能作为「站点可纯脚本」的依据**。
- 反例参照：天雪的 CF 同为被动层但 GET/POST 都不拦（纯 HTTP 全流程可跑，见 `references/skyey.md` §5）——同样是「有 CF 字样」，结论可以相反，只有实测算数。

## ★ 路径级规则可能有缝：编码变体探测（先测一轮再止损）

站方的路径规则若是「按字面子串匹配 URL」（管理员手写的规则常见如此），把关键子串里的**任一字符做百分号编码**，请求就不再命中该规则、被边缘直接放行——而 Web 后端（PHP 等）收到后会自动解码、照常处理。命中与否只取决于规则有没有做规范化，与客户端类型无关。

**探测矩阵**（对目标路径逐个 GET，比对 `status` 与 `cf-mitigated` 头）：

| 变体 | 典型结果 |
|---|---|
| 原样 URL（对照） | 403 + `cf-mitigated: challenge` |
| 关键子串单字符编码（`%64` 代 `d`、`%5F` 代 `_`） | **200 = 缝隙成立** |
| 冒号等「未破坏子串」的编码（`%3A`） | 仍 403（子串完整，规则照中） |
| 大小写 / 双斜杠 / 尾点 | 通常仍 403 |

- 缝隙成立后：该路径**全部**业务请求（取 token、GET 面板、POST 动作）都改走编码形式；**纯 curl/requests 同样有效**——穿透发生在边缘规则层，与应用层无关。
- 模式脚本：`scripts/cnlang_cf_variants.py`（改 URL 列表即可套用到任何站）。
- 性质：碰「规则写得粗」的概率技——规则做了规范化匹配即无效，站点事后也常补规则；测一轮只要几分钟，**值得测，但不是万能钥匙**。
- 对交互式 Turnstile 无效：编码只破「字面匹配的放行/拦截规则」，破不了人机验证（需点击的盾依旧是硬墙）。

## Turnstile 查哪些信号（信任分是多层叠加的）

- **浏览器环境**：Canvas 指纹、**WebGL 的 GPU 厂商/渲染器/扩展**、`AudioContext`、`MediaDevices`、`Bluetooth`
- **行为**：鼠标轨迹（速度/加速度）、键盘节奏、页面停留时长
- **网络**：IP 信誉、**TLS 指纹（JA3/JA4）与声称的浏览器是否匹配**

其中最容易踩的两个坑：

1. **WebGL 渲染器**。真实桌面应报 `ANGLE (NVIDIA/Intel/AMD ...)`；无头/虚拟机常报 `SwiftShader Device` 或干脆缺失 → 直接判机器人。加不加 `--disable-gpu` 都可能是 SwiftShader，要用 `scripts/fingerprint_probe.py` 实测。
2. **`navigator.webdriver`**。Playwright 驱动的 Chrome 是 `true`；纯命令行启动的 Chrome、以及 Camoufox 都是 `false`。

## 环境信誉与时间

- **信誉是按域名算的**：同一台机器在 A 站信誉正常，在 B 站可能已被降级。同一 IP 在短时间内的密集自动化请求（几十次登录尝试）会把该域名的信誉打低，挑战从「托管式」升级为「交互式」甚至「永不自动过的 JS 拦截页」。
- **信誉会随时间恢复**：等 1~2 天再试是有效且唯一剩下的变量。
- `cf_clearance` 常与 **IP + User-Agent 绑定**，换任一端都要重新求解；因此**不能**把用户在自己设备上拿到的通行证搬过来用（IP 不同）。

## 方案矩阵（实测结论）

| 方案 | 对交互式 Turnstile | 备注 |
|---|---|---|
| Playwright/Chrome（无头或有头 Xvfb） | ❌ | `webdriver=true` + SwiftShader，环境层就被扣分 |
| CDP 合成鼠标事件 / Playwright 原生 mouse 点复选框 | ❌ | 合成事件不被信任 |
| 纯启动 Chrome（无 CDP）+ `xdotool` X11 真实鼠标事件 | ⚠️ 点击被组件接受过，但 CF 后续校验仍失败 | 说明卡点不在点击 |
| Camoufox（Firefox 内核）原生指纹 | 环境最干净（`webdriver=false` + 真实 GPU） | 若仍被拦，基本可判定为路径级规则或 IP 信誉 |
| 换主机名 / 常规路径变体 | ❌ | 路径级规则对所有主机名、大小写/双斜杠等常规变体生效；**百分号编码变体是例外——见《路径级规则可能有缝》专节** |
| 纯 HTTP 客户端（requests / curl_cffi） | ❌ | 无法执行 JS 与交互 |

**止损线**：环境已用 `scripts/fingerprint_probe.py` 验证干净、且目标路径在原样 URL 的所有常规变体上都被挑战时，**先跑一轮编码变体探测**（见专节；字面匹配的规则可被单字符百分号编码穿透）；确认无缝隙后再**停止自动化尝试**，改让用户手动点一下，或安排 1~2 天后重试。继续换姿势只会白耗时间，也可能进一步拉低该域名下的 IP 信誉。

## 可自动化的部分

即使签到过不去，**登录 + 会话保活 + 读取积分/余额**通常都能自动化（这些页面往往不在路径级规则内）。可行的降级方案：每天自动登录一次保持会话，读余额；余额没涨就提醒用户手动签到。

**结论更新**：路径级规则一旦被编码穿透，原先「签到只能人工」的判断要重估——实例见 `references/cnlang.md`「签到完全突破」节（签到同样纯 HTTP 化）。
