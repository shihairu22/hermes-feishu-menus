# 各站自动化能力速查表（2026-09-28）

> 用途：回答「这个站到底能不能脚本化、用什么方式跑」。
> 数据来源：例行实测 + `apis/*.json` 流量扫描 + 各站 wiki 规则。

## 一、四种自动化档位

| 档位 | 含义 | 优点 | 风险 |
|---|---|---|---|
| **A 纯 HTTP** | urllib/requests 即可，无 JS 挑战 | 快、稳、资源占用低 | 需要自己处理验证码 |
| **B 必须浏览器** | Cloudflare 挑战 / JS 加密 / challenge-response | 能过绝大多数防护 | 慢（每站 30s~数分钟） |
| **C 半脚本（有 REST API）** | 站点有真接口，但仍需 JWT/cookie | 最干净，可精确调用 | 需维护令牌；注意站点对第三方工具的态度 |
| **D 会话恢复** | 不重登，直接复用已验证的浏览器档案 | 绕过验证码/2FA，100% 可靠 | 档案必须持久化在磁盘 |

## 二、29 站逐站清单

| 站点 | 档位 | 登录方式 | 签到方式 | 特殊限制 |
|---|---|---|---|---|
| **M-Team** | C+B | 浏览器（React 新版）+ 邮箱码 | **无签到** | 40 天不登录删号；官方禁第三方 cookie 调接口 |
| **Audiences** | B | 浏览器 + 图形验证码 | attendance.php | 单种上传 >125MB/s 自动封禁 |
| **OurBits** | B | 浏览器 + 图形验证码 | attendance.php | 下载 >100G 且分享率 <0.3 直接封号 |
| **KEEPFRDS** | B | 浏览器 | attendance.php | **35 天不登录就封号（全站最短）** |
| **HDSky** | B | 浏览器 + 图形验证码 | attendance.php | 恶意限速直接禁号；认领已关闭 |
| **PigGo** | B | 浏览器 + **2FA 动态码** | attendance.php | 分享率 <0.1 立即禁用；SafeLine 防护 |
| **CHDBits** | B | 浏览器 | **bakatest.php 答题** | 答题答错扣 1 魔力；HP 点数制 |
| **UBits** | B | 浏览器 + **Turnstile** | attendance.php | 仅剩 6 次尝试；也装了 SafeLine |
| **HDDolby** | B | 浏览器 + 图形码 + **2FA** | attendance.php | 下载 >100G 且分享率 <0.2 不受理申诉 |
| **TTG** | B | 浏览器（**仅 6 次机会**） | signed.php（AJAX） | 失败封 IP；单种限速 100MB/s |
| **HDHome** | B | 浏览器 | attendance.php | 下载 >200G 且分享率 <0.2 系统封禁 |
| **OpenCD** | B | 浏览器 + 图形码 | plugin_sign-in.php | 登录和签到**都要验证码** |
| **U2** | B | 浏览器 + 图形码 + **2FA** | 找圆点图像题 | DNS 污染需 hosts；**用会话恢复绕过** |
| **天雪** | B | 浏览器（Discuz） | **无签到** → 模拟下载字幕 | 仅 5 次尝试 |
| **MonikaDesign** | B+C | 浏览器（UNIT3D） | **无签到** | DNS 易污染；有 7 个 `/api/chat/*` |
| **PTHOME** | B | 浏览器 + 图形码 | attendance.php | CF JS 挑战，curl 403 |
| **朱雀** | C | **API + 邮箱码**（8 位 hex） | **无签到** → 游戏化 | 全部 API 必带 `x-csrf-token` |
| **TL** | A | urllib（**只要账密**） | **无签到** | DNS 需 hosts；站规禁账号共享 |
| **HDFans** | A | **urllib** + 图形码 | attendance.php | 绝不带 `securelogin` |
| **HDU** | B | 浏览器 + 图形码 | 首页 `[签到]` 按钮 | 无 attendance.php；无 CF |
| **PANDA** | A | **urllib** + 图形码 | attendance.php | 单种限速 100MB/s（盒子备案不可豁免） |
| **SJTU 葡萄** | A | **urllib**（固定令牌） | **无签到** | 15 分钟不活动登出 |
| **大青虫** | B | 浏览器（challenge-response） | attendance.php | 仅 10 次；纯脚本 POST 被 tarpit |
| **DiscFan** | A | **urllib**（challenge-response） | attendance.php | 10 次；验证码错不扣次数 |
| **冬樱** | A | **urllib** 明文 POST | attendance.php | 45 天不登录禁用 |
| **织梦** | B | 浏览器（CF 挑战） | attendance.php | 登录本身极简（无验证码） |
| **BYR** | A+B | 浏览器 + **NAS 代理** | **无签到** → 趣味盒投票 | 教育网，本机直连 403；2026-10-07 起恢复（走代理） |
| **SunnyPT** | C+A | **API**（NextAuth） | `/api/v1/attendance/check-in` | 优先续期（cookie 持久化） |
| **CnLang** | B+HTTP | 浏览器登录（Discuz，30 天会话） | ✅ **已自动化**：`%64su_paulsign` 编码绕 CF，纯 curl 可签 | 路径规则须走编码形式；脚本 `cnlang_sign_http.py` |

## 三、按档位汇总

**A 纯 HTTP（7 站）**：TL · HDFans · PANDA · SJTU · DiscFan · 冬樱 ·（BYR 需代理）
**B 必须浏览器（18 站）**：M-Team · Audiences · OurBits · KEEPFRDS · HDSky · PigGo ·
CHDBits · UBits · HDDolby · TTG · HDHome · OpenCD · U2 · 天雪 · MonikaDesign · PTHOME ·
HDU · 大青虫 · 织梦 · CnLang
**C 有 REST API（5 站）**：朱雀（33 个）· M-Team（POST + JWT）· MonikaDesign（7 个 chat）·
SunnyPT（14 个）· OurBits（辅助域 `api.ourhelp.club`）
**D 会话恢复**：U2（必用）· SunnyPT（续期）· 其余站可选加速

## 四、可自动化的「额外收益点」（合规范围内）

| 站点 | 额外动作 | 当前状态 |
|---|---|---|
| 朱雀 | 释放角色技能（每 8 小时）· 抽卡 · 升级 · 绑定 | cron 已建（用户暂停中） |
| 朱雀 | 种子认领 `/api/torrent/claimAllSeeding` | **用户已否决** ✗ |
| CHDBits | 答题签到（已授权助手自答） | 例行内 ✓ |
| BYR | 趣味盒投票（+10 魔力） | 例行内 ✓ |
| M-Team | 收藏卡（挂种自动掉卡） | 被动获得，无需操作 ✓ |
| UBits | U币商城换上传量 | **用户暂缓** ✗ |
| 其余 22 站 | **无额外收益玩法**（赌博类一律不参与 ✗） | — |

## 五、红线（任何档位都不能碰）

1. **禁止通过代理连 tracker**（M-Team 明文；VPN/机场/GCP/AWS/Azure 同禁）
2. **DHT / PEX / LPD 必须关闭**（HDSky、TL 明文）
3. **不要用 cookie/API KEY 直接刷接口**（M-Team 官方明文警告可能停号）；
   正式自动化走官方 `x-api-key`
4. 单种上传限速：Audiences 125MB/s · PANDA/PTHOME/HDDolby/TTG/织梦 100MB/s
5. 恶意限速（做种速度过低）同样封号：M-Team 月15天 <10KB/s · HDSky <250KB/s
6. 分享率警戒：PigGo <0.1 立即禁 · OurBits <0.3 · HDDolby/HDHome/PTHOME <0.2

## 六、纯脚本化再评估（2026-09-30 只读复扫结论）

> 方法：`scripts/scan_all_login_pages.py` 复扫全部 29 站 + 针对性只读探针（不带凭据、不提交表单）。
> 目标：找出「浏览器档」里还能改纯 HTTP 脚本的站。

**可直接转纯脚本（表单洁净，无 CF/Turnstile/SafeLine 墙）—— 5 站**：

| 站 | 实锤依据 | 转法要点 |
|---|---|---|
| **HDHome** | 无验证码、无 CF；表单 username/password/scode → `takelogin.php` | 登录 POST 1 次 + `GET attendance.php` 即自动签 |
| **MonikaDesign** | 无验证码、无 CF；Laravel `_token` + meta csrf-token | `POST /login`（username/password/remember）；仅登录保活 |
| **U2** | 旧版入口 **`portalbc.php`**（划重点：专为无 JS 设备）；验证码 `captcha.php?sid=` 直抓（108×40 PNG，与现有净化器同规格）；登录/签到字段早已全扒清 | requests 会话：登录（码+2FA）+ `showup.php` 圆点题（本地绿点扫描已有脚本） |
| **OpenCD** | 无 CF；登录与签到验证码均为「纯黑文字+彩色噪点」，颜色分离读法已实测 | `takelogin.php` / `plugin_sign-in.php?cmd=signin` + `?cmd=show-log` 复核 |
| **CHDBits** | 无 CF；登录验证码 + `bakatest.php` 答题表单 | 答题的「逐 radio 读文案精确匹配」逻辑照搬到 HTTP 解析 |

**有门槛候选 —— 5 站：2026-09-30 逐站实测，4 站转成、1 站维持浏览器**：

- **HDSky** ✅ **已转纯 HTTP**（`scripts/hdsky_http.py`）：登录验证码「净化放大 → 双路识读」一次过（实测 `19G172` 被接受，分享率 1.569；[已签到] 状态识别正常）。纪律保留：登录码仍走双路一致才提交；签到弹层端点 2026-10-02 已抓取打通（`image_code_ajax.php {action:new}`→`image.php?action=regimage&imagehash=`→`showup.php {action:showup,imagehash,imagestring}`），双读一致一次过（历史签到码视觉判错两次的纪律继续沿用，双读一致才提交）。
- **BYRBT** ✅ **已转纯 HTTP**（`scripts/byr_http.py`，固定走 NAS 代理）：SPA 逆向得 `POST /api/v2/login.php`，JSON `{type:"username",username,password,remember}`；响应信封 `{success,code,msg,data.auth_token}`；实测「登录成功」+ `index.php` 复核「欢迎, PTUSER · Extreme User · 分享率 8,111.15」**2026-10-07 已恢复（走 NAS 代理）；10-10、10-11 例行登录均通过。**
- **TTG** ❌ **维持浏览器**：GET 登录页放行（CF 仅被动 jsd），但 **POST `takelogin.php` 被 CF 拦截**（无会话产生、未消耗登录次数）。6 次额度不值得反复试探；`ttg_http.py` 保留（勘察/签到 token 解析可复用），登录继续 Camoufox。
- **天雪** ✅ **已转纯 HTTP**（`scripts/skyey_http.py` + `scripts/skyey_fp.js`）：`skfaid.js` 实为 **FingerprintJS Pro v3.3.0**——Node 里桩好浏览器全局直接跑官方 JS 现算 64 位 hex 令牌，实测被接受（`rkvl_2132_auth` 就位、用户组 Lv.5）；「字幕附件模拟下载」保活同步 HTTP 化（实测 11307 字节）。
- **HDU** ✅ **已转纯 HTTP**（`scripts/hdu_http.py`）：历史「curl 登不上」根因 = 未保持 cookie 会话；urllib+LWPCookieJar 一次过（验证码双路读 `7765G4` 被接受；分享率 13.251）。签到端点已挖出：`POST added.php`（body `action=qiandao`，出自 `common.js` 的 `qiandao()`）。

**确认维持浏览器（10 站）**：M-Team（红线不用官方 API）· Audiences / OurBits / PigGo / UBits / HDDolby / PTHOME / 织梦（**CF 403 实墙**，复扫再次确认）· KEEPFRDS（Turnstile）· 大青虫（challenge-response 可解但服务端 tarpit 非浏览器 POST，本次复扫 51s 实测）。

**换纯脚本的收益**：每站 10~60s（Xvfb+浏览器冷启动）→ 1~5s；不吃内存盘；消掉 JS click 超时等历史坑。**落地纪律**：每站转换后先跑一次真实登录实测（成功登录不消耗失败次数），再更新本表与技能正文。

**最终落地进度（2026-09-30 夜）**：**10 站计划全部有结论——9 站转成纯 HTTP、1 站（TTG）维持浏览器**。已实测「空 jar 冷启动登录、一次过」：`hdhome_http.py` / `monika_http.py` / `opencd_http.py` / `chdbits_http.py` / `u2_http.py`（验证码+2FA 双值流程）/ `hdu_http.py` / `hdsky_http.py` / `skyey_http.py` / `byr_http.py`；天雪保活段（附件下载）也已实测。**待未签日 / 人工环节补测的段**：~~OpenCD 签到段、CHDBits 答题段、U2 圆点题、HDSky 签到弹层端点~~ **2026-10-02 全部补测通过 ✓**（OpenCD +10 / CHDBits 水星计划 +358 / U2 一次过 / HDSky +10）；顺手修复：CHDBits 单引号属性解析、HDU `--stage4` 接线。至此 HTTP 版全链路无待办。**2026-10-02 例行实测：29/29（23:29–23:51，约 22 分钟），全程零人工环节；HDSky 新端点、CHDBits 修复后答题、U2 圆点题、PigGo 慢流程均一次过。**所有转换零失败次数消耗。

**2026-09-30 收尾清理**：转换后淘汰的浏览器脚本（hdhome_login / hdhome_signin / monika_login / opencd_login / opencd_do_signin / chdbits_baka / u2_login / u2_showup_signin / hdu_login / skyey_login / skyey_keepalive / byr_login / ttg_probe）已从 `scripts/` 清理（12 个移入 `_research/_superseded/`；`u2_showup_signin` 与既有归档逐字节重复、就地去重）；venv 迁至 `~/.pt-sessions/venv`（⚠️ `venv/bin/pip` 的 shebang 指向已删除旧路径——装包一律用 `~/.pt-sessions/venv/bin/python -m pip install …`）；M-Team 档案合并为 `~/.pt-sessions/mteam-session` 单一副本；discfan / htpt / wintersakura cookie 迁入 `~/.pt-sessions/state/`；旧目录 `cache/documents/{mteam_keepalive_test,u2,cnlang}` 已删除。全库已无 `cache/documents` 活引用。

## 七、跑批次前的现场判读（会话档案 / 瞬时失败）

> 用途：例行里「哪些站批次能直接签、哪些站必须走完整登录」不用猜，先看档案。

- **档案里有没有登录态，看 `cookies.sqlite` 字节数**：
  `ls -la ~/.pt-sessions/*-session/cookies.sqlite | awk '{print $5, $9}'`
  - **98304 字节 = Chromium 空模板**（从未写入过 cookie）→ 该站档案里没有登录态，`pt_batch_check.py` 只会回「未登录」，必须跑一次完整登录脚本。
  - **524288 字节（或更大）= 有真实 cookie**，批次里基本能直接进站、按 `attendance.php` 自动签。
  - 一批站里同时出现这两种大小是常态；先按大小分流，再决定哪几个站要补登录，能省掉整轮瞎等。
- **单站瞬时超时不要直接记 fail**：`Page.goto: Timeout 60000ms exceeded`（attendance.php 导航超时）多半是 CF / 站点抽风，不是会话失效。单站重试即可验证：
  `PT_ONLY="<站名>" timeout 560 xvfb-run -a ~/.pt-sessions/venv/bin/python pt_batch_check.py`
  暖会话下整批 11 站约 2.5 分钟，单站重试成本极低——先重试再定成败。
- **判据以站点文案 / 脚本 state 为准，不看状态词**：有的站即使当天已签，正文照样写「签到成功 这是您的第 N 次签到」（PigGo 即如此），`piggo_signin.py` 的 `state` 字段（`already_signed`）才是判据；批次的 `签到成功` 正则命中不等于本轮真签了。
- **站点端显示「今天已签到」而距上一轮已超 24 小时**：属正常结果（各站日界不同，也可能用户侧另有客户端在签）。汇报里一句话说明即可，记为 ok，**不要花多轮去查是谁签的、也不要重复点**。
- **无签到的站**（M-Team / KEEPFRDS / 朱雀 / 天雪 / MonikaDesign / TL / SJTU / BYR）：批次回「已登录」就是成功判据，不要去找签到行。

