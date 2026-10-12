---
name: pt-site-keepalive
description: "Use when 签到pt / PT checkin / keepalive，或国语视界站点操作。"
version: 1.0.0
metadata:
  hermes:
    tags: [keepalive, pt-site, camoufox, auto-login, email-2fa]
---

# PT 站点账号保活脚本

保持账号活跃的自动登录脚本（Camoufox 反检测浏览器 + 邮箱验证码），用于长期不登录会被清退的 PT 站保号。

## ★ 会话与档案管理（重要）

### 档案位置：`~/.pt-sessions/`（**不要放 /tmp**）

`/tmp` 是 **tmpfs（内存盘）**：①档案占等量内存（1.9G 档案 = 1.9G 内存，曾把交换区顶到 50%+ 并触发 OOM）②重启即清空 ③总量仅 3.6G，开十几个站就爆。
所以浏览器档案统一放磁盘上的 `~/.pt-sessions/<站名>-session/`，持久状态文件放 `~/.pt-sessions/state/`；验证码图、答案 txt 等临时件继续放 `/tmp`。

### 凭据：唯一凭据库 `~/.pt-sessions/.env`（0600）

**所有登录脚本的凭据都从这一个文件读**，不再各自散落：

- 脚本默认路径已统一为 `~/.pt-sessions/.env`（可用环境变量 `MTEAM_ENV` 覆盖）。**改脚本时沿用这个默认值**，不要再引入新路径。
- 键位：`MTEAM_USERNAME` / `MTEAM_PASSWORD` / `MTEAM_TOTP_SECRET` / `MTEAM_EMAIL_*`（IMAP 与邮箱验证码），以及本站独立的 `U2_EMAIL` / `U2_PASSWORD`、`CNLANG_USERNAME` / `CNLANG_PASSWORD`。
- ⚠️ **绝不要把凭据文件放回 `~/.hermes/cache/documents/`**：那是缓存目录，被清理后所有登录会同时失败，且症状是「脚本读不到凭据」这种难归因的形态。历史副本在 `~/.pt-sessions/creds-backup-*/` 留一份仅供比对。
- ⚠️ **凭据值不写进技能文档**：只写键名、做法、坑；值一律写「见凭据库」。这个技能的文档常被当成可直接外发的去敏件，值写进去就等于泄露。
- 清理/迁移凭据前先做「排除清单 + 逐个消费者验证」，不要全盘替换 —— 见通用凭据卫生实践（该技能未随本包提供）。

### 备份：**不做例行全量备份**（用户明确要求）

★ **本包未随附历史归档**（原 `scripts/_research/` 未分发）。因此下面各站文档里若提到
`scripts/xxx_login.py` 这类**旧的浏览器版脚本**、而 `scripts/` 里找不到，属正常：它们已被
纯 HTTP 版取代（同名改为 `xxx_http.py`，见 `references/automation-matrix.md` 第六节）或属历史归档。
**以 `scripts/` 目录里实际存在的文件为准**，别照着旧文档去跑不存在的脚本。

★ **两套解释器别混用**：纯 HTTP 族走 `/usr/bin/python3`（要 requests / PyYAML / Pillow / numpy）；
浏览器族走 `~/.pt-sessions/venv/bin/python`（要 camoufox[geoip] + playwright + 内核；
**这个 venv 不在包里，得自己建**）。详见包内 `SETUP.md` 第 3 节。

`scripts/pt_backup_sessions.py` 保留作为**备用工具**（只在即将做高风险操作前手工跑一次），**不要每站登录后都自动备份**。

### 难登录站的策略

「图形验证码 + 强制 2FA」的站（KEEPFRDS / HDSky / CHDBits / UBits / HDDolby / HDHome / OpenCD / U2 共 8 站）需要人工过验证码与动态码：

- 有备份时：优先恢复会话备份（秒级、免验证码）
- **无备份时（当前状态）**：走正常登录流程，验证码由助手双路识图、动态码找用户要
- U2 的验证码**不要走批量识别器**（字体/字号随机化，需 1.1 万种字形覆盖），但**逐张双路自读照常可行**（实测双路读 `SAKc` 一次过），见 `references/u2.md` 第 2 节

**为什么**：这些站一旦登出就极难登回来，而 PT 站的认证 cookie 普遍有效数百天（U2 实测 ~400 天），**恢复 `cookies.sqlite` 就等于免登录**。

恢复会话（**手上确实有备份时**才用；例行不做全量备份，见上）：
```bash
cp <备份>/u2-login-session__cookies.sqlite     ~/.pt-sessions/u2-login-session/cookies.sqlite
cp <备份>/u2-login-session__cookies.sqlite-wal ~/.pt-sessions/u2-login-session/cookies.sqlite-wal
# Camoufox 打开 https://u2.dmhy.org/index.php → 「欢迎回来 ... [已签到]」✅
```

**推论**：遇到难登录的站，**先找有没有可用的历史会话备份，不要去攻克验证码** ——
验证码识别投入产出比极低（U2 自建识别器实测仅 62.2% 逐字 / 33% 整张，见
`references/u2.md` 第 2 节），而恢复备份是秒级且 100% 有效。
**U2 验证码不做批量识别器** —— 逐张双路自读照常（见上）；原因（字体/字号随机化导致需 1.1 万种字形覆盖）见 `references/u2.md` 第 2 节。
⚠️ 删任何备份前先确认目标站能正常登录；但**不要因为「怕丢」而拒绝用户明确要求的清理**。

## 运行方式

- **浏览器档案统一放在 `~/.pt-sessions/`**（**不要放 /tmp**）：
  `/tmp` 是 **tmpfs（内存盘）** —— 档案放那里会①吃掉等量内存（1.9G 档案 = 1.9G 内存，
  曾把交换区顶到 50%+ 并触发 OOM）②重启即清空（登录态全丢）③总量只有 3.6G，开十几个站就爆。
  持久状态文件（`*_cookies.txt` / `*_state.json`）放 `~/.pt-sessions/state/`。
  临时件（验证码图、答案 txt）继续放 `/tmp` 即可（用完即弃、运行时重建）。
- 调试运行（跳过 0–600s 随机人形延迟）：
  `cd /tmp && MTEAM_NO_DELAY=1 xvfb-run -a ~/.pt-sessions/venv/bin/python ~/.hermes/skills/software-development/pt-site-keepalive/scripts/<站>_login.py`
- 单实例锁 `/tmp/<site>_keepalive.lock`：已有实例在跑时静默退出（exit 0），不是失败
- 脚本不自带调度：必须另接 cron / systemd timer 才会定期执行；排查“没在保活”时先 `crontab -l` 和 `systemctl list-timers`
- 成功标准：页面上出现「退出」登录标记（不依赖用户名），然后发通知、退出码 0。失败：截图 + 通知 + 退出码 1
- 随机延迟期间不占资源：sleep 放在浏览器启动前

## 触发词：「签到 pt」

用户说「签到pt」「签到 PT」「PT 签到」等类似说法 → **默认全部 29 站**，依次走一遍；不要反问“哪个站”、不要只做一站。

> ★ 开跑前先 `scripts/record_checkin.py --show` 查今天是否已跑过（同一 PT 日已有完整记录时不要重跑全量，直接引用那轮 `fail` 项作答）。
> ★ 「只看失败的」＝只报 `fail`/异常项；成功站一句带过，不贴 29 站全表；用户没点名的失败站也要如实列出。
> ★ 纯 HTTP 站族、档位表与转换纪律见 `references/automation-matrix.md`（第二、六节）；**TTG 维持 Camoufox**；被取代的旧浏览器脚本**未随包分发**（原在 `_research/_superseded/`，如需查阅请向提供者索取）。
> ★ **逐站操作前先打开该站对应的 reference 文件**；读取失败（缺失/打不开）→ **停止该站并在最终报告里如实说明**，不要凭记忆继续跑。

1. **M-Team**（馒头）`kp.m-team.cc` — 无签到，登录保活。★ **不要改用官方 API（用户 2026-09-28 决定，保持 cookie 登录）**。见 `references/m-team.md`。
2. **Audiences** `audiences.me` — 登录 + `attendance.php` 签到。见 `references/audiences.md`。
3. **OurBits** `ourbits.club` — 登录 + `attendance.php` 签到。见 `references/ourbits.md`。
4. **PT@KEEPFRDS** `pt.keepfrds.com` — 仅登录确认（无签到；保号期全站最短）。见 `references/keepfrds.md`。
5. **HDSky** `hdsky.me` — 登录 + 签到（首页 `#showup` 弹层；**双路读码一致才提交**）。已转纯 HTTP `hdsky_http.py`。见 `references/hdsky.md`。
6. **PigGo** `piggo.me` — 登录 + 签到（2FA）。★ **SafeLine 慢是正常：不能凭“十几分钟没输出”杀掉重跑**（判断进度只看 `/tmp/nx_piggo_*` 文件；`database is locked`＝浏览器在正常工作）；超 30 分钟无进展改天（cookie 58 天，不影响保号）。★ 从零会话先 `nexusphp_login.py --site piggo` 再 `piggo_signin.py`；**会话有效时不会出公告/2FA 表单——别把“没要码”误判成没签到**。见 `references/piggo.md`、`references/piggo-safeline.md`。
7. **CHDBits** `ptchdbits.co` — 登录 + 签到（**签到＝提交答题表单**）。用 `chdbits_http.py --stage1→2→3→4`（`SKIP`=不会+5魔力 / `CHANGE`=换题；页面已“签过到”就直接退出）。见 `references/chdbits.md`。
8. **UBits** `ubits.club` — 登录 + 签到（CF+Turnstile）。★ **仅剩 6 次机会：别用通用脚本，用专用 `ubits_login.py`（等 180s，令牌未就绪即中止不提交）**。见 `references/ubits.md`。
9. **HDDolby** `hddolby.com` — 登录 + 签到（CF+图码+必须 2FA）。★ 铁律：**先取图码 → 最后要动态码 → 同秒填写提交**（字段 `input[name="2fa"]`）；**图码本身有时效：取码后尽快提交，拖过期就重开一轮**。见 `references/hddolby.md`。
10. **TTG** `totheglory.im` — 登录 + 签到（AJAX `signed.php`）。★ **仅 6 次机会、失败封 IP——绝不盲试**；CF 拦 POST → 维持 Camoufox。见 `references/ttg.md`。
11. **HDHome** `hdhome.org` — 登录 + 签到（`GET attendance.php` 打开即自动签）。已转 `hdhome_http.py`。见 `references/hdhome.md`。
12. **OpenCD** `www.open.cd` — 登录 + 签到（两者都要图码；签到页 `plugin_sign-in.php`）。已转 `opencd_http.py`。见 `references/opencd.md`。
13. **U2** `u2.dmhy.org` — 登录 + 签到（账号独立；邮箱+图码+2FA；hosts 指定真实 IP）。★ 圆点题 120s 时限（含冷启动，超时重跑一次）；**以抄图中文字为硬判据**；**不要重拉页面**（每次加载出新题——用 `--stage3` 同次加载的映射提交；图里无字就换题）。已转纯 HTTP `u2_http.py`。见 `references/u2.md`、`references/u2-captcha.md`。
14. **天雪** `www.skyey2.com` — 无签到；登录保活（**2026-10-06 起字幕区站点侧故障，保活=纯登录**；原为模拟下载 1~3 个字幕附件）。已转 `skyey_http.py`+`skyey_fp.js`（Node 现算 skfaid）。见 `references/skyey.md` 第六节。
15. **MonikaDesign** `monikadesign.uk` — 无签到；登录保活（先确认 hosts）。已转 `monika_http.py`。见 `references/monikadesign.md`。
16. **PTHOME** `www.pthome.net` — 登录 + 签到（CF JS 挑战，curl 403 → Camoufox；GET 自动签）。见 `references/pthome.md`。
17. **朱雀** `zhuque.in` — 无传统签到；**例行只做登录**：自动释放技能 365 天卡生效中（不要跑技能、不要建 cron）；**别再提议升级老角色**；`/api/gaming/*` 必带 `x-csrf-token`；等级上限 79（别再试 80+）；圣遗物未开放；**抽卡等花资产先经用户同意**；种子认领不做。理由与数据见 `references/zhuque.md`。
18. **TorrentLeech** `torrentleech.org` — 无签到；登录保活（hosts `172.66.134.33` 三条；curl 即可）。★ 站规禁账号共享，别换出口反复登录。见 `references/torrentleech.md`。
19. **HDFans** `hdfans.org` — 登录 + 签到（图码；无 CF）。★ **绝不勾/带 `securelogin`**；GET 自动签（含补签卡）。见 `references/hdfans.md`。
20. **HDU** `pt.hdupt.com` — 登录 + 签到（`hdu_http.py` 纯 HTTP；验证码 memcached 时效 1~2 分钟；签到＝`POST added.php`，本站无 `attendance.php`）。见 `references/hdu.md`。
21. **PANDA** `pandapt.net` — 登录 + 签到（与 HDFans 同款：regimage 图码；**绝不 `securelogin`**；GET 自动签）。见 `references/panda.md`。
22. **葡萄 PT（SJTU）** `pt.sjtu.edu.cn` — 无签到；登录保活（固定令牌 `checkcode`；15 分钟不活动登出）。见 `references/sjtu.md`。
23. **大青虫** `cyanbug.net` — 登录 + 签到（challenge-response → Camoufox）。★ 跑前先清会话锁（`.parentlock`/`lock` 指死 PID 会让整站打不开）；先判登录态再等表单。见 `references/cyanbug.md`。
24. **DiscFan** `discfan.net` — 登录 + 签到（纯 urllib）。★ HMAC 参数别写反（key=`challenge`）；取图必带图片类 `Accept` 头。见 `references/discfan.md`。
25. **WinterSakura** `wintersakura.net` — 登录 + 签到（标准 NexusPHP，urllib 即可）。见 `references/wintersakura.md`。
26. **织梦** `zmpt.cc` — 登录 + 签到（CF JS 挑战 → Camoufox；无图码；积分叫电力值）。见 `references/zmpt.md`。
27. **BYRBT** `byr.pt` — 无签到；登录保活。★ 出口受限（家宽直连 403）；**2026-10-07 已恢复，走 NAS 代理，别自行折腾出口**（10-10、10-11 例行登录均通过）。见 `references/byr.md` 第八/九节。
28. **海棠PT（HTPT）** `www.htpt.cc` — 登录 + 签到（直连即可）。★ **提交只带 `username/password/imagestring/imagehash` 四字段，绝不带 `securelogin`**。见 `references/htpt.md`。
29. **SunnyPT** `sunnypt.top` — 登录 + 签到（API 三步）。★ **api 子域只认 `accessToken`**（cookie 会 401）；优先续期、**别删 cookie 文件**。见 `references/sunnypt.md`。

—— 非例行 ——
- **CnLang 国语视界**（账号独立）：**只在用户单点时才做**（「签到pt 和国语视界」＝两件都做）；签到已可全自动化（`%64` 绕 CF；`cnlang_sign_http.py`）；**不入 `sites.json`、不设任何常驻自动化（含上新雷达）**。见 `references/cnlang.md`。
- **清单外站名辨析（避免重复调查）**：`hdarea.club`/`www.haidan.video` 从未登录过（来自他人模板）；`skyeysnow.com`=天雪别名、`anime-no-index.com`=MonikaDesign 的 Tracker 域、`naudiences.me`=Audiences 镜像。（DiscFan 已正式接入例行，第 24 站。）
- **U2 备份恢复捷径已作废**：备份已按用户要求删除、当前无备份可恢复；「图形验证码+强制 2FA」站一律走完整登录。结论与数据见 `references/u2-captcha.md`。
- **无签到的站**（M-Team/天雪/MonikaDesign/TorrentLeech/SJTU/BYR）例行做登录保活。2026-10-02 全量补测通过：OpenCD +10、CHDBits 答题（水星计划 +358）、U2 圆点题（一次过）、HDSky 弹层 HTTP 端点打通（P53DN6 +10）——明细见各站 refs。
## 各站 API 与前端代码（2026-09-28 新增研究线）

> 研究目标：不只站点规则，更要摸清**每站的 API 与前端代码结构**（用户明确要求）。

**★ 首选方法：记录真实网络流量。静态扫 JS 对 SPA 基本无效。**

- SPA（Vue / React / Next.js）的 API 路径是**运行时拼出来的**：把 bundle 下载回来 grep `/api/`
  只能捞到零头（实测某 React SPA 静态扫描仅得 1 条 API，且「Laravel」之类指纹是**误报**）；
  同一站改用网络流量记录后立刻拿到真实调用。**别再用静态 grep 的条数下结论。**
- 做法：已登录档案打开站点 → 挂 `page.on('request')` 记录每个请求 → 依次访问关键页
  （种子 / 用户 / 签到 / 论坛 / 游戏 / 商城 / 我的）→ 汇总去重，保留 `method` 与 `post_data`。
- 工具：`scripts/pt_api_scan2.py <批次>`（每批 3 站）→ 落盘
  `~/safeline-research/apis/<site>.json`；**汇总用 `scripts/pt_api_report2.py`**（每站 `.md` + `SUMMARY.md`）。
  ⚠️ `scripts/pt_api_report.py` 是 v1 的配套脚本，只读 v1 的 `api`/`php`/`routes` 字段，
  **喂它 v2 数据会逐站打印「API 0」**（看着像扫描全失败，其实数据都在 `calls` 里）——别用错。
- **静态扫描（下载 JS 再正则）只作补充**：服务端渲染的 NexusPHP 站还能靠它列出 `.php` 端点，
  **SPA 不要依赖它**（原 `pt_api_scan.py` 已随 v2 上线废弃，勿再找）。
- ⚠️ **SPA 站的导航是 JS 路由、页面上没有 `<a>` 标签**，靠「收集站内链接再逐个访问」只能走到
  1~2 页（实测 M-Team / 朱雀 都只到 2 页）→ 要覆盖全站接口，得改成「点导航元素」或
  「直接访问已知路由路径」。
- 已确认的逐站接口档案见 `references/site-apis.md`。

**已验证的站点技术栈**（来自此前 `references/architecture-study.md` 与本轮扫描）：
- **朱雀** TNode（Vue SPA + Ant Design）+ Node 后端，**全部 API 必带 `x-csrf-token`**；
  107 个 API 与前端路由表已落盘在 `references/zhuque.md`。
- **M-Team** Java/Spring Boot + React SPA（webpack）；API 在 `api.m-team.cc`，
  静态在 `static.m-team.cc`；官方 API 文档 `wiki.m-team.cc/api`（需 x-api-key）。
- **MonikaDesign** UNIT3D / Laravel。
- **SunnyPT** Next.js SPA，API 在 `api.sunnypt.top/api/v1/...`（Bearer accessToken）。
- **BYR** Vue SPA，登录 `POST /api/v2/login.php`。
- **大青虫 / DiscFan** crypto-js challenge-response（同源）。
- **NexusPHP 系 20/28 站**（71%）：服务端渲染 PHP，无独立 REST API，
  「接口」就是 `*.php` 端点（`takelogin.php` / `attendance.php` / `bakatest.php` 等）。

## 站点规则与红线（2026-09-28 全站 wiki 研究）

**29 站规则全文已抓取并归档**：`references/site-rules-and-redlines.md`（总表）、
`references/wikis-digest/*.md`（20 站摘要 + M-Team 官方 Wiki 63 页）。

### ★ 四条最关键的硬规则

1. **保号时限：每 35 天内必须用浏览器真登录一次** —— KEEPFRDS 最短（35 天），
   CHDBits/织梦 45 天，HDHome/UBits 60 天，其余 90~150 天。
   M-Team 原文强调「單純做種不算登入，使用第三方工具間接存取也不算登入」。
2. **禁止通过代理连接 tracker**（M-Team 明文；VPN/机场同样禁止；另禁 GCP/AWS/Azure）。
   → NAS 上的 BT 客户端必须绕过 mihomo 代理（127.0.0.1:7890）。
3. **防吸血：分享率过低直接封号** —— HDDolby/HDHome/PTHOME 下载 >100~200G 且
   分享率 <0.2 即封；OurBits <0.3 封。本账号当前全部安全（最低 HDSky 1.568）。
4. **单种上传限速与恶意限速** —— Audiences 125MB/s、PTHOME/HDDolby/TTG/织梦
   100MB/s 超速自动封；M-Team「月累积 15 天均速 <10KB/s」直接封号且不可申诉。

### 其他要点

- **DHT 必须关闭**；HDSky 屏蔽端口 411-413/6881-6889/1214/6346-6347/4662/6699。
- **客户端白名单**：qBittorrent 4.x/5.x-5.2.3，**不支持 Enhanced-Edition**。
- **H&R**：Audiences/OurBits 14天48h、HDHome/织梦 336h、UBits 官种 72h、
  CHDBits H3/H5+HP 点数制；累计 10 条即封号。
- **M-Team 永久 FREE 分类**：音乐（无损/AAC/ALAC/演唱）、运动（全部）—— 正当刷上传。
- **M-Team 收藏卡**：挂种随机掉卡，官种掉得更勤，守护濒危官种有加成。
- **M-Team 红种**：九成问题用「cc 改 io」或 CF 自选 IP 解决；江苏用户建议用 .io 网址。
- **HDSky 认领已关闭**（原文「请不要尝试认领」）—— 印证用户「种子认领别干」的判断。

### 重新抓取

★ **先找对地方：规则常常不在主站 `rules.php`，而在一个独立的 wiki 域名。**
实测 M-Team → `wiki.m-team.cc`、PigGo → `wiki.piggo.me`、DiscFan → `wiki.discfan.net`、
TorrentLeech → `wiki.torrentleech.org`；主站 `rules.php` 里往往只有一句「请去 wiki 看」。
所以抓到一份只有百余字的 `rules.php` 时**不要下「该站没有规则」的结论**，去页面里搜
`https?://[^ ]*wiki[^ ]*` 把域名抠出来。

★ **两种 wiki 引擎的取法不同**：
- **Wiki.js**（M-Team / PigGo / DiscFan）：`POST <wiki>/graphql` 用
  `{pages{list{id,path,title,locale}}}` 列目录（★ `locale` 常是 `zh-tw` 而不是 `zh`），
  但**正文读取可能鉴权失败** → 改抓 HTML `/<locale>/<path>`。
- **DokuWiki**（TorrentLeech）：首页的 `/doku.php/<page>` 链接就是全部页面，直接遍历。
- PigGo 的 wiki 要 **OAuth2 登录**（page 上选「PIGo OAuth2」，授权后 session 存在档案里，
  之后同档案直接可读）；脚本见 `scripts/piggo_oauth.py`、`scripts/fetch_wikijs.py`。
- 各站 cookie 文件格式不统一（**LWP-Cookies-2.0** 的 `Set-Cookie3: name=value; path=…; domain=…`、
  **Netscape** 制表符七列、JSON）——按格式写解析，别假设是 Netscape。

```bash
cd ~/safeline-research
python3 pt_fetch_wikis.py <批次号>   # 批次 1-20 对应 SITES 列表
python3 fetch_mteam_wiki2.py         # M-Team 官方 Wiki（63 页，GraphQL 列目录+HTML 正文）
python3 make_wiki_digest.py          # 生成 digest/*.md 摘要
```

执行要点：
- **依次串行**，不要并发，避免触发风控 / 封 IP。
- 单站失败不中断后面的站点，继续跑完。
- **邮箱验证码不要向用户要 —— 自己从本机邮箱读**（IMAP，见下方「邮箱验证码自助读取」节；**包括新站首次登录的邮箱码**）。只有**动态口令（TOTP / authenticator 类）**才停下来找用户；若该邮箱本机尚未配置过凭据（第一次接入），才请用户给一次。
- **图形验证码先自己读，不要一上来就丢给用户**（用户明确表达过不满：「之前不都是你自己识别的吗」）。做法：**ASCII 点阵自己读像素 + 视觉模型**双读，两者一致就直接提交；两者不一致时先按字形判据自行裁决（见下文 6/G、C/G、S/9 等判别条）或换图重读——**不要把「让用户确认」当默认步骤**（用户原话：「你自己识别」；实测 HDSky 登录码 5/6 位双路一致、第 6 位按视觉逐位理由裁决，一次提交即被接受）。只在自己确实读不定、或连读错两次后，才把放大图发给用户代读。验证码读错通常**不消耗登录次数**，可以放心重读/换图。
- **双路识图里的「视觉路」受模型通道影响**：它走 Hermes 辅助视觉链（`vision_analyze`），而辅助链**不读 `fallback_providers`** —— 主分组抽风时会挂（表现为只剩点阵单路，HDSky/OpenCD 这类带噪点粘连的图容错下降）。已修：`auxiliary.vision.provider=auto` + 本地补丁 `aux-povider-capacity-fallback.patch`（辅助链识别 502/503/504 后走兜底，重启生效）。答题型签到（U2 图题 / CHDBits 窑口问答）**必须靠助手读图**，模型全挂时这些站直接走不动。
- **验证码 / 动态码一律用「两阶段等待」**：浏览器脚本用 `background=true` 跑，先把验证码图导出并打印 `CAPTCHA_READY`，然后**阻塞轮询一个答案文件**；填入后再打印 `NEED_2FA` 等动态码文件。这样动态码从用户发出到提交只有几秒，不会因为 30 秒过期而白白消耗尝试次数。“先要码、再开浏览器”的单阶段做法一定会把码耗掉。
  **具体文件名（记牢，别猜）**：通用脚本 `nexusphp_login.py` 用 `/tmp/nx_<site_key>_captcha.png`（另有 `_clean.png` 净化版）+ 答案 `/tmp/nx_<site_key>_captcha.txt` + 动态码 `/tmp/nx_<site_key>_2fa.txt`；专用脚本各用各的（hdfans/panda 是 `--stage1` / `--stage2 <码>`，hdu 是 `/tmp/hdu_answer.txt`）。写答案前先 `grep` 脚本确认文件名。
- 结束时给一张汇总表：每站「已签到 / 已是签到状态 / 登录失败」，失败的注明原因。
- ★ **「只看失败的」口径下仍要把「站点自报今天已签到」的站单列一句**（如「其余 N 站站点端显示今天已签到」）：这些站不是我们本轮签的，用户会追问「怎么已经签了」，一句话交代清楚比事后解释省事。
- 已有持久登录态时不必重走完整登录流程，直接进签到页判断。
- ★ **登录表单里的复选框一律不要勾、也不要在提交数据里带**（尤其是「**限制只能使用本IP登录**」/ `securelogin`，以及 `ssl` / `trackerssl` / `logout` 这类）。**用户明确要求：以后遇到「限制只能使用本IP登录」千万别勾**。只提交账号/密码/验证码/验证码哈希这四个字段最安全：海棠PT（HTPT）就是因为多发了 `securelogin=yes`，被服务器回「用户名或密码不正确！或者你还没有通过验证」，白排查了很久。**在提交前先抓一次浏览器实际发出的表单体对照，是最快的确认方式。**（2026-09-27 已按此规则把 `hdfans` / `panda` / `wintersakura` / `hdu` / `zmpt` / `cyanbug` 六个脚本里的 `securelogin` 全部移除——该字段在 NexusPHP 登录页的标签就是「限制IP：限制只能使用本IP登录」。）
- 账号密码均为同一套（用户名 `PTUSER`），从本机已有配置读取，不在聊天里索取或复述。

## 例行执行顺序（29 站一次跑完的推荐流程，2026-09-27 实测 ~30 分钟）

> **每轮开记录（供飞书「PT 签到」卡显示进度）**：开跑前 `scripts/record_checkin.py --begin`（站点总数自动从 `state/sites.json` 推导，也可显式 `--total N`；两者都拿不到会**明确报错且不落盘**，绝不猜数）；每站完成后 `scripts/record_checkin.py --site "<站名>" --status ok|fail|skip --note "<判据>"`；收尾 `scripts/record_checkin.py --finish`。记录落在 `$PT_SESSIONS_DIR/state/checkin_runs.json`（默认 `~/.pt-sessions`，保留最近 5 轮），飞书「PT 签到」卡读它显示「已签到 N/M + 最近一轮明细」；站点名以 `state/sites.json`（29 站清单）为准（**2026-10-03 已与技能编号清单同步**：此前该文件误收 CnLang、漏收海棠PT，已改为 28=海棠PT、29=SunnyPT，与例行跑记录逐字一致；CnLang 属清单外非 PT 站，不入此表）。`--show` 可打印最近一轮摘要自检。
> ★ **2026-10-04 起：同一套命令会实时直播一张「流式进度卡」**——`--begin` 自动开卡并发送到飞书（标题「📋 PT 签到进度」）；每 `--site` 追加一行（打字机式写入）；`--finish` 收口为「✅ 完成 N/29」。全程失败安全（卡挂了只打一行提示，绝不拖累签到记录本身）；`--no-card` 可关闭本轮卡；`--demo-card` 可单独演示效果。跑例行时**不需要额外操作**，照常逐站记录即可。★ **登录流程也能直播**：慢环节（读验证码/等动态码/过 WAF）随时 `scripts/record_checkin.py --stage "HDSky · 读取验证码…"`（覆盖卡上“当前动作”行），站点完成时自动变「✅ 最近完成」。下次例行遇到要人工介入的站，记得在等待时顺手发一条 `--stage`。
>
> ★ **2026-10-09 修：卡面会「定格」在某个站 —— 飞书流式模式 10 分钟自动关闭。** 现象：卡上站数明显少于实际记录数（实测定格在第 16 站），但记录文件里 29 站齐全。根因：飞书流式更新模式**距上次开启约 10 分钟后被服务端自动关闭**（官方文档），关闭后所有 `elements/{id}/content` PUT 返回 `200850 card streaming timeout` / `300309 streaming mode is closed`；旧 `_stream()` 只认 `code==0` 且静默返回 False，卡面就永久停在关闭前最后一次成功的状态（那天 03:45 记完第 16 站后去跑批量巡检，13 分钟没碰卡片，正好踩中）。
> - **已修**：`_stream()` 遇 `200850/300309/200510` 会自动 `PATCH /cardkit/v1/cards/{id}/settings`（`{"config":{"streaming_mode":true}}`）重开流式模式再重试一次，并打印到 stderr；长空窗后卡片能自己接上，不再定格。
> - **sequence 必须统一分配**：飞书要求同一卡片 sequence 严格递增，否则 `300317 sequence number compare failed`，且**没有**「已用到几号」的查询接口。现在统一走 `_next_seq() = max(上次+1, 当前秒级时间戳)`——用时间戳做基数，磁盘 `card_seq` 落后于服务端时能自动追平。实测：秒级时间戳与 int32 上限都被接受，**毫秒级（1.79e12）会被 `9499 Invalid parameter value` 拒掉**；sequence 一旦被顶到 int32 上限（2147483647），这张卡就再也改不动（只能重发一张）——别拿真实卡做序号上限实验。
> - **排查手法**：卡面行数 < 记录行数时，先看是否长空窗（>10 分钟）导致流式超时；`checkin_runs.json` 最后一条 run 的 `sites`/`card_lines` 才是真相，卡面只是显示层。补发完整卡：读记录文件 → `card_begin` → 全量 `_stream(list)` → 收口。

> ★ **2026-10-05 起记录器契约升级（务必遵守）**：① `--site` **必须**在 `--begin` 之后 —— 没有进行中的轮次时默认拒绝并 exit 1；确实要临时补记才加 `--allow-new-run`（会打 `[warn]`）。② 每轮**必须**以 `--finish` 收口：它除了关轮次，还会**清掉飞书静音标记并收口流式卡**；只跑 `--site` 不收口，会让「PT 签到」卡一直停在进度中（静音窗只能靠心跳超时兜底自灭）。**审计实测近 5 轮里有 3 轮没走 `--finish`，这是纪律问题，不是可选项。** ③ 记录器每次 `--site`/`--stage` 都会刷新心跳 —— 标记为 v2 格式 `{v,started,hb,round,pid}`，插件侧按「45 分钟无心跳＝停摆自灭」判活、另有 12 小时硬上限；因此长跑中间**不需要额外操作**，心跳由记录本身顺带维护。④ 状态文件损坏**不再静默清空**：会另存 `checkin_runs.json.corrupt.<时间戳>.<pid>` 并在 stderr 告警。⑤ 并发写已加 `checkin_runs.json.lock` 文件锁，多进程同时记录不再丢更新（旧版实测 40 条并发只剩 2 条落盘）。

1. **先跑纯脚本站**（快、无需人工，几分钟搞定）：`sunnypt` → `sjtu` → `tl` → `hdfans` → `panda` → `discfan` → `wintersakura` → `htpt`（有验证码的按「两阶段等待」处理）。**HTTP 版已实测登录、可逐步加入此列**：`hdhome_http.py`、`monika_http.py`、`skyey_http.py`（单命令级）；`opencd_http.py`、`chdbits_http.py`、`u2_http.py`、`hdu_http.py`、`hdsky_http.py`、`byr_http.py`（按各自 `--stage` 跑）。
   ★ **会话优先，先试复用再谈验证码**（2026-10-04 实测，省掉整个读码流程）：这些站的 cookie 都是**持久 cookie**（NexusPHP 的 `c_secure_uid`/`c_secure_pass`），跨日往往仍有效。带码站先跑一次 `--stage1`：脚本若回「已是登录态 / 未取到 imagehash / 登录页异常」就**直接跳登录、只做签到**（opencd / chdbits / u2 / hdu / hdsky / discfan / wintersakura / htpt 全都有这条捷径）。**没有捷径的站（`hdfans_login.py`）就自己用同一 cookie jar `GET index.php`** 看有没有用户名/「欢迎回来」，有则 `GET attendance.php` 即完成。反例代价：HDFans 验证码路连读 3 次全被回「图片代码无效！」（`stage1` 刷多了还出现过退化成噪点的空图，点阵 `segs=0`），改走会话复用 1 秒签到成功——**先花 2 秒验证会话，别急着读码**。通用工具（2026-10-05 新增，首选）：`scripts/nexus_session_checkin.py --name HDFans --base https://hdfans.org/ --cookies ~/.pt-sessions/state/hdfans_cookies.txt` —— 零消耗，只读：index.php 判登录态（无 `name="username"` + 出现用户名）→ 读 attendance.php（NexusPHP 打开即自动签到）→ 回写 cookie。实测 HDFans（+30）、PANDA（+325）、冬樱（+1888）均一次过，全程无验证码；**DiscFan 等繁体站页面为「簽到成功 / 簽到已得 N」——判据已简繁双匹配**（此前只认简体会误报「未见签到文字」；遇到该提示先人工读片段确认，别直接判失败）；这些站的 `*_login.py` 只有 `--stage1/--stage2`，**没有会话捷径，别拿它当探针**（裸跑会打 usage 并退出 2，不代表掉登录）。
   ★ **日界（何时能再签一轮）**：绝大多数站按**北京时间 0 点**重置，即欧洲时间 18:00 过后就是新一天 —— 实测 2026-10-04 22:28 CEST（= 北京 10-05 04:28）跑一轮，全站都已过零点、拿到新一天的签到（SunnyPT 从 checked_in=false 变签到成功、DiscFan 1117→1118、海棠PT 连续 201 天、HDHome 1249 次……）。因此**同一天欧洲傍晚前重复跑只会得「今天已经签到」**（无害、不算失败）；傍晚后再跑就是新的一天。
   ★ **站点瞬时 5xx 不要当失败**：2026-10-05 冬樱 `index.php`/根路径连续返回 **HTTP 500**（站点侧故障，非登录/验证码问题），约 10 分钟后自愈（302），重跑同一命令即签到成功（+1888）。遇到 5xx 先 `curl -o /dev/null -w '%{http_code}'` 探根路径确认是站点而非本机，再等几分钟重试，**不要连着重试刷**。
2. **再用 `scripts/pt_batch_check.py` 串行巡检其余浏览器站**（★ **必须套 `xvfb-run`**，它 `headless=False`）：逐站复用持久 profile → 判登录态 → 直接进签到页（多数 NexusPHP 站打开 `attendance.php` 即自动签）。
   - 该脚本对已有登录态的站**不会尝试重新登录**（避免白扣有限次数），只报告「❌ 未登录/需重登」等人工处理。**注意：它报「未登录」的站常常是已经走 HTTP 通道签完的站**（两套凭据互不影响）——先比对记录里该站是否已 `ok`，再决定要不要重登。
   - 想只跑部分站：`PT_ONLY=HDSky,PigGo`。
   - ★ **个别站报「异常 TimeoutError: Page.goto: Timeout 60000ms exceeded」时，先单站重跑一次再判故障**：`cd /tmp && PT_ONLY=<站> xvfb-run -a ~/.pt-sessions/venv/bin/python scripts/pt_batch_check.py`（实测 HDDolby 首轮 `attendance.php` 导航 60s 超时、单站重跑即回「已登录 + 签到已得 300」）。这类超时多为瞬时，**不要直接判成掉登录去走重登**（那要花一次验证码 + 一次动态码）。
3. **单独处理被脚本报异常的站**：需要过验证码的（HDSky 的 `#showup` 弹层）、需要图像题的（U2 `showup.php`）、PigGo 慢（**耐心等，见第 6 站，别杀进程**）。
   ★ **巡检器报 PigGo「⚠ 被 CF/WAF 拦，无法判定 (HTTP 468)」不是失败**：那是 SafeLine 验证页（`Security Detection Powered By SafeLine WAF`），**约 10 秒内会自行放行**（经验值，**时长待验证**——无计时日志，且与巡检「最多轮 ~40s」并存）。单站处理不用过 2FA：打开 `attendance.php` 后每 5s 读一次 body、最多轮 ~40s，读到「签到成功 这是您的第 N 次签到 / [签到已得N]」即完成（实测一次过；session cookie 有效时全程不出公告、不出 2FA 表单）。

   ★ **「等登录框超时」≠「登录失败」——先怀疑“本来就已经登录”**：登录脚本（如 `zhuque_login.py`）会先 `wait_for_selector('#form_item_username')`，但**已登录的 profile 打开 `/entry/login` 会被跳到 `/index`，登录框永不出现 → 60s 超时**。这类超时是假失败，别据此判定掉登录。权威核验（只读、不动数据）：用同一 `user_data_dir` 启动 Camoufox，打开站首页，看用户栏是否出现用户名，并带 `meta[name='x-csrf-token']` 调 `fetch('/api/user/getInfo')` —— 返回 200 + `data.username` 才算真登录（**不带 csrf 头会返回 400「请求异常，请清空缓存」**，那是假警报）。

   ★ **「登录成功」≠「签到完成」—— 通用脚本常常只完成登录**：`nexusphp_login.py` 跑完打印「⑧ 签到页 … （未见签到文字）」，意思是**登录成功了但签到没做**（该站签到不在它能自动走的路径上）。逐站补做：
   - **HDSky** → `scripts/hdsky_signin.py`（`#showup` 弹层 + 层内验证码；答案写 `/tmp/hdsky_signin_ans.txt`）
   - **HDSky（纯 HTTP 版，首选，秒级）** → `scripts/hdsky_signin_http.py --stage1` → `--stage2 <码>`：端点从 `common.js` 的 `initshowupajax()` 读出 —— `POST image_code_ajax.php{action:new}` 拿 imagehash → `GET image.php?action=regimage&imagehash=…` 存图（`captcha_dotmatrix.py … lowsat` 点阵）→ `POST showup.php{action:showup,imagehash,imagestring}` 回 `{"success":true,"message":N}`（N=本次魔力）。实测 2026-10-04 `D49985` 一次过 +12；**不需要浏览器**（浏览器版 `hdsky_signin.py` 用的是独立档案 `~/.pt-sessions/hdsky-login-session`，**2026-10-04 实测该档案已非登录态**、弹层取不到图而回登录页；它不是 HTTP 版的直接兜底——要用它得先在那份档案里重新登录一次。**别把它的失败当成站点问题**）
   - **TTG** → `scripts/ttg_signin.py`（AJAX `signed.php`，靠捕获 alert 弹窗文本判成功）
   - **UBits** → 直接打开 `attendance.php` 即完成签到（实测：Camoufox 直接导航该页即回「签到成功 这是您的第 N 次签到」，无需额外点击——与 HDFans/PANDA 同款「打开即签」）；登录后在首页点用户栏的 `[签到得U币]`（指向 `attendance.php`）是同一入口。`pt_batch_check.py` 该站 path 已改为 `attendance.php`（此前用 `index.php` 巡检不会触发签到，只会显示「已登录，未见签到相关文字」）。
   - **OpenCD** → `plugin_sign-in.php` 是「验证码图 + 输入框 + 签到/算了」的小表单，**必须填验证码再点签到**；成功返回 `{"state":"success","signindays":…,"integral":…}`（该页不显示「已签到」字样，别按页面文字判失败）；跑 `scripts/opencd_http.py`（纯 HTTP：`--stage1` 登录码 → `--stage2 <码>` 登录（已登录时无需码）→ 自动进签到取码 → `--stage3 <签到码>` 提交并复核签到记录页）。旧浏览器两脚本已归档
   - **HDU** → 跑 `scripts/hdu_http.py`（纯 HTTP：`--stage1` 取码 → `--stage2 <码>` 登录 → `--stage4` 提交签到 `POST added.php`）；旧浏览器版 hdu_login.py 已归档
   - **U2** → `scripts/u2_http.py`（`--stage3` 抓题 → `--stage4 <序号或作品名>` 提交；已签到时页面写「感谢，今天已签到」）；旧浏览器版已归档
   - **朱雀（游戏化，无签到）** → **只登录即可，不要释放技能**：站点有生效中的「自动释放技能 365 天卡」会自己放（见第 17 站）。角色列表里 `info:{}` 的角色是**尚未抽到**，既不能释放技能也不能升级 —— 别把它误读成「未升级角色」
   - **天雪（无签到，需“活跃行为”）** → `scripts/skyey_http.py --stage3`（候选池随机换附件 + 历史去重；判据看附件的「下载次数」+1）；旧脚本已归档。**⚠️ 2026-10-06 起字幕区站点侧故障：暂不必跑 stage3（白扫并会拉黑候选），登录保活即可——见 `references/skyey.md` 第六节**
4. **收尾核对**：有签到记录页的站以记录页为准（最硬）；其余看用户栏标记；无签到的站确认「已登录」即完成。
5. **收口记录（不能省）**：`scripts/record_checkin.py --finish` —— 关轮次 + 清飞书静音标记 + 把流式卡收口成「✅ 完成 N/29」。只跑 `--site` 不收口，卡会一直停在进度中。

> 经验：**大多数站当天已经签过**（尤其一天内跑两次时）—— 看到「今天已经签到过了 / 签到已得 N」就是正常结果，**不要重复点签到**。
>
> ★ **距上一轮已 >24 小时、站点仍回「今天已签到」时，不要去找「谁签的」、也不要重登**：这种形态常**多站同轮齐现**（一轮里 5 站同时如此），各站日界规则不同（有的按 24h 冷却、有的服务器时钟有偏差），**站点自报已签就是权威结果，一律记 ok**。
> - 要证据就用站点自己的**连续天数计数器**（如 CHDBits「已连续 N 天签到」）：比上一轮 +1 即证明两次巡检之间确实被签过 —— 大概率是用户自己手机端的工具/站点自动签到在签，**与我们的流程无关**。
> - **不要为这个异常花时间**（曾去 NAS 翻容器找自动签到工具，一无所获、白费一轮）：用户只关心「有没有漏签」。
> - 反过来：**只有「站点明说没签 + 脚本也确实没提交成功」才算 fail**。

### 跑例行时的操作纪律（下面每条都各踩过一次，代价是整站重跑）

- **外层 `timeout` 必须大于「浏览器冷启动 + 人工读验证码」的总时长**：带 CF/WAF 的站冷启动可达 1~9 分钟（同一站快慢差别很大），而脚本内部等验证码的窗口是 1800s。外层只给 `timeout 600` 会在验证码刚生成时把进程杀掉，表现为「跑到一半凭空退出」。统一用 `timeout 2400`，或干脆不套外层 timeout。
- **不要用 `| tail -N` 包住长跑脚本**：管道会缓冲，脚本早已打印 `CAPTCHA_READY` / `NEED_2FA` 时你看到的仍是一片空白 —— 极易误判成「卡死了」并杀掉一个其实已经跑到要码步骤的进程（PigGo 就这么被误杀过一次）。**判断进度的唯一可靠依据是进度文件**（`/tmp/nx_<key>_captcha.png`、`/tmp/nx_<key>_captcha.txt`、`/tmp/nx_<key>_2fa.txt`）加进程是否存活；要看实时输出就重定向到文件再 `tail -f`，别用管道。
- **会话被清空后不要先跑 `pt_batch_check.py`**：它只判登录态、**从不主动登录**，cookie 清空后它只会逐站报「未登录/需重登」，白跑十几分钟。清空后直接按站点跑登录脚本（通用 `nexusphp_login.py --site <key>` + 各站专用脚本）；巡检器只在「预期已有登录态」时用来核对。
- **探针/巡检器报「未登录」时，先核对它打开的档案目录，再怀疑登录态**：档案名是 `<站名>-login-session`（如 `hdu-login-session`），**不是短站名**；把短名（`hdu`、`opencd`）传给探针时它会**静默新建一个空档案**，于是「未登录」这个结论其实是**正确的**——只不过是对那个空档案而言，真档案里的登录态完好无损（实测：探针报 HDU / OpenCD 未登录，专用脚本 `hdu_login.py` / `opencd_login.py`（均已于 2026-09-30 归档，对应改走 `hdu_http.py` / `opencd_http.py`）一跑就是 `already_logged_in: true` 并当场签到成功）。跑探针前先确认它打开的档案名对不对（档案名是 `<站名>-login-session`），**别拿探针结论去重登** —— 重登要花一次验证码和一次尝试机会。结论一律以「该站专用脚本」为准，探针/巡检器结果只当线索。
  ⚠️ **不要用 `cookies.sqlite` 的大小或「文件在不在」预告哪站要重登**：实测 `mteam-session/cookies.sqlite` 只有 98KB（与所谓「空模板」同尺寸）却仍是已登录态，`zhuque-login-session` / `zm-session` 连 `cookies.sqlite` 都没出现在 `ls` 列表里、巡检器打开仍是「欢迎回来」——登录态可能落在 `-wal` 或档案的其它存储里。尺寸/存在性只能当线索，**唯一权威是「打开站点看到用户名/退出」**。
- **登录脚本在「已登录」时会 exit=1（假故障）**：`monika_login.py`（已归档）/ `zhuque_login.py` 这类按「等登录表单出现」当判据的脚本，已登录时表单不存在 → `wait_for_selector` 60s 超时退出。看到这种超时、而站点其实处于已登录态，判为**保活达成**，不要重跑也不要重登。
- **每个浏览器站都是「一个进程 → 一次人工介入」的串行循环**：跑起来 → 轮询它的进度文件 → 读出验证码写入答案文件 → 需要动态码就找用户要 → 看日志确认结果 → 下一站。不要并发开多个浏览器（内存与风控双重风险）。
- ★ **浏览器批次（`pt_batch_check.py` 十几站）用后台进程跑，别占着回合干等**：`background=true` + `notify`（长批次再加 `heartbeat` 便于中途播报），输出重定向到文件（`> /tmp/pt_batch_<日期>.log 2>&1`）；**批次在跑时不要再并发开第二个浏览器**，也不要空转轮询 —— 收到退出通知后再继续下一批（动态码站、被报异常的站）。中途要播报就 `tail -c 400 <log>` 读文件，**不要用 `| tail -N` 管道**（会缓冲，见上条）。
- **长跑期间逐站主动播报进度**：每完成一站就发一条「已完成 N/29 ＋ 站点原文判据（如「+22」「签到已得 100」）」，用户会盯着流程确认；沉默跑完一串站会被追问「怎么不显示流程和进度了」。**同时顺手记一条**：`scripts/record_checkin.py --site "<站名>" --status ok --note "<判据>"`（飞书「PT 签到」卡的进度就靠它）。

## 邮箱验证码自助读取（IMAP）—— 用户明确要求：**一律自己读，不要问他**

> **规则（用户 2026-09-27 强调）：邮箱验证码一律由 Hermes 自己读取。**
> **唯一例外：某个邮箱是「第一次接入」——本机还没配过它的凭据** —— 这时才需要请用户提供一次（邮箱地址 + 应用密码/授权码），配置好后后续全部自己读。
> （另：TOTP / authenticator 类动态口令仍需找用户。）

- **凭据来源**：统一凭据库 `~/.pt-sessions/.env`，键名 `MTEAM_EMAIL_IMAP_HOST` / `MTEAM_EMAIL_IMAP_PORT` / `MTEAM_EMAIL_USER` / `MTEAM_EMAIL_APP_PASSWORD`（另有 `MTEAM_EMAIL_CODE_TIMEOUT` 控制等待时长）。
- **备用来源**：`~/.config/himalaya/config.toml` 里有 4 个账号（Gmail + 3 个 QQ 邮箱），密码写在 `backend.auth.cmd` 里。⚠️ **不要用宽泛 `grep` 读这个文件**（会把应用密码整行打印出来）；要按 key 精确取值。
- **实测（2026-09-27）**：`imap.qq.com:993` 登录成功，收件箱 61 封；**M-Team 的邮箱同时接收「朱雀 zhuque.in 登录二步」验证码** —— 这两个站的邮箱码都能自助读取。
- **取码写法**：`search(None,'ALL')` 取最近 N 封 → `fetch(i,'(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])')` 看标题 → 命中后 `fetch(i,'(BODY.PEEK[TEXT])')` 抓正文，正则：
  `(?:驗證碼|验证码|Verification|code)[^0-9A-Za-z]{0,12}([0-9]{4,8}|[0-9a-f]{8})`
- **码格式**：M-Team 纯数字 6 位；朱雀 8 位 hex。
- 注意：`imaplib` 登录用 ASCII 编码，应用密码必须纯 ASCII；`.env` 里是占位符时以 himalaya 配置里的真实值为准（**修 .env 值，不要改脚本编码去迁就占位符**）。

## 动态口令（TOTP / 两步验证码）—— 现状与可选方案

> ⚠️ **用户决定（2026-09-27）：不再折腾动态口令自动化。约定流程：脚本先跑到要码那一步（打印 `NEED_2FA` 并阻塞轮询答案文件）→ 我用中文向用户要一次码 → 用户给出 → 立刻写入答案文件提交**（全程几秒，避免 30 秒过期白费尝试次数）。不要主动提议「导出验证器数据」或「重设 2FA」，也不要为它单独做调研/探测。**不要为要码打断整轮例行**：先把其他站跑完，最后集中把需要动态码的站一次问完。

**涉及站**：PigGo（`two_step_code`）、HDDolby（**`input[name="2fa"]`**，强制）、U2（强制）。

★ **2026-10-04 实测：卡内输入方案已评估并否决** —— 手机飞书输入框会唤起原生全屏编辑页（样式不可改，与下拉弹层同类限制）；表单容器还会把数据卷进官方合成命令路径（值到不了我们的回调）。**动态码维持「聊天里要」的既有流程，不要再探索卡内输入。**（组件知识存档：表单提交按钮不能带 `behaviors`；输入框回调字段名为 `action.input_value`。）

**★ 提交顺序铁律（2026-09-27 实测，HDDolby 上验证）**：2FA 站必须「**先取图形验证码图 → 读出来 → 最后才要动态码 → 验证码与动态码同一秒填入 → 立刻提交**」。
反例（踩过的坑）：先填 TOTP 再取验证码，等 2 分钟 → 站点回「**两步验证码错误！**」（码过期）；把两个答案一次性写入文件、脚本同一秒提交 → **一次通过**。

★ **图形验证码有寿命，用户回码慢就别硬提交**：码取出后 **约 5 分钟就开始危险，十几分钟必死**（HDDolby 实测：取图到提交拖了 18 分钟 → 回「**图片代码无效！**」，该站报错时还会顺手废掉这张码，页面必须重取）。
- **读到码就立刻写答案文件**，让脚本先推进到 `NEED_2FA` 再去要动态码 —— 用户思考的时间就不烧验证码的寿命。
- 从取图到提交预计超过约 5 分钟就**杀掉进程重开取新码**，不要赌（重开只花一次取图 + 一次读码）。
- **动态码反而很快**：写文件到脚本填入实测**约 7 秒**，30 秒窗口够用 —— 所以**收到码后只发一条「写文件 + 轮询结果」的命令，中间不要插任何其它调用**，每个多余往返都在吃那 30 秒。
- **「一个一个来」时的固定节奏**：`取图 → 读码 → 写答案文件（脚本进 NEED_2FA）→ 只向用户要这一站的码 → 写入即提交 → 报结果 → 下一站`。
  **不要几站同时挂起等码**：验证码会集体过期，且用户的码 30 秒一变，来不及分别提交。
- **开跑前清掉上一轮的答案文件**（`/tmp/nx_<key>_captcha.txt` / `_2fa.txt`、`/tmp/u2_2fa_code.txt` 等）：脚本见文件已存在会**直接拿去提交**（`u2_http.py` 命令行不给码就读 `OTP_FILE`），旧码会白耗一次尝试。

**已探明的事实（2026-09-27 只读探测，别再重复查）**：
- `pyotp` **已装在 M-Team venv** ✓ —— 本地生成动态码毫无问题，**缺的只是密钥**。
- `.env` 里 `MTEAM_TOTP_SECRET` 为**空** —— 本机目前没有任何已存 TOTP 密钥。
- **站点侧不显示密钥**：U2 的 `2fa.php` 只给「移除我的两步验证」；PigGo / HDDolby 的 `usercp.php?action=security`（安全设定）也不显示密钥/二维码。密钥只在「设置两步验证」那一刻出现，之后服务端只存哈希。
- **HDDolby 有「信任设备」机制**：安全设定页明确写「下次通过 2FA 验证后，浏览器会自动登记为信任设备（**最长 90 天有效**）」→ 一次 2FA 之后 90 天免码。★ 2026-10-01 空 jar 冷启动实测：**cookie/本地存储被清掉后就不再算信任设备**，仍会要求 2FA —— 这是预期行为，不是配置问题，别去查。
- 本机**没有二维码解码库**（zbarimg / cv2 / pyzbar 均无；PIL 只在系统 python3 里，不在 Camoufox venv）。

**可选方案（按推荐度）**：
1. **信任设备**（零风险，优先）：**仅 HDDolby 有**（安全设定页写明 90 天）。**已核实 U2 / PigGo 都没有此类机制**（已查 index / 2fa.php / usercp?action=security / faq / rules 均无「信任设备/记住此设备/免验证」字样；U2 rules 里的“90 天”指的是不登录停用，与 2FA 无关）。
2. **用户从验证器 App 导出一次**：Aegis / 2FAS / Bitwarden / Google Authenticator（可导出 otpauth-migration）等支持导出 → 用户把导出文件或二维码截图发来 → 解码后存本机 `0600` 文件（如 `~/.hermes/pt_totp.json`）→ 之后 `pyotp.TOTP(secret).now()` 全自动。需先装 `pyzbar` 或 `opencv-python`。
   - ⚠️ **若用户用的是 Microsoft Authenticator（安卓版 6.x，蓝色盾牌图标）—— 这条路走不通**：微软官方明确**不支持导出 TOTP 密钥**（只能导出「密码」）。此时改用方案 3（重设时抓密钥），用户无需换 App。
3. **重设 2FA（用户用 Microsoft Authenticator 时的首选）**：先在站点上移除现有 2FA（U2 的 `2fa.php` 有「移除我的两步验证」，需用户给一个当前码 + 密码）→ 再重新启用，**二维码出现的那一刻抓取密钥存本机** → 把二维码图片发到 Telegram 让用户用 MS Authenticator 扫 → 用户读一个当前码确认启用 → 两边都有密钥，以后全自动。代价：需用户授权 + 手机上配合一次（约 3~5 分钟/站），重设期间短暂失去 2FA。
4. **保持现状**：这三个站的 cookie 有效期 29~58 天，且每次跑例行都会刷新 → 实际很少需要动态码。

⚠️ 用户要求：**邮箱验证码一律自己读**；只有动态口令确实拿不到密钥时才找用户，且**不要为此打断整轮例行**（先把其他站跑完）。

## 全量压测结论与待优化项（2026-09-27「清空全部 cookie 从零跑」）

**做法**：用 `scripts/clear_sessions.py --backup` 备份并清空全部会话（浏览器 profile 的 `cookies.sqlite*` + 纯脚本站的 cookie/state 文件），再从头跑一遍 29 站。（该轮生成的 `~/pt_session_backup_*` **已按用户要求全部删除**，`--restore` 只在手上确实有备份时可用；不要把它当成随时可回滚的保底。）

**从零登录成功的 12 站**：SunnyPT / 葡萄 SJTU / TorrentLeech / 大青虫 / 织梦 / BYR（这 6 站全自动，无需人工）＋ PANDA / HDFans / 海棠PT / 冬樱 / DiscFan / HDU（这 6 站需我读一次验证码）。

**M-Team 已适配**：站点改版为 React 新 UI（`Powered by mTorrent`，登录页 `/login`，控件 `id="username"`/`id="password"`），旧脚本用 `index.php` + 判据「页面含**退出**」→ 新 UI 没这两个字 → 误判未登录 → 去填不存在的表单 → `Page.fill` 10s 超时。**适配要点**：换登录 URL、换成功判据。现在跑 `scripts/mteam_login.py`，它用「**登录页有没有表单**」当判据（没有表单 = 已登录，直接去首页确认）—— 这个判据在站点再改版时也不容易失效。

**通用登录脚本已补齐（该缺口已关闭）**：`scripts/nexusphp_login.py` 一份配置表覆盖 13 站（audiences / ourbits / keepfrds / hdsky / chdbits / ubits / hddolby / piggo / u2 / ttg / hdhome / pthome / opencd；★ 2026-09-30 起 hdsky/chdbits/hdhome/opencd/u2 另走纯 HTTP 版），其余站各有专用脚本（`mteam_login.py` / `skyey_http.py` / `monika_http.py` / `zhuque_login.py` / `hdu_http.py` / `cyanbug_login.py` / `zmpt_login.py` / `byr_http.py` / `discfan_login.py` / `hdfans_login.py` / `panda_login.py` / `sjtu_login.py` / `tl_login.py` / `wintersakura_login.py` / `htpt_login.py` / `sunnypt_login.py`）。

★ **纯 HTTP 版脚本族（无浏览器，2026-09-30 起）**：`hdhome_http.py` / `monika_http.py` / `opencd_http.py` / `chdbits_http.py` / `u2_http.py` / `hdu_http.py` / `hdsky_http.py` / `skyey_http.py`（配 `skyey_fp.js`）/ `byr_http.py`，另 `ttg_http.py` 保留（勘察/解析用；登录维持浏览器）。统一惯例：显式 `/usr/bin/python3` 运行、cookie 持久化 `~/.pt-sessions/state/<站>_cookies.txt`、无验证码站单命令跑通、带码站按 `--stage1`（导出验证码）→ `--stage2 <验证码>`（提交）分段（OpenCD/CHDBits/U2/HDU 各有 `--stage3/--stage4` 段；U2 的 2FA 用 `--stage2 <验证码> <2FA>` 或 `/tmp/u2_2fa_code.txt`）。**空 jar 冷启动登录实测全部一次过**：HDHome / MonikaDesign / OpenCD / CHDBits / U2（码+2FA）/ HDU（`7765G4`）/ HDSky（`19G172`）/ 天雪（Node 算 skfaid）/ BYRBT（NAS 代理）。**TTG 实测 CF 拦 POST → 维持浏览器**。~~待「未签日」补测：OpenCD 签到段、CHDBits 答题段、U2 圆点题、HDSky 签到弹层端点~~ → **2026-10-02 全部补测通过**（OpenCD +10 / CHDBits 水星计划 +358 / U2 一次过 / HDSky +10），HTTP 版全链路无待办。逐站细节与进度见 `references/automation-matrix.md` §六。

★ **新站「能不能转纯 HTTP」的判定顺序（先走一遍再动手）**：
① 只读 GET 登录页（不带凭据、不提交）确认表单与额度提示；
② 页面内嵌 `challenge-platform/scripts/jsd` 片段**不算墙**（被动遥测），硬墙 = 整页「just a moment」/ `cf-chl-` / 根本没有表单；
③ **GET 可达 ≠ POST 可通过**（TTG 反例：POST 被 JSD 挑战、无会话产生、不扣次数）——以带会话的一次 POST 实测为准，被拦即止步、保持浏览器；
④ 「curl 登不上」先怀疑 **cookie 会话未保持 + 验证码与 `imagehash` 绑定**（HDU 反例：换回 `LWPCookieJar` 即解），别归因「前端加密」；
⑤ JS 现算反爬令牌（`skfaid` 类 FingerprintJS）→ **本地 Node 跑站点官方 JS + 浏览器环境桩求值**（模板 `scripts/skyey_fp.js`）；SPA 登录 → 扒 bundle 资产清单找登录分包、读请求封装（响应信封 / `Bearer`），照抄前端载荷（见 `references/byr.md`、`references/skyey.md`）。

★ **新站专用脚本一旦跑通就立刻收进 `scripts/`**，不要留在 `/root` 或 `/tmp` 下：散在外面的脚本不会跟着档案路径迁移一起改（踩过：天雪/莫妮卡/朱雀的脚本还指着旧的 `/tmp/...-session`，迁移后一跑就会新建一份临时档案、白白吃掉内存），也不会进打包/备份。迁移过凭据/档案目录后，还要**巡检脚本里的残留旧路径**：`grep -rn 'hermes/cache' scripts/*.py` —— 旧 `.env` 会让脚本静默读旧凭据副本；标准凭据路径只有 `~/.pt-sessions/.env`（`u2_login.py` / `hdhome_login.py` / `opencd_login.py` / `pthome_login.py` 曾各指旧路径，已统一；2026-09-30 全库复检：已无 `cache/documents` 活引用，旧目录整体删除）。

★ **淘汰脚本 / 迁移活文件的收尾规矩**：① 被新版本取代的脚本**先移入 `scripts/_research/_superseded/`**（不直接删），并把 SKILL.md / references / README 里的引用同步改成『已归档』口径；归档判类别前先 `grep -rn '<脚本名>' SKILL.md references/` —— 被文档写为**现行工具**的（如 `opencd_check_log.py` 这类只读核查器）不是旧脚本，**别误归档**；② 迁移**活在用的文件**（venv / 浏览器档案 / cookie）顺序固定为『**复制到新位置 → 只读冒烟验证 → 带前置断言的脚本才删旧**』：冒烟走「读路径」而不是重新登录一遍（如新 venv 里 camoufox 用新档案打开站点首页读 `[退出]`/用户名即定案）；③ 改完布点用 `clear_sessions.py --list`（只读干跑）自查覆盖：新位置全收录、旧位置零残留。

**本次压测发现并已修复的 5 个 bug**：
1. `clear_sessions.py` 漏了 3 个站的 cookie（discfan / htpt / wintersakura 存在 `mteam_keepalive_test/` 目录，不在 /tmp）—— 已加入 glob 与兜底路径。
2. `htpt_login.py` 打印验证码点阵的代码串用了 `% ()` 格式化且转义不全 → **走登录路径时直接 TypeError 崩掉**（以前总复用会话，从未跑到这段）—— 已改为把图片路径作为 argv 传入。
3. `wintersakura_login.py` 同一处同样的 bug —— 已修。
4. `pt_batch_check.py` 登录态判据有两处**假阳性**：① 登录页含「自动**登出**」→ 误判已登录；② Cloudflare/SafeLine 人机验证页 → 误判已登录。**已改为三重判据**：页面上还有登录表单（username/password 输入框）/ URL 含 login·sign-in·auth / 文本含「未登录·必须登录」/ 命中 CF·WAF 特征 —— 任一成立即不算已登录。
5. 会话文件散落在 `/tmp` 与 `mteam_keepalive_test/` 两处 —— 已在清空脚本里统一收录；`clear_sessions.py` 现已改为**自动发现**（扫 `~/.pt-sessions/*/` 的全部 `cookies.sqlite*` + state/ + 旧位置兜底），不再依赖固定清单。
6. 2026-09-30 复跑再修：6 个脚本内嵌的 subprocess 点阵/净化调用（discfan / hdsky_signin / htpt / nexusphp_login ×2 / wintersakura / nexusphp_challenge_login）由 `python3` / `sys.executable` 显式改为 **`/usr/bin/python3`**（PIL/numpy 只在系统 python3 里，venv 没有）—— 消除每轮 `ModuleNotFoundError: PIL` 噪声并恢复双路识图。
7. 2026-09-30 收尾清理：13 个被纯 HTTP 取代的浏览器脚本从 `scripts/` 清理（12 个移入 `_research/_superseded/`；1 个与归档逐字节相同的副本就地去重）；camoufox venv 迁至 `~/.pt-sessions/venv`；M-Team 档案归并到 `~/.pt-sessions/mteam-session`（单一副本）；discfan / htpt / wintersakura cookie 迁入 `~/.pt-sessions/state/`；`~/.hermes/cache/documents/` 下三个旧目录（mteam_keepalive_test / u2 / cnlang）整目录删除。

**2026-09-30 全清复跑（清空 63 个会话文件 → 29/29 全部走通）**：全自动站照旧一次过（大青虫 / 织梦 / 天雪 / BYRBT 等无人介入）；朱雀全程 API（浏览器零参与）；HDU 验证码须 **≤60s** 提交（36.8s ✅ / 113.7s ❌ 超 memcached 极限）；U2 圆点题＝**本地绿点扫描定位 + 视觉辨认所在半图**；PigGo 正确顺序＝先 `nexusphp_login.py --site piggo`（动态码写 `/tmp/nx_piggo_2fa.txt`）再 `piggo_signin.py`。

**教训（通用）**：**只要一个登录/签到脚本长期只走「复用会话」分支，它的完整登录路径就从未被真正验证过。**定期清一次会话跑一遍，才能暴露这类“只在真登录时才崩”的 bug。

## 站点审计：回答「哪些站真的跑过 / 清单有没有漏」

用户问「之前还有哪些站你执行了但没加进清单」这类问题时，**不要凭记忆回答**——去查三处证据，优先直接跑 `scripts/audit_sites_in_history.py`：

1. **会话库（最权威）**：`~/.hermes/state.db` 的 `messages` 表，抓全部文本里的域名并统计；`role='user'` 命中的域名代表用户真的提过。
2. **持久登录会话目录**：`ls -d /tmp/*-login-session` —— 目录存在＝该站真的走完了登录流程，这是「实际执行过」最硬的证据。
3. **站点脚本**：`ls ~/*.py`、`grep -rl <域名> /root /tmp`。

判读规则：
- **扫到域名 ≠ 跑过**。域名可能只出现在你读过的第三方脚本、模板配置或调研网页里（如某签到脚本 `template_sign.ini` 里的 `hdarea.club`、`www.haidan.video`，第三方 `pt_checkin.zip` 里的 `sunnypt.top`）——这些**不是我们的站**（注：`sunnypt.top` 起初也只出现在第三方 `pt_checkin.zip` 里，后来用户发来链接，已正式接入为**第 29 站**），只能在回执里说明「只读过、未执行」。
- **别名/镜像域名不算新站**：`skyeysnow.com`、`bbs.skyeysnow.com`＝天雪；`anime-no-index.com`＝MonikaDesign 的 Tracker 域名；`naudiences.me`＝Audiences 镜像。
- 新站确认执行过之后，**同时**更新本文件的站点清单与持久记忆里的编号清单，两处必须一致（用户会按编号核对）。
- 审计完把结论（哪些是清单外/未执行）**沉淀回本文件**，避免下一轮重复调查。

## 新站接入：先确认凭据，再动手登录

- **不要默认新站与 M-Team 同一套凭据**：密码常常相同，但**用户名可能不同**。实测在 DiscFan 上默认沿用了 M-Team 的用户名，白白消耗两次尝试机会；而提示「用戶名或密碼不正確」**同时涵盖“用户名错”和“密码错”**，不能只怀疑密码。接入新站时先向用户确认该站的**用户名**。
- **凭据层 vs 机制层的分界看尝试次数**：验证码错→次数不减；次数减 1 而服务器只回“用户名或密码不正确”→已经到凭据层（验证码、字段位置、JS 加密都已排除），此时**停手找用户**，不要再换姿势重试。
- **用户发来“站点首页截图”不等于他已登录**：先看右上角是「登錄」按钮还是「歡迎回來, xxx」；站点统计里的“欢迎新会员: xxx”是**最新注册会员**，不是用户账号（会误判成“他已经登进去了→所以密码没问题”）。
- **用户可能在聊天里直接给出密码明文**：只当次使用，**不回显、不入库、不写入脚本/技能/记忆**；能靠 `.env` 里的现有凭据复现时才验证（本次用户给的密码与 `.env` 里的完全一致，再次证明 `.env` 可信）。
- **浏览器实际提交的值要怀疑，不是只看长度**：用 `input_value()` 把填进去的值与预期**逐字符比对**（只输出「是否一致 + 差异位置 + 大小写位数」，不打印明文），能一次性排除“模拟键盘漏字符/大写没按 Shift”。实测 `type()`、`fill()`、`keyboard.type()` 三种方式均一致 → 排除输入环节。

- **验证码判读要「一次双路读 + 立即提交」，不要为了求稳反复复核**：实测 PTHOME 第一轮我在视觉/点阵分歧后又裁剪放大、来回核实，拖到验证码过期，服务器回「**图片代码无效！不要返回，图片代码已被清除**」（**不扣尝试次数**，重跑即可）；第二轮双路一致就立刻提交，一次通过。短时效站（PTHOME / HDU / DiscFan）尤其如此。
- **6 与 G 的判别**：两者都有「上弧 + 左竖」，关键看**底部是否闭合** —— 6 的下半是**闭合环**（底行有横、左右两侧都封口）；G 的左下是**开口**（左竖到底部不收口）。实测 PTHOME 视觉模型把 6 误读成 G，裁剪放大后一看底部闭合即定。
- **C 与 G 的判别看右侧**：C 的右缘在**中段几行完全空白**（只在顶部和底部有弧），G 的右侧一直有竖笔并在底部内折成横。两者都是「上弧 + 左竖」，只看顶部会把 C 读成 G。
- **两路分歧时，裁出「争议的那 1~2 个字」单独打印纯黑点阵**，不要在整图点阵上反复比对：整图点阵行多字密，肉眼容易把相邻字符的笔画算进来。实测 HDU 一张图第 3~4 字（真值 `CC`）在整图点阵里被读成 `GG`，裁出 x∈[56,94] 单独打印后一眼定案。窗口取「争议字符 ± 半个字宽」，并另存一份 `Image.NEAREST` 放大 8 倍的裁剪图给视觉模型复核 —— 两边重新一致再提交。
- ★ **点阵一律跑现成脚本 `scripts/captcha_dotmatrix.py`，不要临场手写点阵代码**（它已按列间隙切分、逐字打印，正是上面那条「裁出争议字」的自动化版）：临时手写的版本一般只印整图，噪音行多、相邻字笔画混在一起，既慢又容易读错——本轮为 HDSky/OpenCD/HDFans/PANDA 各自临时写点阵脚本是纯浪费。第二个参数选净化口径：默认 `auto`（纯黑文字，纯黑过少时退回逐列背景估计），`lowsat` 走「低饱和深色像素」（HDSky 签到层那类彩色噪点图）。解释器用 `/usr/bin/python3`（PIL/numpy 只在系统 python3 里，camoufox venv 没有）。散点噪点图（随机黑点满图飞）改跑 `scripts/captcha_clean.py <png>`：**先去噪再切分**，字符变干净笔画图，实测三站一次读准（见 references/captcha-reading.md §1b）。
- **验证码识别通用要点（NexusPHP 系列）**

- **字符集排除易混字符**：NexusPHP 的 regimage 一般不使用 `0`、`O`、`1`、`I`（防混淆）→ 遇到「圆环」优先读 **D** 而非 O/0；遇到竖线优先读其他字母。实战：点阵读 `OFSFF6` ✕，视觉按字符集裁决读 `DFCFFG` ✓（服务器认可）
- **彩色噪点验证码**：文字是**纯黑 `RGB(0,0,0)`**，噪点是彩色 → 用 `g < 100` 过滤后点阵极干净
- **点阵打印要覆盖全宽**：验证码图宽 150px，若只打印到 x<130 会**漏掉最后 1~2 个字符**（曾因此误读成 5 位）
- **双路识图**（视觉模型 + 自读点阵）分歧时，用**字符集规则**裁决
- **短时效站**（如 DiscFan <70s）：Camoufox 首轮启动就吃掉 40s → 改**循环模式**（浏览器常驻，后续轮次取图只需数秒），并把「取图 → 读数 → 提交」总时长压到最短
- **验证码错通常不扣尝试次数**（DiscFan/PANDA/HDFans 均是）→ 可用「故意填错」抓真实提交数据做诊断（见 `references/discfan.md`）
- **用裸 HTTP 客户端取验证码图时，必须带浏览器的图片请求头**：`Accept: image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8` 加 `Referer: <登录页>`。缺这个头时站点会返回一张**答案不绑定当前会话**的图——即使双路识图一致、逐字符读对，每次提交都回「圖片代碼無效」且**不扣次数**，表现得像「识图永远不准」。带上后同一套流程立刻被服务器接受。**遇到“怎么读都不对”先核对请求头，别在读法上继续折腾。**
- **验证码答案不依赖会话 cookie**：实测裸客户端 CookieJar 为空时服务器仍认可验证码（答案按 `imagehash` 检索）。别把「没有 cookie」当成验证码失败的原因；但也不要据此认为整条链路无状态。
- **零消耗判断账号是否存在（challenge 型站）**：`POST /api/challenge {"username": X}` —— 真实账号返回的 `data.secret` 是 **20 位**，不存在的用户名返回 **40 位随机串**（防枚举，但长度露馅），且不消耗登录次数。

## 通用坑（Camoufox，所有站都适用）

- **先自检环境指纹，再怀疑交互**：登录/签到过不去时，**不要先换点击方式**。先读三个值——`navigator.webdriver`、WebGL 的 `UNMASKED_RENDERER_WEBGL`、`navigator.userAgent`。Playwright 驱动的 Chrome 默认 `webdriver=true`，且渲染器是 `SwiftShader Device`（纯软件渲染）——这是典型的「虚拟机/无头」特征，Cloudflare 一眼识破；Camoufox 原生指纹则是 `webdriver=false` + `ANGLE (NVIDIA ...)` 这类真实 GPU 字符串。用 `scripts/fingerprint_probe.py` 一把测出来。**环境不干净时，换多少种点击方式都是白费。**
- **关于「自动登录 / 记住我」——不要去找不存在的选项**（2026-09-27 逐站核查）：
  - **NexusPHP 系站（大多数）登录页根本没有「自动登录」复选框**。它的「高级选项」只有三个：`自动登出`（15 分钟后自动登出，**勾了反而会掉登录，绝不勾**）、`限制IP`（= `securelogin`，**绝不勾**）、`SSL`（默认已勾且多为 disabled）。**不要为了“勾自动登录”去乱勾这三项**。
  - 这些站的 cookie 时长由站点默认决定，**实测都是持久 cookie（不是会话 cookie）**：多数 ~400 天，最短的 29~58 天（UBits/天雪 29 天、BYR/SunnyPT 30 天、HDDolby 55 天、PigGo 58 天）——都远长于例行周期，且每次跑例行都会刷新，不会因关浏览器掉登录。
  - **真正有「记住我」类选项的站**（都已确认生效）：天雪 Discuz 的「自动登录」+ `cookietime=2592000`（30 天）；MonikaDesign 的 `remember`（`remember_web_*` 89 天）；SunnyPT 的 `rememberMe: true`（30 天）；BYR 的「保持登录」（该控件不持久化，但 `auth_token` 本身 30 天）。
  - **核查手法（零风险）**：直接读浏览器 profile 里的 `cookies.sqlite` 看认证 cookie 的 `expiry` —— `expiry=0` 才是会话 cookie（关浏览器即失效）；也可用 `curl` 抓登录页的 `rowhead/rowfollow` 行把选项列出来。
- **提交前把「字段是否符合预期」做成硬校验，不合就中止**：用户名是否相符、密码长度是否相符、该勾的勾了没、隐藏令牌格式对不对。只有 5~6 次机会的站（TTG、UBits、天雪）一次盲提交代价很大——天雪正是靠这道校验发现 `skfaid` 不是蜜罐、而是必填令牌。
- **Camoufox 绝不要手动覆盖 `user_agent`**：它自带成套一致的指纹，手动改成别的 UA（尤其改成 `HeadlessChrome/...`）等于自己贴上机器人标签，把它的优势全废掉。用 `Camoufox(headless=False, os="windows", humanize=True, persistent_context=True, user_data_dir=...)` 即可；`humanize=True` 提供拟人鼠标轨迹。
- **不要用 `page.evaluate` 读页面自己的全局变量**：它跑在**隔离环境**，`typeof pwmd5`、`typeof STYLEID` 这类探测会全部返回 `undefined`，极容易误判为“站点 JS 没加载”并基于错误结论去改方案（踩过，差点白扣一次登录机会）。要判定页面 JS 是否执行，**注入脚本到主环境、把结果写进 DOM 属性再读回**（DOM 是共享的）：
  ```python
  page.evaluate("""(js) => { const s = document.createElement('script');
                              s.textContent = js;
                              document.documentElement.appendChild(s); }""",
                "document.documentElement.setAttribute('data-probe', JSON.stringify({pwmd5: typeof pwmd5}))")
  val = page.evaluate("() => document.documentElement.getAttribute('data-probe')")
  ```
- **判定登录结果看服务器原始响应正文**（拦截 POST 响应），不要只看页面可见文字：很多站的错误只出现在 AJAX 返回体（如 `<root><![CDATA[...]]></root>`）。
- **提交前确认关键令牌已就绪**（如 Cloudflare Turnstile 的 `cf-turnstile-response`），否则白扣尝试次数。
- 识图**两次交叉验证**；只差大小写时，裁该字符单独放大 12~14 倍用 NEAREST（点阵字体用 NEAREST 比 LANCZOS 更清）定夺。
- **视觉模型给出矛盾答案时，直接把图转成 ASCII 点阵自己读像素**（最可靠，不依赖模型）。Discuz/NexusPHP 的验证码图约 100×30，逐字符边界很清楚：
  ```python
  from PIL import Image; import numpy as np
  a = np.array(Image.open(png).convert('L')).astype(float)
  bg = np.percentile(a, 85, axis=0)        # 逐列背景估计（背景有渐变，不能用全局阈值）
  mask = (bg[None, :] - a) > 18
  for y in range(a.shape[0]):
      print('%3d %s' % (y, ''.join('#' if mask[y, x] else '.' for x in range(a.shape[1]))))
  ```
  实测：视觉模型对最后一位给了 2:2 的 R/P 分歧，ASCII 点阵一看就定——**R 的腿在环下方右侧仍有竖笔画，P 没有，B 应有底部闭合横**。
  点阵打印三条规范：**覆盖整幅图宽度**（写成 `range(20, 130)` 这类局部窗口会把最右侧的字符整位丢掉 —— 实测把 6 位读成 5 位、白提交一轮）、**带列标尺**（每 10 列标一位，用来按列间隙切分字符边界）、**只印有效行并保留行号**。字形判别表（6/8、B/8、9/4、A/4、R/P、C/G）与三类图各自的分离/净化法见 `references/captcha-reading.md`。
- **带彩色噪点的验证码（NexusPHP regimage 系列，如 OpenCD）要先按颜色分离**：文字是**纯黑 `RGB(0,0,0)`**，噪点是彩色。用 `g < 100` 直接过滤，噪点全消、字符形状极干净；直接用灰度阈值分割会被噪点淹没。实测 OpenCD 一次分出 776 个纯黑像素，6 位字符完全可读。
- **Discuz 登录页的隐藏空字段不一定是蜜罐，可能是 JS 现算的反爬令牌**：天雪（skyey2.com）的 `skfaid` 在 HTML 里 `value=""`，但页面 JS 会填成 **64 位十六进制**，必须带着一起提交。把它当蜜罐留空 → 登录必失败。**判断方法：读它的实际格式**（32+ 位 hex = 令牌要保留；固定诱饵串/空 = 蜜罐）。提交前把「字段是否符合预期格式」做成硬校验，不合就中止、别盲提交。
- **页面有资源长期挂住时，Playwright 的 `goto` 和 `click` 都会超时**：`goto(wait_until="domcontentloaded")` 等不到 → 改 `wait_until="commit"` + `wait_for_selector(...)`；`click()` 卡在「performing click action」→ 改用 `page.evaluate` 里 `element.click()` / `form.submit()` 提交（立即返回，不等导航）。这两个坑会让「明明站点用 curl 秒开」的站卡死（天雪踩过）。
- **登录成功判据不能只靠「退出」二字**：天雪成功页只有 `用户名 |我的 |金币 |消息 |提醒 |连接性 | 设置`，**没有「退出」**，用「退出/控制面板」判会得到假阴性。**最硬的判据是认证 cookie**（Discuz 系为 `<前缀>_2132_auth`）——直接读 `browser.cookies()` 查这个 cookie 是否存在。
- **UNIT3D（Laravel）站的登录与判据**：表单是 `POST /login` + `_token`(CSRF，须现取) + `username`/`password`/`remember`，无验证码；成功看 URL 离开 `/login` + cookie `*_session` / `remember_web_*`。**中文界面里同样没有「登出」二字**，别用它判登录态（MonikaDesign 踩过）。
- **验证码「三步净化」对高噪点图（U2 系列）最有效**：① 取非背景色像素；② 抹掉同一行连续 >14 像素的长横段（干扰线）；③ 连通域过滤，只留 ≥25 像素的块（字符），孤立噪点全清。净化后放大成黑字白底图再读。**已脚本化：`scripts/u2_captcha_clean.py`**；注意横段规则只挡横线，**对角线干扰**要靠「宽度 >20 且密度 <0.2 的细长块剔除」补滤。
- **视觉模型读不清时，把净化图发给用户读，比继续换模型/换参数快得多**：U2 的 4 位验证码，视觉两次都读错（`ACg`），用户看净化图一眼给出正确 `AQ6g`。做法：自己读两次不中就发图请用户读，别硬赌。发图时可**附上自己的候选读法供快速核对**，**但仅限「自己的多路读法互相一致」时**（U2 实测：用户回「你是对的」即按候选提交成功），并注明「以你读的为准、不一致直接发你读的」。
  **多路读法互相矛盾时绝不列候选**（实测同一张 U2 码：整串读给 `bfb1` / `bj5t`，逐字裁片读给 `g` / `n` / `R` / `1`）—— 候选会把用户锚定到错答案上，此时只发净化图、让他独立读。
  **触发这个降级路径的判据**：`u2_captcha_clean.py` 打印 `segs=1`（或切出的段数少于位数）＝ 字符粘连未切开 → 别再用裁剪/改参数抢救，直接发净化图。历史机读翻过车的站（HDSky）候选只作核对、不作默认。
- **图像类验证题（U2 签到「选作品」）的正确读法：先抄文字，再按文字匹配选项 —— 不要按画风猜、也不要采信模型给出的序号。** U2 的题面图（约 500×363）经常**直接带着作品标题或作者名**（实测一张图上有「バトルスピリッツ 龍虎の拳」，另一张上有作者名「武田弘光」），而 4 个候选里只有一个对得上。做法：**一次**视觉调用只问两件事——「把图中所有文字逐字抄出来」＋「从这 4 个候选里选序号」，**以抄出的文字为硬判据**：实测模型抄对了「バトルスピリッツ 龍虎の拳」却把序号答成 4（真值 2），**矛盾时按文字选**，选对后站点回「回答正确！」并写进签到记录（该轮 +55 UCoin）。120 秒时限**包含读图时间**，所以只做一次调用、别反复裁剪复核；超时站点回「验证码已过期。不要返回！点我重新签到（信息已缓存，保留10分钟）」→ 按提示重跑脚本、尽快作答即可。
- **点阵与视觉模型交叉是标准流程**：两者一致直接提交；不一致时点阵优先（不依赖模型）；只差一两位时按视觉取一个再验（验证码错通常不扣次数）。
- **但「草率点阵」不如「净化图 + 视觉」**：点阵只有在**逐字符切分、谨慎判读**时才有裁决力。实测 PTHOME 六位验证码（真值 `NEM6C9`），整图粗扫的点阵读成 `HEHOC8`（前两位即错），而视觉模型在**去噪去边框、放大 6 倍**的净化图上读得完全正确。所以：先把图净化干净（去背景/噪点/边框）再给视觉，点阵结论与视觉冲突时优先信视觉。
- **判断站点是不是 challenge-response（前端算密码）型**：拿登录页 HTML 看表单里有没有 `input[name="response"]` —— **有它、且页面引用了 `api/challenge` / `crypto-js` / `hmac`，就是挑战-响应认证**：后端发明文密码会失败，甚至 POST 被服务端挂住不返回（GET 正常）。这类站**直接用 Camoufox 走浏览器流程**，不要徒手移植算法（算法与站点细节见 `references/cyanbug.md`）。
  - **密码框常常没有 `name` 属性**，所以提交的 POST body 里**看不到 `password` 字段是正常的**：密码被页面 JS 读走、连同 challenge 一起算进 `response`（64 位 hex）。别据此以为「密码没填上」而改选择器反复重试。
  - **零消耗抓真实提交内容**：用 `page.on('request')` 捕获目标 URL 的 `post_data`（Camoufox 下比 `page.route` 可靠，route 常拦不到这类 XHR），并**故意填一个错的验证码**提交 —— 验证码错不扣次数，于是能零消耗地看到真实 body（字段是否齐全、`response` 是否已算出、`/api/challenge` 是否被调用）。**提交链路干净却仍扣次数，基本可判为凭据不符**：此时停下找用户，不要继续试（用户会问「是不是你输错位置了」，拿这份 body 就能给出证据）。
- **challenge-response 型站的验证码时效极短，且同一 `imagehash` 每次请求都换一张图**（连取两次图的 md5 就不同）：只能读「刚取到的这张」并立刻提交，不能缓存复用；而 Camoufox 冷启动就要 30～40 秒，单轮「启动→取图→人读→提交」经常来不及。做法：**浏览器常驻 + 脚本循环**（每轮 reload 取新图重试），并让**脚本自己打印 ASCII 点阵**（脚本内 `subprocess` 调系统 python + PIL），把「取图→读数→提交」压到一次往返。打印点阵要覆盖**整幅图宽度** —— 只印到中间会漏掉最右侧的字符。
- **等登录表单别用 `wait_for_selector('#login-form')`**：元素存在但被判为不可见时会白等到超时（30s）。改等真正要操作的控件并加 `state="attached"`（如 `wait_for_selector('input[name="username"]', state="attached")`）。
- ★ **更常见的情况：已有持久登录态时 `login.php` 根本不渲染登录表单**（直接跳首页），此时 `wait_for_selector('input[name="username"]')` 必然白等超时，看起来像“站点结构变了/坏了”。**先判登录态（页面有 `退出`/`欢迎回来`/`控制面板` 且无 username 输入框）→ 有则跳过登录直接进签到页**。大青虫 2026-09-27 就栽在这里（签到其实早就成功了）。
- **被 kill 或超时的 Camoufox 会留下残余进程和 profile 锁**，下一次启动表现为「导航 60s 超时」（站点其实好好的）。清理用 `killall -q camoufox-bin; killall -q Xvfb`（用 `killall` 不用 `pkill -f`，理由见「坑」节），必要时删掉 `user_data_dir` 下的 `lock` / `.parentlock`。**收工时顺手删掉答案文件**，防止残留进程继续提交消耗次数。

## Cloudflare 挑战：判断「能不能过」的次序

1. **先分清挑战层级**：同一站点，首页/登录页往往直接放行，而某个功能路径（如签到插件 `plugin.php?id=xxx`、`dsu_paulsign-sign.html`）被单独挑战。**路径级规则是站点有意设的**（签到是刷分重灾区），不是你的环境问题。
2. **判定方法**：`curl` 带正常 UA 依次探「首页」和「目标路径」——首页 200 无挑战、目标路径 403 带 `cf-mitigated: challenge`，就是路径级规则。再把同一站的其它域名（如 `a.org` / `a.me` / `bbs.a.org`）也测一遍；**若所有主机名的该路径都被拦，换域名就没有意义**。
3. **到了这一步就该停**：环境已干净（见上）、所有 URL 变体与主机名都被拦时，不要再换浏览器 / 换点击方式 / 换 IP 折腾。给用户二选一：**手动点一下**，或**过 1~2 天再自动重试**（IP 在该域名下的信誉会随时间恢复）。
4. Turnstile 到底查哪些信号、以及已穷尽的方案矩阵，见 `references/cloudflare-challenges.md`。

## 新站 / 新机制调研的顺序（比硬试快得多）

1. **先找站点自己的文档**：`/wiki`、`/api`、`/faq`，以及 SPA 路由里的 `ruleAndFaq` 类页面。
   实测两站都有「官方 wiki / 规则页」，直接给出机制与数值（M-Team `wiki.m-team.cc/api` 写明第三方必须用 `x-api-key`；
   朱雀 `/api/site/ruleAndFaq` 给出 11 条规则，含收益削减表与角色等级范围）。**跳过这一步会在黑箱里试很久。**
2. **抓前端 JS bundle，grep `/api/` 字符串字面量**：SPA 的接口清单常以字面量躺在 bundle 里；
   顺带抽 `path: "..."` 就能拿到完整路由表，能发现菜单里没暴露的功能页。
   若 JS 由页面动态注入（webpack 壳），先用纯 HTTP 读壳 HTML 拿到 bundle URL 列表。
   - **多 chunk 的 Vite 系前端：入口 bundle 只是清单**——把清单里每个 `assets/*.js` 逐个拉下来再 grep（`/api/`、请求字段名、响应信封关键字如 `success`/`auth_token`）。BYR 的登录载荷 `{type,username,password,remember}` 与响应信封 `{success,code,msg,data}` 就是这样拿到的（见 `references/byr.md` 七）。
   - ★ **JS 现算的反爬令牌不要手逆算法**：把站点官方 JS 拉到本地，Node 里桩好浏览器全局直接 eval、调它自己的生成函数（实测 FingerprintJS Pro 系 `skfaid` 生成的 64 位 hex 被服务端接受——服务端无法核验组件真伪，只校验格式/存在性）。实例：`scripts/skyey_fp.js` + `references/skyey.md` §5。
   ⚠️ **静态 grep 只覆盖一部分**（路径可能是运行时拼的）—— 要完整接口清单，改用
   「已登录档案 + `page.on('request')` 记录真实流量」，见「各站 API 与前端代码」节。
3. **只读接口先探**：`GET` 类零风险，先把「已拥有 / 状态 / 图鉴定义」读出来再谈写操作。
4. ★ **写操作必须复查状态才算成功 —— 返回码不是证据**：接口回 `SUCCESS` 却没有任何状态变化是常见形态
   （目标对象不满足前置条件、id 语义不对、缺必填字段都会这样静默失败）。
   **每次写操作后重新拉一次列表 / 余额做对比**，不要凭返回码下结论。
5. ★ **误导性错误码按「条件不满足」读，不要按字面读**：如 `LEVEL_IS_90` 实际含义是「等级超过上限」而非「已经是 90 级」；
   「请清空缓存及本站 Cookie 后重试」实际只是缺 CSRF 头。**错误码只提示「哪一类校验没过」，具体阈值要自己推。**
6. **参数语义逐个验证**：同一接口的批量模式与带 id 模式的参数含义可能不同（如 `level` 一处是目标等级、一处是增量）；
   单字段变化 + 复查状态是最快的定位法。

## 卡住时的标准套路

1. **先搜现成的开源/社区实现**（青龙脚本、Greasyfork 油猴脚本、GitHub）——这类站点的自动化往往已有人做过，能直接拿到接口、参数与判据，比自行摸索快得多（用户也会主动要求这么做）。
2. **Discuz / 论坛类站点：公开脚本几乎全部复用已有登录会话（cookie）**，没人写密码登录——图形验证码 + 失败锁定太难缠。登录屡试不过时，优先考虑 cookie/会话方案，而不是继续换姿势提交密码。
3. **不消耗尝试次数的自检手法**：用 `page.route` 拦截提交请求、读出 `post_data` 后 `route.abort()` —— 既能看全发出去的字段（密码是否已 MD5、隐藏字段是否齐全），又不会真的提交。比“先提交再看响应”安全一个量级。（Camoufox 下 `page.route` 可能拦不到 XHR，此时改用真实 Chrome + Playwright。）
4. 登录失败且无法区分“密码错”还是“站点坏”时：让对方用**无痕窗口**自行登一次。**问法必须是可执行的二选一**：「① 打开就是登录态（没输密码）还是 ② 退出后用无痕手输密码登进去的」——只问“能不能登录”会得到“正常啊”这种无法定性的回答（踩过）。
5. **Discuz 有独立的手机版模板与端点**（`forum.php?mobile=1`、提交地址带 `&mobile=yes`），与电脑版是两套代码路径，需手机 UA + 窄视口才能拿到；排查登录问题时两条都要试。
6. **提交侧排除干净后，就要果断停下并给用户二选一**，不要为了“再试一种”而反复消耗失败次数（本会话 6 种组合全失败后才转问用户）。

## 用户偏好（必须遵守）

- **不要为这些站点自行创建定时/自动化任务**：签到、答题、保活、游戏化动作（释放技能等）都等用户明确开口再做（用户明确说过“不着急，等我说了”）。用户明确要求时，做一次性的「到点自动重试」（如等锁定解除）是可以的。
  ★ **用户也会事后主动要求撤掉已建成的工具**（「XX 删掉吧」）。撤的时候按四步走：① 只删**用户点名的那一件**（脚本本体 + 它的状态文件）；② **相邻的知识性记录要留下**（解析口径、风控前例、URL 套路）—— 它仍有价值，连它一起删等于白做一轮研究；③ 在技能文档里把该处标注改成「**已按用户要求删除，勿重建**」，否则未来的会话会照着旧文档把它重建出来；④ 确认没有 cron / 定时任务仍在引用它。删完明确告诉用户「保留了什么」，让他决定是否也要删 —— 他往往只想删常驻部分。
  ★ **用户说「你自己决定」只授权「现在把这件事做掉」，不等于授权建立常驻定时任务** —— 要常驻调度必须单独确认。
  自作主张建的周期性任务往往事后被证明多余（站点自己已有等价机制），只能再回头暂停。
  ★ **已授权花钱/花资产的动作就直接做完，不要再摆一遍回本测算反问**（用户说过「不用管回本」「你自己决定」）——
  把结论与风险讲一次，然后动手；反复用「要不要做 / 我倾向 B」的菜单把决定推回给用户是会被嫌的。
- 答题（尤其 CHDBits 的 bakatest）不确定性高，先问用户再答。
- ★ **PT 站登录/签到一律走本机直连，绝不挂代理**（包括 NAS 的 `127.0.0.1:7890`；NAS 侧端点与维护档案见 NAS 维护手册）：一挂代理出口就变成国外 IP，会触发站点风控甚至封号。**用户明确要求：「不能让他走代理，登陆会变国外ip」** —— 不要再提议用代理去加速或绕 WAF（实测代理既更慢、又换 IP，两头不讨好）。唯一例外是站点本身直连不通（BYR 教育网 IPv6，见第 27 站）——**BYR 已按用户要求（2026-10-07「以后 byr 登陆自动加代理」）固化为「登录自动加代理」**：`scripts/byr_http.py` 的 requests 会话写死 `s.proxies = PROXIES`；`scripts/pt_batch_check.py` 的 BYR 条目也自带 `proxy=`（可用 `BYR_PROXY` 环境变量覆盖，默认 `http://127.0.0.1:7890`）。**跑 BYR 不需要任何额外参数、也不要临时手动加代理**；除 BYR 外一律直连。
- **不要用未确认的凭据盲试登录**：各站失败次数有限，且**锁定/封禁期间返回的提示与「密码错误」相同，无法区分密码对错** —— UBits 6 次封 IP、HDDolby 20 次、HDSky 连错 10 次封 IP、CnLang 错 5 次锁 15 分钟。用户说「账号密码同某站」时先确认再提交；一旦出现锁定提示就停下等解锁，不要继续试。
- **区分「验证码错」还是「凭据错」：看尝试次数有没有扣减**。失败后读提示里的 `你还有 [N] 次尝试机会`：**N 不变 = 验证码层面被拒，重取图重试是安全的；N 减 1 = 验证码已经过了，是账号/密码/两步验证不对 —— 立刻停手，别再重试，找用户确认凭据或让用户手动登一次给会话**。缺了这个信号，就会把凭据问题误当验证码问题反复重试，把仅剩的次数白烧掉。**次数是按 IP/会话计的，不按账号** —— 用户在自己设备上看到的剩余次数与你这个出口的余额可以不同（实测用户在手机上是 10、服务器回给我们的是 8），一律以服务器响应里的 `你还有 [N] 次` 为准，别把用户报的数字当成自己的额度。

- 验证/演示登录流程时：逐步截图给用户确认（登录页 → 提交后页面 → 验证码输入页 → 首页）；用户确认后才算流程验收。确认后的例行/自动运行不再发截图
- **报数字前先跟清单核对口径**：用户会按编号核对 29 站清单。任何统计（站数 / 档案数 / 备份数）都要先想清「这个数是怎么数出来的」再报，别把脚本扫到的条目数当成站点数（踩过：备份脚本把 profile 内部的 `sessionstore-backups` 子目录也当独立档案，24 个档案被报成 47 个；用户当场就问「怎么会是 47 个站点」）。统计脚本要按「真档案特征」过滤（同时存在 `cookies.sqlite` + `prefs.js`），并排除档案内部子目录。
- ★ **回执里的数字只能引用站点自报字段，不要引用被窗口截断的数值**：累计魔力值/积分这类大数在窄窗口里会被截掉前半段（实测 `魔力值 4,098,266.8` 只剩 `98,266.8`），照抄就会把「本次 +10」报成「+98,266.8」。**本次收益只认站点原话** —— 「签到已得 10」「本次签到获得 N 个魔力值」「获得 220 点魔力值」「第 509 次签到，+335 U币」；`4,098,266.8` 这类是**账户余额**，不是本次收益。人工介入次数也**逐条数出来再报**（一次例行里 HDFans / PANDA / HDSky / OpenCD 四个验证码 + CHDBits 答题 + U2 图像题 = 6 次，报成 4 次就是少算）。**没证实的机制不要写成「实测」** —— 回执里出现「实测」二字，必须真有当场日志可回溯。
- ★ **时间 / 日期 / 时长：跑 `date` 只是第一步，输出必须逐字引用。** 本机时区已是欧洲中部（CEST/+0200，DST 自动），与用户所在时区一致。
  **规则**：`date` 显示什么就写什么 —— **不四舍五入、不写「现在约 HH:MM」、不心算加上「上次查到现在过了几分钟」**。
  只要一句话里要报钟点或时长，而对话中最后一次 `date` 距今可能超过 1 分钟，就**在写回复前重跑一次**。
  **踩过两次的形态**：`date` 明明回 `04:04:39`，回复里却写「现在 04:10」；
  后台任务的运行时长同理 —— `ps -eo etime` 显示 `02:14` 就不能说「跑了十几分钟」。
  这类偏差用户一眼就能看出来，且会直接质疑可信度（「你怎么总是报错的时间」）。
  **正确做法**：把 `date` 和要报的数据（进程状态 / 文件列表 / 统计）放进**同一条命令**跑，
  回复里只搬那条命令的原样输出。
- ★ **跑例行期间用户会用单个词随时追问**（进度 / 计划 / 面板 / 后台 / 状态 / 时间）：直接按「**已完成 N/29 ＋ 刚过的站（带站点原文判据，如「第 509 次签到，+335 U币」「[已签到(Showed Up)]」）＋ 剩余站与下一步**」答复，数字全部取当场实测（`date`、日志尾部、`curl` 探测），**不要反问、也不要只回一句「还在跑」**。站点相关的追问（面板 URL、端口、PID、公网出口）同样给实测值，不给记忆值。
  **进度盘点的三条实测命令**（全部搬当场输出，不要凭记忆）：
  ① 今天跑过哪些站：`find ~/.pt-sessions -maxdepth 1 -mindepth 1 -newermt "<今天 00:00>" -printf "%TH:%TM  %f\n" | sort` —— 会话目录 mtime = 该站最后一次被驱动的时间；`state` / `df` / `creds-backup-*` **不是站点**，别数进站数（用户会按 29 站核对）；
  ② 现在是否还在跑：`pgrep -af "showup|nexusphp|_login|baka"`，再用 `ps -eo pid,etime,cmd` 看清是哪个脚本、哪一站；
  ③ 逐站结果：`tail -c 400 ~/.hermes/cache/scratch/pt_r2_<站>.log` —— 判据一律取站点原文（如「感谢，今天已签到」「回答正确！」「签到已得 N」），**不要用自写的关键词启发式**（按 `失败|error` 抓会把正常流程误标成 ⚠）。
  ★ **别把 monika / zhuque 的 `wait_for_selector` 超时当失败上报** —— 这两站脚本以「等登录表单出现」为判据，已登录态下表单不渲染，60s 超时恰好代表**保活达成**（见「跑例行时的操作纪律」条）。报告写「已登录（脚本超时属正常）」，不要写「登录失败」。
  ★ **例行常常由「另一个 Hermes 会话」驱动**（它按「轮询日志 + 写答案文件」的循环在跑）：被问进度时**只读不写** —— 先用日志 mtime 与 `pgrep` 确认驱动方还活着，**绝不要抢写 `/tmp/<site>_answer.txt` / `/tmp/u2_puzzle_answer.txt` 这类答案文件**（两边同时写会互相覆盖，把驱动方刚算好的答案冲掉）；要帮它作答，先确认驱动进程已经不在。
- 回复用中文；先研究验证再改，改完实际运行测试确认，不声称未验证的结果
- 密码/验证码不进入聊天输出：只经脚本 `.env`（0600）或凭据库处理

## 运行环境（重要）

- **camoufox 只装在专用 venv 里**：`~/.pt-sessions/venv/bin/python`（2026-09-30 已从 `cache/documents/mteam_keepalive_test/.venv` 迁入持久目录、与凭据库同处；旧路径已删除）。Hermes 自带 venv 和系统 python 都没装。写新脚本时必须用这个解释器。
- **`~/camoufox` 是个空目录，会遮蔽真包**：cwd 为 `/root` 时 `import camoufox` 会得到 namespace 包，报 `ImportError: cannot import name 'DefaultAddons' from 'camoufox' (unknown location)`。解法：脚本放哪都行，但**运行时的 cwd 不要是 `/root`**（用 `cd /tmp &&` 或直接 `cd` 到脚本目录）。
- 持久化会话目录：`~/.pt-sessions/`（**不要放 /tmp**，/tmp 是内存盘且重启即清）。

## 坑

- **`pkill -f "<关键字>"` 会杀掉自己的 shell**：当命令行里也含该字符串时（例如命令本身就是 `pkill -f "google-chrome"`），pkill 会把执行它的 shell 一起 SIGTERM，命令半途中断、前面的步骤全部白做。对策：用 `killall <进程名>`（按进程名匹配，不匹配命令行），或把模式放进变量（`P="Xvfb"; pkill -f "$P :77"`，这样 shell 命令行里不出现字面量）。
  ★ **`[p]attern` 这种「防自匹配」写法在 `pgrep -f` / `pkill -f` 里同样不可靠**：命令行的其它包装层仍会命中，实测仍把自己的 shell 一起 SIGKILL，整条命令连同后续步骤全部丢失。
  **停后台任务一律按显式 PID 杀**：先 `ps -eo pid,etime,cmd | grep <关键字> | grep -v grep` 看清 PID（跳过自己的 shell），再 `kill <pid>`；
  浏览器任务还要连带清掉 `xvfb-run` 包装进程与孤儿 `Xvfb`，杀完 `ps` 复核一次再继续。
- **邮箱框与验证码框同时出现时，仍必须触发「获取验证码」按钮，且要先往 `#email` 填入账号邮箱**：部分站点（如 M-Team）提交凭证后立即同时渲染 `#email` 和 OTP 输入框；**「只点按钮不填邮箱」= 邮件根本不会发出**（表现为点过按钮但邮箱永远等不到码）。M-Team 是 React 受控表单：`fill('#email', MTEAM_EMAIL_USER)` 后要 `press('Tab')` + `dispatchEvent`（input/change/blur）解禁按钮，再遍历 `button` 找文案含「获取验证码/獲取驗證碼」且 `is_enabled()` 的点击；读码同时扫 INBOX + Junk，等待时长读 `MTEAM_EMAIL_CODE_TIMEOUT`。（另：把发码动作 gate 在“找不到 OTP 框”上也是同类坑，曾导致 90s IMAP 超时。）
- **IMAP 应用密码必须纯 ASCII**：imaplib 登录时用 ASCII 编码，非 ASCII 值（如中文占位文本）直接抛 `UnicodeEncodeError`。`.env` 里是占位符时，真实可用密码通常在本地邮件客户端配置（himalaya config.toml）里——修复 .env 值而不是改脚本编码去迁就占位符。
- **站点信任的浏览器会跳过 2FA**：同一指纹/设备登录成功后，后续登录可能直接进首页、不再要验证码。这是正常现象，不是缺陷；判定成功只看登录标记是否出现，不看验证码环节是否发生。
- **点「退出」不一定清掉登录态**：需要全新登录流程复测时，先清 cookie + localStorage 再导航到 /login，否则页面仍是已登录态。
- 验证码提取按站点格式匹配（M-Team 为纯数字、通常 6 位）；**识图一律两次交叉验证**（原图 + 放大 5~6 倍重读），一致再提交，不一致就刷新重读，别赌。
- **Discuz 论坛（非 NexusPHP）两种登录入口都可用，但成功判据不同**：首页浮动框提交后会弹「请补充下面的登录信息」验证码层——这是**正常第二步，不是错误页**；此时必须点弹窗表单内的 `button[name=loginsubmit]`，页面上同时有好几个可见的「登录」按钮，点错就白费一次尝试。Discuz 是 AJAX 提交、页面不跳转，`#returnmessage_*` 容器里常常只有「找回密码」链接，**不能当错误信息用**；必须拦截 `loginsubmit=yes` 的 POST 响应正文（`<root><![CDATA[错误信息...]]></root>`）来判成功/失败，详见 `references/cnlang.md`。
- **Audiences 图形验证码 OCR 不可靠**：空串提交会报「图片代码无效」并消耗失败次数；要截图识图后在同一会话填入。
- **探测站点可达性要用「文档里记的真实登录 URL」，不要临场拼 `.php` 路径**：MonikaDesign 是 UNIT3D/Laravel，登录是 `POST /login`；用 `curl .../login.php` 探只会拿到 **404**，这只说明该路径不存在，**不能据此断言「入口地址变了 / 站点改版了」**（本轮据此误报过一次，用户拿到的就是错的结论）。探活统一写成：`curl -s -o /dev/null -w "%{http_code} %{time_total}s" --noproxy '*' -A "Mozilla/5.0" <文档里的 URL>`；判「站点挂了 / 入口变了」之前，先用该站专用脚本或 `references/<站>.md` 里的真实 URL 复核。
- **不要用统一的「退出 / 欢迎回来」文本启发式判定登录态**：各 NexusPHP 站用户栏不一样。Audiences 登录成功也不一定有「退出」，它的判据是跳到 `index.php` 且页面出现用户名；OurBits / KEEPFRDS / HDSky / PigGo 才有「欢迎回来 …」+「退出」。用统一启发式会把已登录的站误判成未登录。
- **签到态判定看用户栏标记**：已签到的站用户栏会出现「已签到」「签到已得 N」「[已签到]」等标记，或顶部不再保留签到入口。有标记就不要再点。
- **签到接口的返回值会误报 —— 判据按「硬 → 软」排序**：① **签到记录页里出现当天日期**（最硬，如 `plugin_sign-in.php?cmd=show-log`）→ ② 用户栏标记变化 → ③ 魔力值/积分增量 → ④ ~~接口返回的 `state` 字段~~（**不能单独作准**：OpenCD 实测返回 `state:false` 时签到其实已经成功）。判「签到失败」之前先看记录页，别因为一个字段就重复点签到。
- **SafeLine WAF / Cloudflare 站点要等页面真正渲染再读**：固定 `sleep(5)` 常常读到空 body（拿到的只有页头页脚）。改成轮询直到 `body.innerText` 长度超阈值再解析，否则会把已签到误判为找不到按钮。
- **Audiences 签到页**：`/attendance.php`；若已显示「已签到/签到成功」就不要再点。
- ★ **`pt_batch_check.py` 必须套 `xvfb-run` 跑**：它内部是 `Camoufox(headless=False, os="windows", ...)`，没有 DISPLAY 时**每一站**都会立刻报 `BrowserType.launch_persistent_context: Failed to launch the browser process`（汇总表里满屏「异常 Error」）。本机常驻 `DISPLAY` 为空，正确写法：`cd /tmp && xvfb-run -a --server-args="-screen 0 1920x1080x24" ~/.pt-sessions/venv/bin/python scripts/pt_batch_check.py`。**看到满屏 launch 失败先查 DISPLAY，不要当站点故障。**（单跑 `Camoufox(headless=True)` 能成功，容易误判成「环境没问题」。）★ **解释器别混用**：`pt_batch_check.py` 依赖 camoufox，**只能用 venv 解释器** `~/.pt-sessions/venv/bin/python`；拿系统 `/usr/bin/python3` 跑会立刻 `ModuleNotFoundError: No module named 'camoufox'`（`/usr/bin/python3` 只用于纯 HTTP 脚本 + PIL 点阵工具）。跑之前先 `unset PYTHONPATH`，否则 venv 里的包会被 Hermes 环境的 site-packages 遮蔽。
- ★ **巡检器报的「❌ 未登录」不要当失败上报 —— 先看这一站是不是已经走 HTTP 通道签完了**：浏览器档案（`~/.pt-sessions/<站名>-login-session`）与 HTTP cookie jar（`~/.pt-sessions/state/*_cookies.txt`）是**两套独立凭据**，前者过期完全不影响后者。本轮实测：巡检器把 HDSky / CHDBits / HDHome / U2 / HDU / MonikaDesign / 海棠PT / 天雪 全报「未登录」，而这 8 站**全部已由纯 HTTP 脚本签完**（`ok` 已在记录里）。汇报时按「这站走的是 HTTP 通道、结果已拿到」说明，不要顺着巡检器的结论说「掉登录了」——用户会直接追问「怎么不登录了」。
- ★ **U2 答题：圆点位置只认 `u2_dot_locate.py`，不要问视觉模型「圆点在左还是右」**。本轮实测视觉模型对同一张图**两次都判右侧**（还编出一个「半透明粉紫圆+鼠标箭头」），而 `u2_dot_locate.py` 判 **LEFT**（绿圆 11x8、fill 0.69、ROUNDISH）——按 dot_locate 判的左块提交**一次成功**。视觉模型只用来**辨认 dot_locate 指出的那一块**是 4 个候选里的哪一部（这一步它很准）。
- ★ **U2 提交成功与否，只认 `--stage3` 复跑的回显**：`--stage4` 的「① 签到结果: ✅」是正则匹配到页面里 `UCoin` 字样就打的，**不代表签到成功**；答错/过期时它反而回 `未见明确标记 → window.location.href = 'showup.php'`。最终判据是**再跑一次 `--stage3`** —— 回「✅ 今天已经签到过：[已签到] 标记存在」才算成。不要拿 stage4 的 ✅ 去记 `--site ... ok`。
- ★ **站点整站 5xx 超过 20 分钟没自愈就直接记 fail 收口**：本轮冬樱（`wintersakura.net`）根路径/index.php/login.php **持续 500 达 27 分钟**（首跑 04:52 → 复探 05:19 仍 500），不是等几分钟就好的瞬时故障。探活复核一次、记 `fail` 并写明「站点侧故障」，**不要连着重试刷**，也不要为它拖延整轮收口。
  ★ **同一站连续多日 500 时，每轮只做一次根路径探活**（`curl -s -o /dev/null -m 25 -w '%{http_code} %{time_total}' <根路径>`）**＋记 `fail`，不要再跑该站的登录/巡检流程**（站点没起来，跑也是白跑一轮），等它自愈。

## References

- `references/login-overview.md` — **29 站登录方式总览（已去敏、可直接外发）**：登录机制四分类（纯脚本 / 需浏览器 / 需特殊网络 / 需人工介入）、风险等级与尝试次数判据、例行做什么、通用经验十条、站点清单表。用户要“总结网站登录”或要对外分享时直接给这份。
- `references/m-team.md` — M-Team 保活脚本的目录、.env 键位、登录页选择器、邮箱账号来源与既有修复。
- `references/audiences.md` — Audiences.me 登录（Camoufox + 图形验证码）与签到页流程。
- `references/ourbits.md` — OurBits 登录（Camoufox，无图形验证码，2FA 可空）。
- `references/keepfrds.md` — PT@KEEPFRDS 登录（Camoufox，TOTP 可空，Turnstile 可能出现）。
- `references/hdsky.md` — HDSky 登录（Camoufox + 图形验证码，两步可空）。
- `references/piggo.md` — PigGo（猪猪）登录（SafeLine WAF，需 2FA 动态码）+ **登录 IP / 异地登录审计**（box=202 消息盒、资料页当前IP、判读与抓取坑）；配套脚本 `scripts/piggo_seclog.py`。
- `references/piggo-safeline.md` — **PigGo 两层防护的源码级探测**：Cloudflare（全站 JS 挑战）+ SafeLine challenge v2（`challenge.rivers.chaitin.cn` 下发 `calc.js`/`calc.wasm` 算 PoW）；issue/verify API 报文、拿 JWT 后写 `sl-challenge-jwt` cookie、公开 PoC 的 `calc()` 算法，以及「浏览器本来就能过、不要去做绕过」的结论。
- `references/chdbits.md` — CHDBits 登录（图形验证码）+ 签到 + bakatest 答题的选值与判定坑。
- `references/ubits.md` — UBits 登录与签到（Cloudflare + Turnstile，提交前须等令牌就绪）。
- `references/hddolby.md` — HDDolby 登录与签到（Cloudflare + 图形验证码 + 必须两步验证码；两阶段等待）。
- `references/ttg.md` — TTG（TotheGlory）登录与签到（无验证码；**CF JSD 被动层：GET 放行、POST 被挑战 → 维持浏览器**；仅 6 次登录机会；签到为 `signed.php` AJAX，弹窗消息 + 积分变化双重判据）。
- `references/hdhome.md` — HDHome（高清家园）登录与签到（NexusPHP，无验证码无 CF，20 次尝试；签到 GET `/attendance.php` 即自动完成）。
- `references/opencd.md` — OpenCD 登录与签到（NexusPHP，无 CF，登录/签到都需图形验证码；**验证码按颜色分离纯黑文字**的关键技巧）。
- `references/u2.md` — U2（u2.dmhy.org）登录与签到：DNS 污染修法、邮箱+验证码+2FA 两阶段脚本、验证码三步净化、签到图像题（找圆点选作品）的解法与判据。
- `references/skyey.md` — 天雪 Skyey Snow（skyey2.com）登录保活：`skfaid` JS 反爬令牌、Discuz 登录页两个 Playwright 坑、无签到无任务、字幕附件模拟下载的保活做法与选择器。
- `references/monikadesign.md` — MonikaDesign 莫妮卡（monikadesign.uk）登录保活：UNIT3D/Laravel 登录与判据、DNS 污染 hosts 加固、无签到（/bonus 404）。
- `references/pthome.md` — PTHOME（pthome.net）登录 + 签到：Cloudflare JS 挑战（curl 403 须用 Camoufox）、纯黑文字验证码分离、`attendance.php` 打开即签、以及「净化图+视觉模型 胜过草率点阵判读」的验证码教训。
- `references/zhuque.md` — 朱雀 ZHUQUE（zhuque.in）登录：TNode SPA 纯 API 流程、`send2fa` 需带密码、**验证码是 8 位 hex 不是数字**、`LAST_2FA_VALID` 互斥处理；无传统签到、游戏化动作（释放技能/转盘/竞猜）。
- `references/cnlang.md` — CnLang 国语视界（非 PT，Discuz 论坛）登录结构与正确成功判据；Camoufox 指纹对比数据、验证码点阵读法、CF 路径级封锁与 2026-10-03 百分号编码绕过突破的完整记录。
- `references/torrentleech.md` — TorrentLeech（TL）DNS 污染与 CF 真实 IP 处理、免验证码登录流程与成功判据、账号现状、无签到（只有登录保活）、HnR/比率规则与账号共享风险。
- `references/hdfans.md` — HDFans（hdfans.org）登录 + 签到：NexusPHP 图形验证码（纯黑文字分离）、`securelogin=yes` 自动登录、无 CF 用 urllib 即可、`attendance.php` 打开即签、账号现状与脚本用法。
- `references/hdu.md` — HDU（pt.hdupt.com）登录 + 签到：**已转纯 HTTP（`scripts/hdu_http.py`；旧「curl 永远登不上」结论已推翻——根因是旧探测脚本未保持 cookie 会话）**；页面里那段 `password_hash` 位于 HTML 注释内、不是前端加密；验证码 memcached 短时效应对；签到 = `POST added.php` 带 `action=qiandao`；Camoufox 路径保留备用。
- `references/panda.md` — PANDA（pandapt.net）登录 + 签到：与 HDFans 同款特征（无 CF、无 JS 加密、可 urllib）、`securelogin=yes`、`attendance.php` 打开即签、派生脚本的 sed 写法。
- `references/sjtu.md` — 葡萄 PT（pt.sjtu.edu.cn，Nexus Project）登录保活：极简表单 + 固定 `checkcode` 令牌、15 分钟登出、无签到（各候选路径 404）、账号现状。
- `references/cyanbug.md` — 大青虫（cyanbug.net）登录 + 签到：**challenge-response 算法逐行与为何仍必须用浏览器**、Camoufox 选择器/残余进程两个坑、`attendance.php` 打开即签、10 次机会限制。
- `references/captcha-reading.md` — 图形验证码识别总集：三类图的分离/净化法（彩色噪点纯黑文字、高噪点三步净化、渐变背景逐列估计）、点阵打印三条规范、字形判别表（6/8、B/8、9/4、A/4、R/P、C/G）、时效与两阶段等待、读不准时的升级顺序；**散点噪点图的「先去噪再切分」读法与配套脚本 `scripts/captcha_clean.py` 见 §1b**；U2 蓝底+干扰线图用 `scripts/u2_captcha_clean.py`（三步净化 + 斜线密度过滤，输出 7× 放大图供用户代读）；黑字图（HDU/PTHOME 类）用 `scripts/captcha_clean_blacktext.py`；U2 签到题绿点定位用 `scripts/u2_dot_locate.py`。
- `references/cloudflare-challenges.md` — Cloudflare / Turnstile 查什么信号、挑战层级、判定与止损的通用决策表。
- `references/architecture-study.md` — **29 站架构差异研究**：框架谱系（20/28 站是 NexusPHP 系）、后端栈指纹（靠 Session Cookie 名反推，Server 头无用）、前端栈、防护全景，以及 6 项深挖的执行结果（HDU「bcrypt」是误判、大青虫与 DiscFan 同源、SunnyPT 续期、朱雀经济、M-Team 深度）。
- `references/login-page-scan.md` — **29 站登录页源码级扫描**：CF 拦截面、表单 action/字段对比、前端加密迹象、CSRF meta 令牌、关键结论（9 站用 `imagehash`、DiscFan 表单无 `password` 字段）。
- `references/zhuque_ruleandfaq.json` + `scripts/zhuque_wiki.py` — 朱雀官方 wiki（11 条规则）原文与读取脚本；**收益削减机制**与**种子认领规则**都在里面。
- `scripts/zhuque_econ.py` + `references/zhuque_chars.json` — 朱雀 116 个角色的经济数据与分析（ROI、cost、profit）。
- `scripts/zhuque_draw.py` / `scripts/zhuque_train.py` — 朱雀抽卡（循环抽到集齐，带余额/抽数安全阀）与角色升级（批量到目标等级）。
- `scripts/zhuque_release.py` / `scripts/zhuque_release_strategy.py` — 朱雀技能释放（buff 错开逻辑）与收益最大化分析。**当前都不需要跑**（站点有自动释放卡），保留供卡片失效后使用。
- `scripts/zhuque_train_max.py` — **已作废**（基于「上限 90」的错误前提，只作历史记录）。
- `scripts/scan_all_login_pages.py` / `scripts/scan_architecture.py` / `scripts/identify_masked_sites.py` — 只读扫描三件套：登录页结构、框架指纹、用已登录档案过 CF 识别被遮蔽站点的真身。
- `references/discfan.md` — DiscFan（discfan.net，**例行第 24 站，已攻克**）：challenge-response 字段表与页面 JS 算法（含 Python 等价式）、两条可用技术路径（Camoufox / 裸 HTTP）、「取图必须带图片 Accept 头」的实证、零消耗账号存在性探针。**旧结论「卡在凭据层 / 只剩出口环境层」已作废**——真因是 hmac 的 key/message 写反 + 取图缺图片类 `Accept` 头。
- `scripts/pt_batch_check.py` — **29 站例行巡检器（持久会话版）**：串行复用各站 profile，判登录态 + 进签到页 + 抓签到态，支持 `PT_ONLY=` 过滤；登录态失效只报告不重登。例行跑浏览器站的首选工具。
- `scripts/nexusphp_login.py` — **通用 NexusPHP 登录脚本（Camoufox）**，一份配置表覆盖 13 站（audiences / ourbits / keepfrds / hdsky / chdbits / ubits / hddolby / piggo / u2 / ttg / hdhome / pthome / opencd）。用法：`--site <key>` / `--list` / `--check`。已内建：先判登录态再登录、图形验证码两阶段（先要 2FA 码再取验证码，保证时效）、**Turnstile 令牌就绪等待**（不等就提交会被回「验证失败：未进行验证」）、JS 点击提交、`document.body` 为 null 时的安全读文本。**2026-09-27 实测已通：hdhome / hdsky / ourbits / ttg / keepfrds / audiences / chdbits / pthome / opencd**（含 CF+验证码、Turnstile 等组合）；ubits 已于 2026-10-01 空 jar 冷启动实跑通过（登录 + 签到，第 511 次/连续 68 天/+345 U币）；hddolby 已实跑至「图形验证码 + 2FA 同页」阶段（**新建 profile 也不免 2FA**，该站没有信任设备豁免）。
- `scripts/ubits_login.py` — **UBits 专用登录 + 签到**（2026-10-01 新增）。为什么不用通用脚本：通用版只等 60 秒 Turnstile 令牌，实测冷 profile 要 ~30 秒才渲染出 token，超时后它会**带长度 0 的令牌盲提交**，换回「人机验证未通过」并白耗一次尝试（UBits 连错 6 次封 IP）。本脚本等 180 秒，**令牌未就绪直接中止、绝不提交**；实测冷 profile 约 30 秒就绪、有 CF 放行缓存时 6 秒就绪。签到走首页用户栏 `[签到得U币]` → `attendance.php`。
- `scripts/clear_sessions.py` — **会话备份/清空/回滚（自动发现版）**：扫 `~/.pt-sessions/*/` 全部 `cookies.sqlite*` + 散落的纯脚本站 cookie/state + 旧位置兜底（先 `--list` 看清单）；`--backup` 备份到 `~/pt_session_backup_<时间戳>/` 后删除，`--restore <目录>` 回滚。用于「清空会话从零跑一遍」的压测。⚠️ **只清 cookie 文件**：SPA 站（M-Team 等）的登录态还存在档案目录 `storage/default/https+++<origin>`（localStorage/IndexedDB）里，**清 cookie 不会登出**（实测馒头清空后照常进首页）——要真正冷启动，需手动把这份存储连同 `https+++challenges.cloudflare.com` 一并清掉（有副本档案时两处都清）。
- `scripts/audit_sites_in_history.py` — 扫会话库 + `/tmp/*-login-session` + 本机站点脚本，列出「哪些站真的跑过、哪些域名只是出现过」，用来回答「清单有没有漏站」。
- `scripts/hdfans_login.py` — HDFans 两阶段登录+签到（`--stage1` 取图零消耗 / `--stage2 <验证码>` 提交并签到）。
- `scripts/hdhome_http.py` / `scripts/monika_http.py` / `scripts/opencd_http.py` / `scripts/chdbits_http.py` / `scripts/u2_http.py` / `scripts/hdu_http.py` / `scripts/hdsky_http.py` / `scripts/skyey_http.py`（配 `skyey_fp.js`）/ `scripts/byr_http.py`（另 `scripts/ttg_http.py` 保留勘察）— **纯 HTTP 版登录/签到脚本族**（无浏览器、无 xvfb；cookie 在 `~/.pt-sessions/state/`；用法与实测状态见 `references/automation-matrix.md` §六）。U2 的 HTTP 版走站点旧设备入口 `portalbc.php`、验证码直接下载（见 `references/u2.md` §5）；天雪 skfaid 由 Node 跑官方 JS 现算（见 `references/skyey.md` §5）；BYRBT 走 `api/v2/login.php`（见 `references/byr.md` 七）。
- `scripts/hdu_http.py` — HDU 纯 HTTP 登录+签到（`--stage1` 取码 → `--stage2 <码>` 登录 → `--stage4` 签到）；旧 Camoufox 版 hdu_login.py 已归档。
- `scripts/panda_login.py` — PANDA 登录+签到（从 hdfans 脚本派生，`--stage1` / `--stage2 <验证码>`）。
- `scripts/sjtu_login.py` — 葡萄 PT 登录保活（单阶段，无验证码）。
- `scripts/cyanbug_login.py` — 大青虫登录+签到（Camoufox 单阶段，**必须 xvfb-run**；卡住时先 killall 清残余）。
- `scripts/tl_login.py` — TorrentLeech 免验证码登录保活，curl 式实现。
- `scripts/fingerprint_probe.py` — 一把测出浏览器环境指纹（webdriver / WebGL 渲染器 / UA），Chrome 与 Camoufox 对比。
- `scripts/nexusphp_challenge_login.py` — NexusPHP challenge-response 类站的**通用裸 HTTP 登录**（两阶段：打印点阵 → 等答案文件；内置正确的图片 Accept/Referer 与本地 `response` 计算），不需要浏览器。
- `scripts/hdsky_signin.py` / `scripts/ttg_signin.py` — **登录之外的签到**两件套（HDSky 弹层验证码 / TTG AJAX 弹窗）；- `scripts/nexus_session_checkin.py` — **会话复用签到通用器**（NexusPHP 系；带已存 cookie 读 index.php 判登录态 → 读 attendance.php 自动签到；`--name/--base/--cookies` 三个参数）；HDSky 另有**纯 HTTP 版 `scripts/hdsky_signin_http.py`**（首选：`--stage1`/`--stage2 <码>`，无浏览器）；U2 签到已并入 `u2_http.py`（--stage3/--stage4），旧 u2_showup_signin.py 已归档。
- `scripts/chdbits_http.py` — **CHDBits 纯 HTTP 登录+答题签到**（四段式；`SKIP`=不会、`CHANGE`=换一题）。旧浏览器版 baka 脚本已归档。
- `scripts/opencd_http.py` — OpenCD 纯 HTTP 登录+验证码签到（三段式、不多花验证码）。旧浏览器两脚本已归档（历史坑留存：旧登录脚本提交按钮须 JS 点击，原生 `page.click` 会卡 60s）。
- `scripts/skyey_http.py` / `scripts/monika_http.py` / `scripts/zhuque_login.py` — 天雪 / 莫妮卡（均已转纯 HTTP）/ 朱雀（仍浏览器）的专用登录。
- `scripts/pt_backup_sessions.py` — 会话档案备份（备用工具，不例行跑）：按「同时存在 `cookies.sqlite` + `prefs.js`」识别真档案，避免把 `sessionstore-backups` 这类内部子目录也数进去。
- `scripts/probe_cloudflare.py` / `scripts/probe_piggo_waf.py` / `scripts/test_piggo_challenge.py` — 只读探测：CF 挑战类型与出口机房（`cf-mitigated` 头 / CF-RAY 机房 / curl_cffi 各指纹表现）、SafeLine challenge v2 全链路（issue → calc.wasm → verify → JWT）、公开 PoC 算法验证。站点再报「WAF 拦住了」时先跑这三个拿证据，别凭猜。
- `scripts/pt_probe_features.py` — 只读探测（0 调用、手工运行，原样保留）：产出 `pt_feature_pages.json`（被 `references/hidden-features.md` 引用）。
- `scripts/pt_probe_invest.py` — 只读调查（0 调用、手工运行，原样保留）：织梦银行/借贷、UBits 勋章等结论的来源（见 `references/hidden-features.md`）。
- `references/site-apis.md` — **逐站 API 与前端代码档案**（M-Team 的 `_sgin` 签名、OurBits 的 `api.ourhelp.club`、朱雀 `/api/*`、各站技术栈）。
- `scripts/pt_api_scan2.py` + `scripts/pt_api_report2.py` — **接口扫描主力**：前者用已登录档案记录真实网络流量（静态扫 JS 对 SPA 无效），后者汇总成每站 `.md` + `SUMMARY.md`。
- 凭据存储/迁移/清理的通用规则与坑（含误改数据库后的恢复）见通用凭据卫生实践（该技能未随本包提供）。
