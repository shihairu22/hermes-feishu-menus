# 各站 API 与前端代码档案

> 用途：摸清每个 PT 站的**接口与前端结构**，供自动化与排障使用。
> 采集方式：`scripts/pt_api_scan2.py`（已登录档案 + 记录真实网络流量）→
> `~/safeline-research/apis/<site>.json`；用 `scripts/pt_api_report2.py` 汇总成 `.md`。

## 方法论（先看这条，能省一轮）

- **静态扫 JS ≠ 接口清单**：SPA 的路径是运行时拼接的，把 bundle 下载回来 grep 只能捞到零头，
  还会产出**假指纹**（某 React SPA 被误判出 Laravel）。同一站改用网络流量记录后立刻拿到真实调用。
- **正确做法**：`page.on('request')` 记录真实流量 + 依次访问关键页，保留 method 与 post_data。
- **SPA 没有 `<a>` 导航**（JS 路由），靠收集链接只能走到 1~2 页；要全量覆盖得点导航元素
  或直接访问已知路由路径。
- **出口 IP 自检**：部分站提供 `/geo?ip=<本机IP>` 之类的辅助接口，回显值可确认是否走代理。

## 逐站档案

### M-Team（Java / Spring Boot + React SPA）

- 主机划分：前端 `kp.m-team.cc` · API `api.m-team.cc` · 静态 `static.m-team.cc`。
- 观测到的调用：`POST /api/system/sysConf`、`GET /api/system/unix?...`。
- **★ 2026-09-28 实测更正（详见 `mteam-api.md`）**：
  - `_sgin` 字符串在 JS 里**搜不到**（源码用 `["_","s","g","i","n"].join("")` 拼接）。
    算法：`_sgin = HMAC-SHA1(method + "&" + path + "&" + timestamp, env.secret)`。
  - **但实测：已认证请求不带 `_sgin` 也能成功** —— 只带 `authorization`(JWT) +
    `ts` + `visitorId` + `did` 头即可，`POST /api/member/profile` 与
    `POST /api/system/sysConf` 均返回 200。签名只是前端 axios 拦截器行为。
  - **官方文档写 GET，实际必须 POST**：`getConf`/`member/profile` 用 GET 会回
    `Request method 'GET' is not supported`，改 POST + `{}` 即可。
  - **API 域名有两个**：`api.m-team.cc` 与 `api2.m-team.cc`（实测 `unix` 走 api2）。
  - 有效登录档案是 `~/.pt-sessions/mteam-session`（2026-09-30 起唯一位置；旧 `cache/documents` 副本已删除）。
- 官方立场是第三方改用 `x-api-key`（文档 `wiki.m-team.cc/api`），但**用户明确不用官方 API，
  保持浏览器 cookie 登录**，不要再提议迁移。
- 受 Cloudflare 影响：`/userban` 等路径会出现 `Just a moment...` 挑战页。

### OurBits（NexusPHP + jQuery，服务端渲染）

- 主站无 REST API，接口即 `*.php`。
- **有独立辅助 API 域名 `api.ourhelp.club`**：`/geo?ip=<ip>`、
  `/rating?site=douban|imdb&sid=...`（站点用它补全种子信息）。
- 会话用 JWT（cookie `ourbits_jwt`）。

### 朱雀（TNode：Vue SPA + Ant Design + Node 后端）

- 全部接口在 `/api/*`，**必带 `x-csrf-token`**（从 `<meta name="x-csrf-token">` 取）。
- **★ 2026-09-28 v3 流量扫描抓到 33 个真接口**（静态扫 JS 只能得到 7 个，因为 SPA 导航是 JS 路由、
  没有 `<a>`；v3 改成「点导航元素 + 直连已知路由」后 42 页 / 20 次点击 / **0 异常**）：
  ```
  论坛  GET  /api/forum/get?path=announcement|communicate|gaming|invite
        GET  /api/topic/list?page=&size=&forumId=1|2|4|5
  种子  POST /api/torrent/advancedSearch          ★ 唯一 POST 接口
        GET  /api/torrent/list · listClaims · getClaimInfo · option
  游戏  GET  /api/gaming/listBet?tab=game · listBlackjack · listLottery3d
        GET  /api/genshin/listArtifact?page&size&type&total · listArtifactMap
  灵石  GET  /api/transaction/list?page&size&type&onlyUnsold&onlyRelated
  商城  GET  /api/mall/listMagicCard
  用户  GET  /api/user/getBonusCalc · getInfo · getMainInfo · getMenu · getSecurityInfo
  站务  GET  /api/site/load · ruleAndFaq · status · zwex
  其它  GET  /api/announcement/list · banner/list · invite/get
  ```
- **导航结构（点出来的）**：首页 · 论坛（站务区/交流区/游戏区/邀请区）·
  种子（影视列表/种子列表/发布种子）· 用户信息（个人信息/种子认领/师徒系统/个人设置）·
  灵石系统（灵石信息/道具商城/交易行）· 娱乐游戏
- **前端路由**：`/forum/{announcement,communicate,gaming,invite}` ·
  `/torrent/list/1/20/` · `/torrent/search/<base64>`（查询参数 base64 编码 JSON）·
  `/torrent/upload` · `/user/{info,claims,invite,setting}` ·
  `/bonus/{info,shopping,transaction}` ·
  `/gaming/{genshin/artifact,prizeWheel,blackjack,lottery3d,bet}` · `/site/ruleAndFaq`
- 完整接口清单与收益/玩法说明见 `zhuque.md`。

### 其他站（技术栈指纹）

- **MonikaDesign**：UNIT3D / Laravel（`POST /login` + `_token`）。
  **v3 扫描：21 页 / REST API 7 条（全在 `/api/chat/*`）** —— `audibles` · `bots` · `config` ·
  `echoes` · `messages/1` · `rooms` · `statuses`。
  完整路由：`/torrents`（+ `cards` 卡片展示 / `grouped` / `poster` 海报墙 / `airing` 新番）·
  `/upload/8` · `/requests` 求种 · `/rss` · `/mediahub` · `/forums` · `/playlists` ·
  `/serieslists` · `/polls` · `/users` · `/bonus` · `/achievements` · `/articles` ·
  `/tickets` · `/chat`。功能清单与 UNIT3D 官方一致，无隐藏玩法。
  外部数据源：`image.tmdb.org`（海报）· `lain.bgm.tv`（Bangumi）。
- **SunnyPT**：Next.js SPA，接口在 `api.sunnypt.top/api/v1/...`（Bearer accessToken）。
  **★ 2026-09-28 v3 扫描（cookie 注入浏览器）拿到 14 个接口**：
  ```
  GET  /api/v1/banner/list · site/stats · medals/list · medals/my
  GET  /api/v1/chat/channels · chat/history?count=200&room_id=hall · chat/private/list
  GET  /api/v1/torrent/hot?limit=20
  POST /api/v1/torrent/list            ★ 搜索走 POST
  GET  /api/v1/user/basic-info · details/info · seed-bonus · rainbow-status?ids=
  GET  https://sunnypt.top/api/auth/session      ← NextAuth
  ```
  **页面均返回同一标题 `SUNNYPT`**（客户端渲染，标题不随路由变）。
  大量 `?_rsc=` 请求是 Next.js 的 React Server Components 负载，不是业务接口。
  外部域：`image.tmdb.org` · `img.sunnypt.top` · `pic.pting.club` · `t101.pixhost.cc`。
- **BYR**：Vue SPA，`POST /api/v2/login.php`。
- **大青虫 / DiscFan**：crypto-js challenge-response（同源）。
- **NexusPHP 系（多数站）**：服务端渲染，无 REST API，「接口」= `*.php` 端点
  （`takelogin.php` / `attendance.php` / `bakatest.php` / `plugin_sign-in.php` …）。

## 待补

- 其余站的流量记录结果陆续落到 `~/safeline-research/apis/`，确认后追加到本文件；
  不要为每个站新建文件，一律追加在本文件对应小节下。
