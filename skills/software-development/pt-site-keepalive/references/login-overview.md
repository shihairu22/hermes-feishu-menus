---
name: pt-site-login-overview
description: "PT 站点登录方式总览（29 站）：登录机制分类、人工介入点、风险等级与通用经验。已去敏，可外发。"
version: 1.0.0
metadata:
  hermes:
    tags: [pt-site, login, keepalive, overview]
---

# PT 站点登录方式总览（29 站）

> **本文已去除敏感信息**：不含账号名、密码、邮箱、内网地址、令牌、会话路径与账号数值。
> 仅保留「机制 / 做法 / 风险」，可直接分享。
>
> 例行触发词：说「**签到pt**」= 依次串行走完全部 29 站，不反问是哪个站。
> 全部站点使用同一套账号，凭据从本机受限权限的凭据文件读取，不在聊天中索取或复述。

## 一、总览

- **站点数**：29
- **有签到的站**：21 个
- **无签到、只做登录保活**：8 个（M-Team、KEEPFRDS、天雪、MonikaDesign、朱雀、TorrentLeech、葡萄 PT、BYRBT）
- **登录方式**：纯脚本 8 站 / 需真实浏览器 21 站 / 需特殊网络 4 站 / 需人工介入 5 站（有重叠）

## 二、按登录方式分类

### A. 纯脚本即可（urllib / curl，不开浏览器）—— 8 站

| 站点 | 关键点 |
|---|---|
| SunnyPT `sunnypt.top` | 无验证码；两步 API：登录 → 取 `accessToken` → 作为 Bearer 调 API 子域 |
| 海棠PT `www.htpt.cc` | 图形验证码；⚠️ 提交**不能带** `securelogin` 字段 |
| 冬樱 `wintersakura.net` | 标准 NexusPHP，明文 POST，无 CF |
| DiscFan `discfan.net` | challenge-response（HMAC 算法已在脚本内对齐）+ 图形验证码 |
| 葡萄 PT `pt.sjtu.edu.cn` | 极简表单 + 固定令牌，无验证码、无加密、无 CF |
| PANDA `pandapt.net` | NexusPHP + 纯黑文字验证码 |
| HDFans `hdfans.org` | 同上（与 PANDA 同款） |
| TorrentLeech `torrentleech.org` | 全站最简单：只需用户名 + 密码，无验证码 / 无 2FA / 无 CF |

### B. 必须真实浏览器（Camoufox 反检测浏览器）—— 21 站

- **因 Cloudflare / WAF**：Audiences、PigGo（SafeLine）、UBits、HDDolby、PTHOME、织梦
- **因验证码/会话绑定**（不是前端加密——页面里那段 bcrypt 在 HTML 注释内、是死代码）：HDU（验证码与 imagehash/会话绑定 + 强制 cookie，裸请求必失败）
- **因 challenge-response 且服务端会挂住裸请求**：大青虫
- **因 SPA / 反爬令牌 / 指纹校验**：M-Team、OurBits、PT@KEEPFRDS、HDSky、CHDBits、TTG、HDHome、OpenCD、U2、天雪、MonikaDesign、朱雀、BYRBT

### C. 需要特殊网络 —— 4 站

- **BYRBT** `byr.pt`：**两头都不通**（直连 403 = 源 IP 黑名单；NAS 代理 `000` = 节点无 IPv6 出口）——2026-10-06 起**搁置待用户决策**
- **U2** / **MonikaDesign** / **TorrentLeech**：DNS 被污染，需 hosts 指定真实 IP

### D. 需要人工介入（脚本停下来要验证码）—— 5 站

| 站点 | 需要什么 |
|---|---|
| PigGo `piggo.me` | 2FA 动态码 |
| HDDolby `hddolby.com` | 强制两步验证码 |
| U2 `u2.dmhy.org` | 强制 2FA（且是独立账号体系） |
| 朱雀 `zhuque.in` | 邮箱二步验证（**8 位十六进制**，不是纯数字） |
| M-Team `kp.m-team.cc` | 首次登录的邮箱验证码（有持久会话后通常不再要） |

## 三、风险等级（尝试次数有限的站，绝不盲试）

- 🔴 **极低**：TTG（6 次，失败即封 IP）、UBits（6 次）、天雪（5 次）
- 🟠 **低**：HDSky（连错 10 次封 IP）、DiscFan / 大青虫 / 织梦 / 海棠PT / U2（各 10 次）
- 🟡 **中**：HDDolby（20 次）、HDHome（20 次）

**核心判据**：失败提示里的 `你还有 N 次尝试机会` ——
**N 不变 = 验证码层被拒（重取图重试是安全的）；N 减 1 = 已到凭据层（立即停手，找用户确认）。**
注意：**次数按 IP / 会话计，不按账号** —— 用户在自己设备上看到的余额与本机出口的余额可以不同。

## 四、例行里具体做什么

- **有签到的 21 站**：登录 + 签到。多数 NexusPHP 站是 `GET /attendance.php` **打开即自动签**；少数在首页用户栏按钮或独立插件页。
- **无签到的 8 站**：只做**登录保活**（登录一次即刷新 Last visit，防止长期不登录被清号）。其中天雪额外模拟下载 1~3 个字幕附件；BYRBT 的每日玩法是「趣味盒」投票（+10 魔力值，需弹窗操作）。

## 五、通用经验（实战踩出来的）

1. **验证码必须双路识图**：视觉模型 + 自读 ASCII 点阵，两者一致才提交；不一致时裁剪放大单独判定。
   NexusPHP 的验证码字符集**不使用 `0`/`O`/`1`/`I`**（防混淆）→ 遇到圆环优先读 **D**。
2. **登录表单里的复选框一律不勾、也不在提交数据里带**（尤其「**限制只能使用本IP登录**」/ `securelogin`，以及 `ssl` / `trackerssl` / `logout`）。
   多带一个 `securelogin=yes`，服务器会回「用户名或密码不正确！或者你还没有通过验证」——极易误判成账号问题。
3. **提交前先抓一次浏览器实际发出的表单体做对照** —— 这是定位登录问题最快的手段。
4. **「用户名或密码不正确」这句话同时涵盖三种情况**：用户名错、密码错、**多带了字段**。不能只怀疑密码。
5. **区分「验证码错」还是「凭据错」看尝试次数**（见第三节判据）。
6. **抓包诊断可零消耗**：故意填一个**错的验证码**提交（验证码错通常不扣次数），即可抓到真实 POST 内容，判断字段是否齐全、前端算法是否已算好。
7. **环境指纹先自检**：`navigator.webdriver` 应为 `false`、WebGL 渲染器应是真实 GPU 字符串。环境不干净时，换多少种点击方式都是白费。
8. **不要用统一的「退出 / 欢迎回来」文本判定登录态**：各站用户栏不一样，最硬的判据是**认证 cookie 是否存在**。
9. **签到结果按「硬 → 软」判**：① 签到记录页出现当天日期（最硬）→ ② 用户栏标记变化 → ③ 积分增量 → ④ 接口返回的状态字段（**不可单独作准**，有站点实测返回 `false` 而实际已签到成功）。
10. **登录成功会重置失败计数**，所以一次成功即可恢复额度。

## 六、站点清单（29 站）

| # | 站点 | 域名 | 登录 | 签到 |
|---|---|---|---|---|
| 1 | M-Team | `kp.m-team.cc` | 浏览器 | ❌ 保活 |
| 2 | Audiences | `audiences.me` | 浏览器 | ✅ |
| 3 | OurBits | `ourbits.club` | 浏览器 | ✅ |
| 4 | PT@KEEPFRDS | `pt.keepfrds.com` | 浏览器 | ❌ 保活 |
| 5 | HDSky | `hdsky.me` | 浏览器 | ✅ |
| 6 | PigGo | `piggo.me` | 浏览器 + 2FA | ✅ |
| 7 | CHDBits | `ptchdbits.co` | 浏览器 | ✅ |
| 8 | UBits | `ubits.club` | 浏览器 + Turnstile | ✅ |
| 9 | HDDolby | `hddolby.com` | 浏览器 + 2FA | ✅ |
| 10 | TTG | `totheglory.im` | 浏览器 | ✅ |
| 11 | HDHome | `hdhome.org` | 浏览器 | ✅ |
| 12 | OpenCD | `www.open.cd` | 浏览器 | ✅ |
| 13 | U2 | `u2.dmhy.org` | 浏览器 + 2FA | ✅（图像题）|
| 14 | 天雪 | `www.skyey2.com` | 浏览器 | ❌ 保活 |
| 15 | MonikaDesign | `monikadesign.uk` | 浏览器 | ❌ 保活 |
| 16 | PTHOME | `www.pthome.net` | 浏览器 | ✅ |
| 17 | 朱雀 | `zhuque.in` | 浏览器/API + 邮箱码 | ❌ 游戏化 |
| 18 | TorrentLeech | `torrentleech.org` | **纯脚本** | ❌ 保活 |
| 19 | HDFans | `hdfans.org` | **纯脚本** | ✅ |
| 20 | HDU | `pt.hdupt.com` | 浏览器 | ✅（按钮）|
| 21 | PANDA | `pandapt.net` | **纯脚本** | ✅ |
| 22 | 葡萄 PT | `pt.sjtu.edu.cn` | **纯脚本** | ❌ 保活 |
| 23 | 大青虫 | `cyanbug.net` | 浏览器 | ✅ |
| 24 | DiscFan | `discfan.net` | **纯脚本** | ✅ |
| 25 | 冬樱 | `wintersakura.net` | **纯脚本** | ✅ |
| 26 | 织梦 | `zmpt.cc` | 浏览器 | ✅ |
| 27 | BYRBT | `byr.pt` | 浏览器 + 代理 | ❌ 保活 |
| 28 | 海棠PT | `www.htpt.cc` | **纯脚本** | ✅ |
| 29 | SunnyPT | `sunnypt.top` | **纯脚本** | ✅ |

> 另有一个**账号独立、不计入例行**的论坛站（CnLang 国语视界 `cnlang.org`，Discuz 论坛，登录可自动化、签到被路径级规则封锁需手动）。

## 七、维护约定

- 新站接入前先做**零风险探测**：查 Cloudflare / 图形验证码 / 前端 JS 加密 / challenge-response，再决定用纯脚本还是浏览器，避免浪费登录尝试次数。
- 接入后**同时更新**本文件与技能正文的清单编号，两处必须一致。
- 例行运行**串行、不并发**，避免触发风控。
