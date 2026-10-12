# BYRBT（byr.pt，北邮人）—— 登录保活（已接入例行，第 27 站）

> 结论：**2026-10-07 已恢复** —— 用户修订阅后，经 NAS 代理 `curl -x http://127.0.0.1:7890 https://byr.pt/` 拿到 **302 → `https://byr.pt/login`（放行）**，`byr_http.py --stage1` 登录成功、`--stage2` 复核回「欢迎, PTUSER 兵长 奥皮 · Extreme User · 分享率 8,111.15 · 上传 9.766 TiB」。直连仍是 **403**（家宽 `240e:` 段在站点黑名单里）。
> **无传统「每日签到」** → 例行做 **登录保活**（也可顺便拿趣味盒投票的魔力值）。
> 2026-09-27 实测：登录成功（`欢迎, PTUSER`），账号 Extreme User。

## 一、★ 代理状态（2026-10-07 已恢复）

- `byr.pt` 解析到 **教育网 IPv6**（`2001:da8:215:4078:...`，CERNET2）——**IPv6-only，无 A 记录**
- **本机直连：HTTP 403**（0.08s 即回，直接被拒 = 源 IP 黑名单；本机全局 v6 是 `240e:3a2:...`）
- **走 NAS 代理：2026-10-07 ✅ 通** —— 用户**修订阅**后自愈。恢复后的形态（对比 §9.3 失效时的形态）：
  - `V6代理` 组现在 **49 个节点**，且 **`use=[]`、节点直接列在 `proxies` 里**（不再是 `use` 引用那个整组死掉的 `二号订阅集`）—— 这恰好就是 §八 修法优先级第 3 条要求的形态
  - 代理出口有 IPv6：`curl -x <代理> http://ipv6.google.com/generate_204` → **204**
  - 端到端：`https://byr.pt/` → **302 → /login**；`https://byr.pt/login.php` → **302**
  - 代理出口 IPv4 = `116.251.216.38`
- 脚本里固定用 `Camoufox(proxy={"server": "http://127.0.0.1:7890"})`
- ⚠️ Camoufox 带 proxy 时会警告建议 `geoip=True`，但 **不要加**（本机 venv 没装 `camoufox[geoip]`，会直接抛 `NotInstalledGeoIPExtra` 而启动失败）
- ★ **教训（已写进 §9.3）**：这次不是站点或凭据的问题，就是**订阅挂了**。「代理下曾实测一次过」和「代理下曾实测全挂」都**不代表现在** —— 每次失败先量订阅健康度（§9.4），别直接归因站点。

## 二、站点结构（混合架构，别搞错）

- 外层是 **Vite/Vue SPA**（`<div id="app">` + `/assets/index-*.js`，页面 html 仅 431 字节）
- 登录走 **API**：`POST https://byr.pt/api/v2/login.php`（浏览器里由 SPA 发起；页面标题「登录 - BYRBT」）
- 登录表单：**一个 `input[type=text]`（placeholder「请输入用户名」，支持 用户名/手机号/邮箱/学号 四种 tab）+ 一个 `input[type=password]` + `button[type=submit]`（“登录”）**；另有“保持登录”（自定义控件，不是原生 checkbox）
  - ⚠️ 两个 input **都没有 name / id**，只能用 `input[type=text]` / `input[type=password]` 选择器
- 登录后的内页仍是**经典 NexusPHP 风格 php**：`index.php` / `usercp.php` / `fun.php` / `mybonus.php` / `userdetails.php` / `log.php` / `forums.php`
- 成功判据：内页出现「欢迎, PTUSER」/「退出」/「魔力值 [明细]」
- ⚠️ **「保持登录」不会跨会话生效**（登录 cookie 不持久化）→ **必须每次重新登录**，不能靠持久档案跳过

## 三、签到：本站在没有

- 导航栏：首页 / 论坛 / 种子 / 试种 / 发布 / 求种 / 字幕 / 控制面板 / 日志 / **趣味盒** / 竞猜 / 徽章 / 设计 / 排行榜 / 规则 / 常见问题 / 管理组 —— **无签到入口**
- `mybonus.php` 的「魔力值获取方式」官方清单：**做种** / 发布新种子 +60 / 上传一个字幕 +5 / **参与一次趣味盒投票 +10** / 收到感谢 +10 —— **没有签到**
- 常用签到路径 `/attendance`、`/signin`、`/checkin`、`/api/signin` 均返回 **404（SPA 风格的“出错啦！该资源不存在”）**
- ⇒ **例行里对它做「登录保活」**（同天雪 / MonikaDesign / TorrentLeech / 葡萄）

## 四、可选的每日收益：趣味盒（fun.php）

- 趣味盒 = 站点定期发一期「每日一乐」图片帖（每期一行，带 图片数/评级/有趣票/有趣占比/收益）
- 首页会显示：`下次抢发趣味盒的时间为：YYYY-MM-DD HH:MM:SS`（固定在 14:08 左右）
- **参与投票 = +10 魔力值**（同时给发布者额外魔力值）→ 属于主观评价动作，需要看完图后在弹窗里选评级
- 列表里的「浏览」链接都是 JS：`javascript: void(0)` + `onclick="funbox('funpage', <期号>)"` → **必须浏览器里开弹窗操作**，无法用简单 GET 完成（除非逆向后端接口）
- 抢发（发自己的趣味盒）能拿更多，但需要用户本人选图发布，不适合代做

## 五、账号快照（2026-09-27）

- 用户名 `PTUSER`（昵称显示为「兵长奥皮」）；等级 **Extreme User**；邀请人 `dxq14`；加入日期 2023-08-23；学校 江苏科技大学
- 魔力值 1,034,320.6 / 分享率 8,111.15 / 上传 9.766 TiB / 下载 1.23 GiB / 上传排行 6437 / 邀请 5 / 做种 0
- 魔力值明细只看到「做种」自动入账（每天 00:02 与 12:02 左右结算）
- 其他：全站 Free 期间 2026-09-25 ~ 2026-10-03；页脚写着「BYRBT DO NOT PROVIDE SERVICES TO EU CITIZENS」
- 已知站点侧故障（与登录无关）：`/bet.php`（竞猜）返回 **500**（`NexusModel::load(): Argument #1 ($id) must be of type int, null given`）；`/medal.php` 404

## 六、运行要点

- 必须 `xvfb-run -a` 跑 Camoufox（无显示环境）
- 不要开 `geoip=True`（见第一节）
- 登录后等 8~9 秒再断言（SPA 提交 + 跳转）
- 本次实测 1 次登录即成功，未遇到验证码/2FA

## 七、纯 HTTP 版 `scripts/byr_http.py`（2026-09-30，已转）

- 从 SPA bundle（`/assets/*.js`）逆向出登录调用：`POST https://byr.pt/api/v2/login.php`，**JSON** body：
  `{"type":"username","username":U,"password":P,"remember":false}`（type 支持 username/mobile/email/studentId）。
- 响应信封：`{"success":bool,"code":200,"msg":...,"data":{"auth_token":...}}`；令牌经 `Authorization: Bearer <token>` 用于后续 API，同时 Session cookie 留存（classic 页 `index.php` 直接复用）。
- 实测（走 NAS 代理）：`① 登录: ✅ 成功 msg='登录成功'` → `index.php`：「欢迎, PTUSER 兵长奥皮 · Extreme User · 分享率 8,111.15 · 上传 9.766 TiB」。
- `--stage1` 登录 / `--stage2` 复核；cookie 在 `~/.pt-sessions/state/byr_cookies.json`、token 在 `byr_state.json`。**保留每次重登**（cookie 不持久，勿依赖档案跳过）。

## 八、⚠️ 2026-10-06 实测：登录失败，根因是代理出口到不了 CERNET（非配置被改）—— **已于 2026-10-07 修订阅后恢复**

**现象**：`byr_http.py --stage1` 失败，`SSL: UNEXPECTED_EOF_WHILE_READING`。

**根因链（已逐步实测锁定）**：
1. `byr.pt` **只有 AAAA 记录**（`2001:da8:215:...`，CERNET 教育网）—— **IPv6-only，无 IPv4**。
2. mihomo 里 `byr.pt` 是**唯一**使用 `V6代理` 组的规则 ⇒ **改这个组只影响 BYR 一站，不碰其它任何流量**。
3. `V6代理` 组是 **url-test**，健康检查 URL = `http://ipv6.google.com/generate_204`，当前选中 **🇭🇰 香港 01**。
4. 代理 **CONNECT 隧道建得起来（HTTP 200）**，但 **TLS ClientHello 发出后无响应** ⇒ 该节点 IPv6 到不了 CERNET 网段。
5. `curl -x http://127.0.0.1:7890 https://byr.pt/` → **HTTP 000，5ms 失败**（立即被拒，非超时）；socks5h / http80 同样失败。
6. 代理出口 IP = `134.195.101.180`（与档案里 2026-09-30 记的香港 IPv6 `2404:c140:...` **已不同** ⇒ 节点/线路换过了）。

**修法优先级（改路由器配置，须用户明确点头，不要擅动）**：
1. **先修订阅**（代价最低、最可能）：`V6代理` 组只挂 `二号订阅集`，而该订阅集实测**整组失效**（见 §9.3）—— 订阅恢复或换源后 BYR 大概率自愈。
2. **换组**：把 `V6代理` 的 `use` 指到一个**已实测能到 CERNET** 的订阅集。
3. **换健康检查 URL（必须连带改节点来源，否则无效）**：把 `V6代理` 的 url-test 检查地址从 `ipv6.google.com` 换成能代表 **CERNET 可达性**的地址（如 `https://byr.pt/` + `expected-status: 200-499`）—— ⚠️ **但官方文档明写：策略组的 `url` 只作用于 `proxies` 字段的节点，对 `use` 引入的订阅集节点完全无效**（后者走订阅集自己的 `health-check.url`）。所以**必须同时把节点从 `use` 改成直接列 `proxies`（或 `include-all-proxies` + filter），否则这句 `url` 是空转且不报错**。`V6代理` 组现在那句标着「【关键】只有支持 IPv6 的节点才能通过测试」的注释，**实际一直没生效** —— 该组的 49 个节点用的是 `二号订阅集` 的 `https://github.com/generate_204`（普通双栈地址，不筛 IPv6）。
4. **换出口**：CF WARP / 自建海外 IPv6（见 §9.5）。

⚠️ **前提铁律**：BYR 是**源 IP 黑名单**，**「挂上代理」不等于「通」**。任何配置改动之前，先用 §9.4 的只读测速确认目标节点真能到 CERNET。

**mihomo API 坑**：
- **认不出带 emoji 的节点名**：纯 ASCII 名（`DIRECT`）`/proxies/<name>/delay` 正常返回（`{"delay":35}`），emoji 名一律 `Resource not found`；**但按「组」批量测速照常可行**（见 §9.4）—— 此前记的「无法逐节点测速」只对 `/proxies/<name>/delay` 成立。
- 响应外层：`/proxies` 是 `{"proxies":{...}}`、`/providers/proxies` 是 `{"providers":{...}}`。
- **PUT 切组接口调了不生效**（读回 `now` 不变，`生效=N`）⇒ 别指望用 API 临时切组来测节点。
- 实测 mihomo 容器 `RestartCount=0`、config.yaml mtime `2026-04-25`、所有组选择均为配置默认值。

## 九、★ 续查：为什么「走代理」也不通 —— 源 IP 黑名单 + 整组订阅失效

### 9.1 拦截机制（先搞清这个，再谈方案）

- `byr.pt` **只有 AAAA 记录**（`2001:da8:215:...`，CERNET）⇒ **IPv6-only，没有 IPv4 入口**。
- 拦截是**源 IP 黑名单，不是白名单**：站点官方口径＝「屏蔽了 ipv4 和国内 ipv6」「**240e、2409、2408 开头的 ipv6 地址无法访问网页**」（电信/移动/联通）⇒ **海外 IPv6 一般在名单外，能过**。
- **判定手法（一行看穿站点眼中的你）**：被拦时站点自己返回的 403 页面里，JS 会吐出它看到的客户端地址 ——
  `var remote_addr = '240e:3a3:...'` ＋「您(IP：...)没有权限访问相应的资源」。**不用猜出口 IP，读这一行。**
- ⚠️ **别拿页面里出现的 `wengine-auth-failed.png` 当「被封」判据**：站点的**通用 404 页也复用同一张图**（实测抓一个 404 内页时它照样出现）⇒ 那个字符串**不是拦截标记**，grep 它会误报。判拦截只认**状态码与重定向**（被拦＝`403`；放行＝`302` 跳 `/login`）加上这行 `remote_addr`。
- **网络层 vs 应用层的分辨**：`ping6 byr.pt` 三机（本机 / NAS / 路由）全 **23~24ms、0% 丢包**（家宽电信 `240e` 与 CERNET 有直连对等），但 `curl -6 https://byr.pt/` **秒回 403**。
  ⇒ **ping 通而 403 ＝ 应用层黑名单，别再去修路由 / 换 DNS。**

### 9.2 实测：直连能到，代理到不了

只读批量测速（`GET /group/GLOBAL/delay?url=https%3A%2F%2Fbyr.pt%2F&timeout=6000`）：

- ✅ **`DIRECT` 通（40ms）** —— 家宽直连在**网络层**能到 byr.pt（被 403 挡是应用层的事）。
- ❌ **全部海外代理节点不通**（同一批节点对 `github.com` 有 42 个组全通）。⇒ 现有节点到不了 CERNET 网段。

### 9.3 直接诱因：`V6代理` 组挂的订阅集整组失效（**2026-10-07 已由修订阅解决**）

`GET /providers/proxies` 读每个节点的 `history[].delay`：

- **`二号订阅集`：170 个节点全部超时**，订阅缓存 `updatedAt` 停在多日之前 ⇒ **整组失效**。
- `一号订阅集`：71 个节点里 13 个有延迟（订阅是新的）。
- 而 **`V6代理` 组（byr.pt 唯一使用）只挂 `二号订阅集`** ⇒ BYR 走的是一条**全挂的通道**。

⚠️ **「代理下曾实测一次过」不代表现在通** —— 节点/线路会换、订阅会死。**每次失败先量订阅健康度，别直接归因站点或凭据。**

### 9.4 mihomo 只读诊断配方

> 以下是 BYR 排查用到的部分。

```bash
S=$(sudo grep -m1 "^secret:" /path/to/mihomo/mihomo/config.yaml | awk '{print $2}')
B="http://127.0.0.1:9090"
# ① 订阅/节点健康度（看 history 最后一条的 delay + vehicleType + updatedAt）
curl -s -H "Authorization: Bearer $S" "$B/providers/proxies"
# ② 整组批量连通性测试（只读；url 要 percent-encode）
curl -s -H "Authorization: Bearer $S" "$B/group/GLOBAL/delay?url=https%3A%2F%2Fbyr.pt%2F&timeout=6000"
```

- 响应外层：`/proxies` 是 `{"proxies":{...}}`、`/providers/proxies` 是 `{"providers":{...}}`。
- ★ **`/group/<组名>/delay` 才是可用的批量测速口**：一次测遍该组全部节点、可指定任意 `url`，**返回里带 emoji 的节点名正常显示**；`GLOBAL` 覆盖全部节点。
- ⚠️ **emoji 组名寻址不了，且报错极具误导性**：传 `🇭🇰 香港节点` 会回 **"all proxies timeout"**（看着像节点全挂），而同样传纯中文的 `漏网之鱼` 立刻返回真实延迟（37~148ms）。
  ⇒ **按组测速只用纯中文/ASCII 组名，或用 `GLOBAL`**；看到 "all proxies timeout" **先怀疑组名带 emoji 没寻址上**，别急着下「节点全挂」的结论。
- **`PUT` 切组不生效**（读回 `now` 不变）⇒ 别指望用 API 临时切组来测节点。

### 9.5 出口候选（按代价排序）

1. **修好 `二号订阅集`**（或换订阅源）→ 用 §9.4 ② 重测节点到 CERNET 的连通性。
2. **把 `V6代理` 组的 `use` 换成已验证能到 CERNET 的订阅集**。
3. **Cloudflare WARP —— ✅ 已实测成立（目前唯一验证过能到 CERNET 的出口）**：免费 WARP 账号 + `warpscout` 扫端点，**直连 `403` ↔ 经 WARP `302 → https://byr.pt/login`**，两个不同端点（新加坡 / 阿姆斯特丹）都复现。站点看到的源地址＝`2a09:bac1:1980:8::208:cb`（`AS13335 Cloudflare`）⇒ 落在黑名单外，符合「海外 IPv6 可过」的口径。**完整配方（warpscout 用法、mihomo `wireguard` 节点模板、必须补 `::/0` 的坑、先在 scratch 本地起 mihomo 验证再动路由器的流程）见本包 `references/warp-byr.md` 与 `scripts/warp_*.py`。**
   ⚠️ **别把路由上在跑的 `cloudflared` 当成 WARP**：实测它是一个**入站 named tunnel**（ARGO TOKEN、`region=us`、连 CF 边缘 `2606:4700:a1::8` / lax01），只负责把路由的服务暴露到公网，**不提供任何出站出口**。它唯一证明的是「路由器能稳定连上 CF 的 IPv6 边缘」。要 WARP 得另装 `warp`/`warp-cli`。
4. **Tailscale exit node**：路由上**已装 Tailscale（1.102.3）但 `Logged out`、无 exit node** —— 设备已就位，只差登录 + 一个有公网 IPv6 的海外出口，出口地址即该 exit node 的地址。
5. **自建海外 VPS（带 IPv6）**：可控性最好，但同样要先验证该机房到 CERNET 的路由。
6. **教育网跳板**：唯一不受黑名单影响的路径（源 IP 天然在放行范围内）。
7. **换国内非三大运营商出口**：广电宽带可用；移动/联通热点是 2409/2408，**同样被封，无效**。
   ⚠️ **「换家宽源地址」这条路是死的**：路由上两个全局 IPv6 前缀（`240e:3a2:aa03:a410::/60` PD + `240e:3a3:aa00:204d::/64` pppoe-wan）**都是 240e**。

★ **一切出口方案的前置判据**：从该出口 `curl -6 https://byr.pt/` 拿到 **`302` → `/login` ＝放行**；拿到 `403` ＝被拦（再读页面 JS 的 `remote_addr` 确认原因）。只看「能连上」不算。

### 9.6 排查纪律

- **`curl` 与 `ping` 矛盾时先怀疑 `curl` 本身**：NAS 上 curl 对**任何**目标都是 `HTTP=000 / time=0.000000s` 秒失败（国内站、教育网站一视同仁），而 `ping6` 正常 —— 是机上 curl 自身的问题，不是网络不通。**判「到不了 CERNET」前必须用 python `socket.connect` 交叉验证**（实测 NAS 的 IPv6 TCP 到 `byr.pt:443` 建连 **24ms**，完全正常）。
- **只读优先**：诊断全用 `GET`；改 `V6代理` 组 / 订阅 ＝ 改路由器配置，**须用户明确点头**。
- **排查后必做两件事**：① 把在 NAS `/tmp` 和本机 scratch 下产生的调试文件删干净；② 向用户**主动申报**「曾尝试 PUT 写操作但未生效」，不要只报「没改」。
- 实测 mihomo 容器 `RestartCount=0`、config.yaml mtime `2026-04-25`、所有组选择均为配置默认值（排查全程未改动）。

## 十、★ 常驻规则：BYR 登录一律自动加代理（2026-10-07 用户明确要求）

用户原话：「**以后 byr 登陆自动加代理**」。已固化为代码默认值，**跑 BYR 不需要任何额外参数**：

| 入口 | 代理怎么加 | 位置 |
|---|---|---|
| `scripts/byr_http.py`（**权威入口**） | 模块级 `PROXIES = {'http':…, 'https': 'http://127.0.0.1:7890'}`，在会话构造函数里 `s.proxies = PROXIES` | 脚本第 27 / 50 行 |
| `scripts/pt_batch_check.py` 的 BYR 条目 | 站点字典加 `proxy=os.environ.get('BYR_PROXY', 'http://127.0.0.1:7890')`，launch 时转成 `Camoufox(proxy={'server': …})` | SITES 表 + 启动处 |

- 覆盖地址：`BYR_PROXY=http://其它:端口` 环境变量；不设就用 NAS mihomo。
- ⚠ **Camoufox 带 proxy 会报 `LeakWarning: … heavily recommended that you pass geoip=True`，但不要加 `geoip=True`**（本机 venv 没装 `camoufox[geoip]`，会抛 `NotInstalledGeoIPExtra` 启动失败）。这条警告可以忽略。
- ★ **巡检器里的 BYR 恒报「❌ 未登录」是正常的，不要据此判掉线**：BYR 的登录 cookie **不持久化**（「保持登录」不跨会话，见 §二），而 `byr_http.py` 用的是自己的 cookie jar、不是浏览器档案 ⇒ 浏览器档案永远是未登录态。**BYR 的权威判据只有 `byr_http.py --stage2`**（回「欢迎, PTUSER」才算）。
- ★ **顺带修掉一个假阳性**：巡检器旧版把 BYR 的 **403 拦截图**误判成「✅ 已登录」（403 页既无登录表单也无「未登录」字样，旧判据全过）。现已在 `pt_batch_check.py` 里加 `http_403 = (resp.status == 403)` 分支，报「⚠ HTTP 403 被源 IP 黑名单拦（此站必须走代理）」，且不进入 `logged`。**以后看到巡检器报某站 403，先想代理，别当登录态。**
- 例行收口时 BYR 记 `ok`、note 写「登录保活完成（自动走代理）」；无签到可做（见 §三）。
