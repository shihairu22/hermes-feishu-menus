# 29 站架构差异研究（2026-09-27）

> 方法：只读 GET 各站登录页，分析框架指纹 / 响应头 / Set-Cookie 名 / 前端栈 / 防护机制。
> 脚本：`scripts/scan_architecture.py`；原始数据 `~/safeline-research/site_architecture.json`

## 一、框架谱系（7 族）

| 框架 | 站数 | 站点 |
|---|---|---|
| NexusPHP | 7 | HDSky、CHDBits、HDHome、HDFans、大青虫、DiscFan、冬樱 |
| NexusPHP 分支 | 3 | HDU、PANDA、海棠PT |
| Discuz! | 1 | 天雪 |
| UNIT3D (Laravel) | 1 | MonikaDesign |
| TNode（Vue SPA） | 1 | 朱雀 |
| Nexus Project（教育网） | 1 | SJTU 葡萄 |
| 自研 / 被 CF 遮蔽 | 15 | M-Team（React 自研）、SunnyPT（Next.js）等 |

## 二、后端栈指纹（靠 Session Cookie 名反推）

**`Server` 响应头基本无用** —— 26/28 站显示 `cloudflare`，真后端被隐藏。
可靠的做法是看 Set-Cookie 的会话名：

| Cookie 名 | 后端 | 站点 |
|---|---|---|
| `PHPSESSID` | PHP | KEEPFRDS、U2、TorrentLeech |
| `SITE_TOTAL_ID` | NexusPHP | 冬樱 |
| `rkvl_2132_sid` | Discuz | 天雪 |
| `monikadesign_session` | Laravel | MonikaDesign |
| `socute` | Node/express-session | 朱雀 |
| `AuthSession` | Next.js | SunnyPT |

## 三、前端栈

- **jQuery** 12 站（全部 NexusPHP 系）
- **Bootstrap** 3 站（KEEPFRDS、TTG、OpenCD）
- **crypto-js** 2 站（大青虫、DiscFan）—— challenge-response 的标志
- **Ant Design** 1 站（朱雀）
- **Next.js + React** 1 站（SunnyPT）

## 四、防护机制全景

| 机制 | 站数 | 站点 |
|---|---|---|
| Cloudflare | 8 | Audiences、OurBits、PigGo、UBits、HDDolby、TTG、PTHOME、织梦 |
| Cloudflare Turnstile | 1 | KEEPFRDS |
| Discuz `skfaid` 令牌 | 1 | 天雪 |
| 前端 bcrypt | 1 | HDU |
| challenge-response | 2 | 大青虫、DiscFan |
| 无明显防护 | 15 | 其余 |

## 五、跨站洞察（同族站会共享坑）

1. **NexusPHP 系（10 站）共享同一套登录/签到结构** —— `login.php` + `takelogin.php` +
   `attendance.php`；字段 `username`/`password`/`imagestring`/`imagehash`；
   **验证码读法、`securelogin` 铁律、尝试次数判据全部通用**。
2. **大青虫与 DiscFan 同源**（都引 `crypto-js.js` + `challenge`）——
   DiscFan 的 hmac 参数顺序坑（`hmacSha256(key,message)` 封装）**很可能同样适用于大青虫**。
3. **UNIT3D 系（MonikaDesign）用 Laravel 标准 CSRF**（`csrf-token` meta）——
   将来接入其它 UNIT3D 站可直接套用。
4. **TNode 系（朱雀）的 `x-csrf-token` 必须带**（见 `references/zhuque.md`）。

## 六、值得深挖的清单（按性价比）

| 优先级 | 目标 | 理由 | 预估 |
|---|---|---|---|
| 🔴 高 | M-Team 自研 API | 唯一自研 React 站，玩法多；无签到 → 活跃机制可能在别处 | 2h |
| 🔴 高 | 15 个「被 CF 遮蔽」站的真实框架 | 浏览器过 CF 后读 cookie 名即可识别；可能发现可纯脚本化的站 | 1h |
| 🟠 中 | HDU 的 bcrypt 细节（盐值/轮数） | 搞懂了可摆脱浏览器 | 1h |
| 🟠 中 | 大青虫的 challenge 算法 | 与 DiscFan 同源，可能已被现有算法覆盖 | 1.5h |
| 🟡 低 | SunnyPT 的 JWT 刷新机制 | 自动续期可省掉重登 | 1h |
| 🟡 低 | 朱雀角色升级策略 | 116 角色，纯策略优化 | 1h |


---

## 七、浏览器过 CF 后的真实框架（2026-09-27 补充，12 站实测）

之前靠纯 HTTP 只能识别 6 站，其余被 CF 遮蔽。用**已登录的浏览器档案**过 CF 后读到真身：

| 站点 | 框架 | 关键 Cookie |
|---|---|---|
| Audiences | NexusPHP | `c_secure_login/pass/ssl/tracker_ssl/uid` |
| OurBits | NexusPHP | **`ourbits_jwt`** ← 用 JWT 认证 |
| KEEPFRDS | NexusPHP | `PHPSESSID` + `c_secure_*` |
| PigGo | NexusPHP | `sl-challenge-jwt`、`sl-session`、`sl_jwt_session` ← **SafeLine** |
| UBits | NexusPHP | `nexus_csrf_token`、`sl-session` ← **也有 SafeLine** |
| HDDolby | NexusPHP | `c_secure_*` |
| PTHOME | NexusPHP | `c_secure_*` |
| 织梦 | NexusPHP | `c_secure_pass` |
| U2 | NexusPHP 分支 | `__cf_bm` |
| OpenCD | NexusPHP（cookie 证据） | `c_lang_folder` + `c_secure_*` |
| TTG | **自研** | `laccess`、`pass`、`uid`、`user_info_hash` |

### ★ 核心结论：20/28 站是 NexusPHP 系（71%）

- **NexusPHP 正统 16 站**：Audiences、OurBits、KEEPFRDS、PigGo、UBits、HDDolby、PTHOME、
  织梦、OpenCD、HDSky、CHDBits、HDHome、HDFans、大青虫、DiscFan、冬樱
- **NexusPHP 分支 4 站**：HDU、PANDA、海棠PT、U2
- → **攻克一站 = 攻克二十站**：`login.php` / `takelogin.php` / `attendance.php` 结构、
  `username`+`password`+`imagestring`+`imagehash` 字段、验证码读法、`securelogin` 铁律、次数判据 **全部通用**。

### 异类清单（要单独对待）

1. **OurBits** —— NexusPHP 但认证换成 JWT（`ourbits_jwt`），不是经典 `c_secure_*`。
2. **PigGo / UBits** —— 都装了 **SafeLine 雷池**（`sl-*` cookie 为证）；
   之前只知道 PigGo 有，UBits 是这次新发现。UBits 的登录页同时有 `nexus_csrf_token`。
3. **TTG** —— 完全自研，cookie 为 `laccess`/`pass`/`uid`/`user_info_hash`；且登录次数只有 6 次。
4. **M-Team** —— Java/Spring Boot REST API（`api.m-team.cc`）+ React SPA（webpack，
   JS 动态注入到 `static.m-team.cc`），见下节。

## 八、M-Team 深度（官方 wiki 证实）

站点有**官方 API 文档**：`https://wiki.m-team.cc/api`（「API 介接功能」）

**架构**：
- 前端：React SPA（webpack 打包，`main.<hash>.js` + 4 个 `vendors`，托管在 `static.m-team.cc`）
- 后端：**Java / Spring Boot**（`api.m-team.cc` 返回 Spring Security 标准 401 JSON）
- 前端会**测速多个 API 主机并自动选最快的**（`localStorage.apiHost`）
- 认证信息存 `localStorage.auth`；另有 `did`（设备 ID）、`visitorId`（指纹）
- 客户端定时轮询：`lastCheckTime`、`user.setLastUpdate`、`user.setLastCheck4news`、
  `user.setMsgStatic`、`user.setPeerCount` → 说明「活跃度」来自访问+轮询
- 内嵌 Turnstile sitekey：`m-team.cc` → `0x4AAAAAAAGmQlZPus1Y93sD`

### ⚠️ 官方对第三方工具的硬性要求（务必遵守）

> 「API KEY 开放后，若发现第三方工具仍以 **cookie** 存取接口，**不排除停用账号**。」

- 正确方式：**API Access Token**，在请求头用 **`x-api-key`** 传递
- 获取位置：**【控制台 → 实验室 → 存取令牌】**
- 官方 Swagger：`https://test2.m-team.cc/api/swagger-ui.html`（需测试站账号）

**允许第三方调用的端点**：
`/member/profile`、`/member/base`、`/member/bases`、`/member/sysRoleList`、
`/member/getUserTorrentList`、`/member/getCrimeRecords`、`/member/queryUserLoginHistory`、
`/msg/statistic`、`/msg/notify/statistic`

**禁止**：`/admin/**`、`/login`、`/apikey/**`

**速率建议**：下载种子 1000/天；下载行为 100/小时；`/torrent/detail` 100/小时；
`/torrent/search` 1000/24 小时。

> **行动项（已否决）**：原拟 M-Team 保活改 `x-api-key` 调 `/member/profile`；按用户 2026-09-28 决定**维持浏览器 cookie 登录**，本行动项不再执行。


---

## 九、深挖清单执行结果（2026-09-28）

### #3 HDU 的「bcrypt」—— 是误判，实为注释掉的死代码

登录页里只有 1 处 `bcrypt`，位于 **HTML 注释**内：

```php
<!-- $options = [ 'cost' => 10, 'salt' => "weloveupxinweloveupxinweloveupxin", ];
     $a = date("Y-m-d H", time()); $b = $a;
     $tempkey = password_hash($b, PASSWORD_BCRYPT, $options); ?>
     <script> function password() { prompt('站点维护中，请输入临时密钥登录', ''); } </script> -->
```

- 这是**站点维护期的临时密钥登录**（按小时生成），已被注释停用。
- 盐值硬编码在页面源码里 → 理论上可推算当小时临时密钥。**属站点运维功能，不去使用。**
- **结论修正**：HDU 登录就是**标准 NexusPHP 明文 POST**（`takelogin.php`），
  之前技能里「HDU 裸请求发明文密码必失败」的判断**不成立**，真实拦路的是**图形验证码**。
- 表单字段：`username` / `password` / `imagestring` / `imagehash` / `logout` / `securelogin` / `ssl` / `trackerssl`。

### #4 大青虫 challenge 算法 —— 与 DiscFan 完全同源，可脱离浏览器

从登录页内联脚本读出的**完整算法**：

```js
1. POST /api/challenge  {"username": "<user>"}
   → {"ret":0, "data":{"secret":"...", "challenge":"..."}}
2. clientHashedPassword = sha256(password)
3. serverSideHash        = sha256(secret + clientHashedPassword)
4. response              = hmacSha256(key=challenge, message=serverSideHash)
5. 提交 username + secret + response (+ two_step_code)
```

- 与 `scripts/discfan_login.py` 里已实现的算法**逐行一致**（含 `hmacSha256(key,message)` 参数顺序坑）。
- 大青虫表单字段：`secret`(hidden ×2) / `username` / `password` / `two_step_code` /
  `logout` / `securelogin` / `ssl` / `trackerssl`；提交按钮是 `type=button`（JS 驱动）。
- JS：`crypto-js.js` + `passkey.js`（WebAuthn，与登录无关）+ `nexus.js`。
- **行动项**：大青虫可复用 DiscFan 脚本（改 BASE 域名），**从浏览器方案降级为纯 Python**。

### #5 SunnyPT JWT 续期 —— 已实现并实测

- 登录下发两个 cookie：`AuthSession`(path=/) + **`AuthRefresh`(path=/api/auth/session)**。
- `accessToken`（236 位 JWT）过期后，只要 `AuthRefresh` 有效，
  **重新 GET `/api/auth/session`** 即可换新 token，**无需重新提交账号密码**。
- **已改** `scripts/sunnypt_login.py`：cookie 持久化到
  `~/.pt-sessions/state/sunnypt_cookies.txt`，启动时先试续期，失败才完整登录。
- 实测：第 1 次走登录并保存 cookie；第 2 次输出「★ 续期成功（236 位）」✓。

### #6 朱雀角色升级策略

数据（`~/safeline-research/zhuque_chars.json`，116 角色）：

- 已升级 **100 个，全部 lv=79**；每个 `cost=1,022,028`、`profit≈3,800,000`、**ROI≈3.7**。
- 未升级 **16 个**（lv=None）→ 释放得 **0 灵石**，而它们恰是「唯一总能释放」的一批。
- 总投入 76,869,142 / 总产出 245,345,225 / 平均 ROI 3.21。
- **结论**：升级一个未升级角色的边际成本 ≈ 1,022,028，长期产出 ≈ 3,800,000（ROI 3.7），
  16 个全升需 ≈ 1,640 万灵石、长期回报 ≈ 6,080 万。
  **属要花用户资产的操作 → 必须先经用户同意，不擅自执行。**

## 十、M-Team 官方 API 方案（待用户授权执行）

- 官方要求第三方工具用 `x-api-key`（见第八章），获取位置【控制台 → 实验室 → 存取令牌】。
- 改造方案：`GET https://api.m-team.cc/api/member/profile` + `x-api-key` 头，
  替代现在的浏览器 cookie 登录，规避官方明示的停号风险。
- **需用户授权**：要在他账号上生成/读取令牌（不落入聊天、直接写本机凭据文件）。
