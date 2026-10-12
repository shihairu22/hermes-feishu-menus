# 29 站规则与红线速查（2026-09-28 抓取）

> 来源：各站 `rules.php` / `faq.php` / `wiki.php` + M-Team 官方 Wiki（wiki.m-team.cc 全 63 页）
> 原文数据：`~/safeline-research/wikis/*.json`（20 站）
>            `~/safeline-research/wikis/M-Team-wiki.md`（63 页 / 108 KB）
> 摘要：`~/safeline-research/wikis/digest/*.md`
> 抓取脚本：`~/safeline-research/pt_fetch_wikis.py`、`fetch_mteam_wiki2.py`、`make_wiki_digest.py`

## 一、保号时限总表（★ 最关键）

**未封存账号连续不登录的封禁/删除时限**：

| 站点 | 时限 | 站点 | 时限 |
|---|---|---|---|
| **KEEPFRDS** | **35 天** ★最短 | HDSky | 90 天 |
| CHDBits | 45 天 | OpenCD | 90 天 |
| 织梦 | 45 天 | U2 | 90 天 |
| HDHome | 60 天 | PTHOME | 90 天 |
| UBits | 60 天 | HDDolby | 90 天 |
| HDU | 120 天 | OurBits | 150 天 |
| 大青虫 | 150 天 | Audiences | 40~100 天（按等级） |
| 海棠PT | **180 天** ★最宽松 | HDFans | 90 天 |
| SJTU葡萄 | 120 天 | 冬樱 | **45 天** |
| M-Team | **40 天** | TTG | 需登录验证 |

**补充站点的无流量删号时限**：HDFans 15 天 · SJTU 30 天 · 冬樱 7 天 ·
海棠PT **90 天**（少见的长）· PANDA 7 天 · M-Team 5 天。

**封存账号后**：多数站 90~600 天；TTG 可用积分商城购买保号道具。

**★ 铁律：每 35 天内至少用浏览器真登录一次**（KEEPFRDS 最短）。

**★ M-Team 原文强调**：「登入指用瀏覽器存取網站網頁進行登入，**單純做種不算登入，
使用第三方工具間接存取也不算登入**」→ 必须用浏览器访问网页，Camoufox 例行符合。

**无流量用户**（上传/下载都为 0）：多数站 5~30 天即删号，HDSky/CHDBits/HDHome/
KEEPFRDS/Audiences 都是 7 天，HDDolby 5 天，OpenCD 15 天。

## 二、防吸血红线（分享率过低 → 直接封号）

| 站点 | 条件 | 后果 |
|---|---|---|
| HDDolby | 下载 >100G 且分享率 <0.2 | 立即封禁，不受理申诉 |
| HDHome | 下载 >200G 且分享率 <0.2 | 系统直接封禁 |
| PTHOME | 下载 >100G 且分享率 <0.2 | 直接封号 |
| OurBits | 下载 >100G 且分享率 <0.3 | 直接禁用账号 |
| M-Team | 注册未满 30 天 + 下载 >10G 且分享率 <0.3 | 立即禁用 |

本账号当前分享率：CHDBits 47.414 · PTHOME 24.135 · OurBits 10.711 · OpenCD 8.117 ·
PigGo 8.715 · 织梦 6.184 · UBits 4.199 · HDSky 1.568 —— **全部安全**。

## 三、单种上传限速（超速自动封号）

| 站点 | 上限 | 备注 |
|---|---|---|
| Audiences | 125 MB/s | 自动封禁，可凭 IP 测速视频解封一次 |
| PTHOME | 100 MB/s | 系统自动封禁 |
| HDDolby | 100 MB/s | 警告期内多次违反封号 |
| TTG | 100 MB/s | 单种 |
| 织梦 | 100 MB/s | 首次警告一个月，多次封禁 |
| HDU | 200 MiB/s | 系统速度监控 |
| HDSky | 500 MB/s | 盒子限速 5gbps |
| M-Team | 1 Gbps | 单种上传上限 |
| **PANDA** | **100 MB/s** | 超速系统封禁；对所有等级/设备适用，盒子备案不可豁免 |

**★ DHT/PEX/LPD 必须禁用**（TorrentLeech 官方 Wiki 专页明文：不禁 DHT 会收到警告直至 ban；
HDSky 同样要求）。NAS 上 Transmission 需确认 `dht-enabled: false` / `pex-enabled: false` /
`lpd-enabled: false`。

## 四、恶意限速（做种速度太低也封号）

- **M-Team**：单月累积达 15 天，当日所有有上传的种子合计，在实际上传时间内
  平均上传速度 **< 10 KB/s** → 直接封号，**不接受任何申诉或解除**。
  （当日做种时间 <1 小时的种子不列入统计）
- **HDSky**：单种最大连接数 <10 或单种最大上传速度 <250 KB/s 视为恶意限速 →
  直接禁号；成功举报者奖励 5,000~20,000 魔力。

## 五、H&R 规则汇总

| 站点 | 规则 | 消除成本 |
|---|---|---|
| Audiences | 14 天内做种 48h 或分享率 1.0；累计 10 警告封禁 | 50,000 爆米花 |
| OurBits | 14 天内做种 48h 或分享率 1.0；累计 10 警告封禁 | 10,000 魔力 |
| HDHome | 60 天内做种 336h 或分享率 1 | 20,000 魔力 |
| 织梦 | 14 天内做种满 72h 或分享率 >1；累计 10 条封禁 | 10,000 魔力 |
| UBits | 官方种子需累计做种 72h（即使上传量已超体积） | — |
| TTG | 下载未达体积 10% 不启动；60 天后自动取消；做种超 240h 奖励 1 HP | — |
| CHDBits | H3 = 20 天内保种 72h；H5 = 20 天内 120h；HP 点数制（初始/封顶 5，为 0 失去下载权） | — |

## 六、DHT / 代理 / 端口（全站通用红线）

### ★ 2026-09-28 实测：本环境 BT 流量合规（已查证）

**结论：NAS 上的 Transmission 直连家宽，未走代理，符合 M-Team 规则。**

证据链：
- 容器 `transmission4.0` / `transmission3.0` 均为 **host 网络**，容器内无代理环境变量。
- 容器内 `curl` 出口 = `117.90.15.0`（家宽 IP）★ 决定性证据。
- Transmission 本身**没有 proxy 配置项**，不会主动走代理。
- 主路由（192.168.1.1）nft 规则中**无任何 tproxy/透明代理**，只有端口转发：
  `62691→127.0.0.1`(tr4) · `51616→127.0.0.1`(tr3.0) · `63219→127.0.0.1`(qb 残留)
- 实测 transmission 进程连接：全部为境内 peer + Cloudflare tracker，无境外代理连接。

**⚠️ 同时发现的隐患**：NAS 控制面板设了**全局代理**（指向一台美国 VPS，
AS14315 1GSERVERS）。它**只作用于 NAS 宿主机**（curl/wget 等 CLI 工具会走代理），
**不影响 host 网络的 Docker 容器**。
→ **切勿在 NAS 宿主机上跑任何 PT 登录/签到脚本**（会走代理触发风控）；
PT 例行一律在 Hermes 主机（出口 117.90.15.0 / IPv6 240e:3a3:...）上跑。

### 其他通用红线

- **DHT 必须关闭**：HDSky 等站明文「任何使用 DHT 的用户将因作弊而被系统禁止」。
- **★ 禁止通过代理连接 tracker**（M-Team 明文）；M-Team 另禁
  「VPN / 機場同樣在此限制內」及「GCP、AWS、Azure 連接 Tracker」。
  → **NAS 上的 BT 客户端必须绕过 mihomo 代理**（127.0.0.1:7890）。
- **HDSky 屏蔽端口**：411-413 / 6881-6889 / 1214 / 6346-6347 / 4662 / 6699；
  推荐 49152-65535。
- **客户端白名单**（M-Team）：qBittorrent 4.x / 5.x-5.2.3，**不支持 Enhanced-Edition**；
  建议 libtorrent 1.2.x；NAS 内建非原生下载软件不在支持清单内。
- **盒子（SeedBox）判定**：使用 VPN/代理访问站点同样被视为盒子设备（HDSky）；
  盒子下载不享有促销、上传最多得种子体积 3 倍（M-Team）。
- **禁止网盘离线下载种子**（离线下载/代抓 BT）——M-Team 一经发现概无转圜。

## 七、各站余额与等级快照（2026-09-28）

| 站点 | 关键数据 |
|---|---|
| CHDBits | 魔力 7,127,266.0 · 邀请 6 · 分享率 47.414 · 上传 1.020 PB · 下载 22.020 TB · 做种积分 2,905,604.0 |
| HDDolby | 上传 433.074 TB · 下载 5.290 TB · 做种积分 1,311,769.3 · 流量排名 28/500 |
| OurBits | 分享率 10.711 · 上传 100.252 TB · 下载 9.36 TB · H&R 0/10 |
| PTHOME | 分享率 24.135 · 上传 147.997 TB · 下载 6.132 TB · 魔力 643,433.5 · 流量排名 102/745 |
| OpenCD | 魔力 2,079,844.7 · 邀请 10 · 分享率 8.117 · 上传 4.778 TB · 下载 602.81 GB |
| HDSky | 魔力 2,570,718.6 · 分享率 1.568 · 上传 2.501 TB · 下载 1.595 TB |
| KEEPFRDS | 魔力 1,263,353.7（快乐肥宅） |
| UBits | U币 926,138.8 · 分享率 4.199 · 上传 16.370 TB · 下载 3.899 TB |
| 织梦 | 电力值 2,692,110.8 · 分享率 6.184 · 上传 21.467 TB · 下载 3.472 TB |
| PigGo | 魔力 959,677.3 · 分享率 8.715 · 上传 3.295 TB · 下载 387.11 GB · 补签卡 36 |
| 大青虫 | 魔力 2,519,234.9 · 签到已得 1100 |
| M-Team | 魔力 1,089,581.1 · ratio 53.53 |

## 八、其他重要规则

- **禁转**：不得把本站种子发布到其他 tracker（多站明文，违者永封）。
- **禁公开分享**：不得把站点信息/种子发到公共场所（贴吧、Q群、微信、微博、网盘）
  —— HDSky 明文「否则您将永远无缘」。
- **连坐**：Audiences/CHDBits 等站，作弊或一人多号的树下邀请**连带封禁**。
- **账号交易**：一切魔力/邀请/账号交易行为直接封禁（多站）。
- **M-Team 促销（永久 FREE 分类）** ★：音乐（无损/AAC/ALAC/演唱）、运动（全部）
  永久 FREE；动画 24 小时 FREE 后转 50%；纪录/教育影片永久 50%。
- **M-Team 收藏卡系统**（2026-07-26 上线）：挂种随机掉卡，稀有度 N/R/SR/SSR/UR，
  火称号五阶（薪王/残焰/星火/薪火/传火）；官种掉得更勤，守护濒危官种有加成。
- **M-Team 官方种子魔力加成**：`B = B₀ · (2/π)·arctan(A/L) · (1 + P/100)`，
  官方种子加成 P 不受 50 个做种上限约束。
- **M-Team 红种**：九成问题可用「cc 改 io」或 CF 自选 IP 解决；tracker 禁止浏览器直连。
- **M-Team 江蘇用戶请用 .io 网址**（用户在南京，适用）。
- **HDSky 认领功能已关闭**：「站点已关闭一般用户的认领功能，请不要尝试认领」。

## 十、第三轮补充（2026-09-28 深夜）：PigGo / SunnyPT / TL 官方 Wiki

### PigGo（OAuth2 打通 wiki.piggo.me，12 页全抓）

- **账号规则**：
  - 新注册账号连续 **30 天不登陆** → 封禁。
  - **恶意限速：盒子测试 24 小时内上传速度为 0kb → 直接封禁**。
  - 分享率 **<0.3 → 封禁**（有条件解封：清空魔力+做种积分、降下载量至分享率 1、追加解封考核）。
  - 多个账号汇聚魔力 → 封禁所有相关账号，不予解封。
- **限速规则**（盒子/限速规则页）：
  - 未标记盒子的用户限速上传 **50 MB/s**；全局用户限速单种上传 **128 MB/s**。
  - 超速：1 次禁上传&下载 24 小时；2 次禁 7 天；**3 次禁用账号**。
  - 试图绕过盒子规则 → 视为作弊 → **永久封禁**。
  - 做种上传：非盒用户发布后 24h 内只计下载量 3 倍上传（辅种不计算）；盒子用户 72h。
- **H&R 规则**：儿童专区/3D 专区**全部种子**考核，其他区部分；考核期 **20 天（480h）**，
  期内至少做种 **72h**；消除一个需 **100,000 魔力**；未达标达 **10 个 → 封禁**，
  首次可申诉（清空魔力+做种积分+解封考核），**第二次不再接受申诉**。
- **邀请规则**：**分享率低于 0.1 → 立即禁用，不接受申诉解封**。
- 站点鼓励使用认领功能（但用户已否决，不参与）。

### SunnyPT（Next.js SPA，cookie 注入浏览器后可读）

- **账号保留：有数据（上传/下载）的用户会永远保留** ★（全站最省心）。
- 没有流量的用户：连续 **14 天**不登录 → 删除；注册满 14 天仍无流量 → 封禁。
- 只有发布员能发布资源；新发布种子 free 7 天；不定期全站免费。
- 备用 tracker 域名：`tracker.sunnypt.top` → 备 `sunnytk.top`。
- 无独立「规则」页，规则在 **公告 → 站点规则** 子页。
- 赏金公会 `/bounty`：扬名立万·交易所·道具屋·时魔·航路竞标·神秘宝箱·荣誉勋章。

### TorrentLeech 官方 Wiki（wiki.torrentleech.org，DokuWiki，48 页全抓）

- ★ **必须禁用 DHT / PEX / LPD**（专页 qbit_dht / utorrent_dht / vuze 均有说明），
  否则会收到警告直至 ban。
- 另有 vpn_usage / seedboxes.all.you.need.to.know / reporting_a_seedbox /
  tl_points / user.ratio / user_classes / what.do.i.do.if.i.am.banned 等专页。
- 站点本身无 rules 页，全部规则在该 wiki。

### 其他

- **tr3.0（NAS 上第二个 Transmission 容器）：用户明确「不用管」** ——
  虽然其 `dht-enabled`/`pex-enabled` 为 true，但 8 个种子全为 Stopped、0 连接、
  无实际风险，**不要再提改它的配置**。活跃的是 tr4.0（已正确关闭 DHT/PEX/LPD）。
- **PANDA**：单种限速 **100 MB/s**，超速系统封禁（所有等级/设备适用，盒子备案不可豁免）。
- **海棠PT**：封存 365 天 / 未封存 **180 天**不登录删号；无流量 + **90 天**不登录才删
  （少见的宽松）。
- **DiscFan**：官方 wiki（wiki.discfan.net）**只有 3 页**（home/donate/guests），
  站点自己还没建完，规则实际就是 NexusPHP 默认。
- **BYR**：2026-10-07 已恢复（NAS 代理可通；直连 403 不变）。

### ★ 抓取技巧沉淀

- **Wiki.js 站**（M-Team / PigGo / DiscFan）：`POST /graphql`
  `{pages{list{id,path,title,locale}}}` 列目录（注意 `locale` 可能是 `zh-tw` 而非 `zh`）；
  **内容读取可能需鉴权**，改用 HTML 路径 `/zh-tw/<path>` 或 `/<locale>/<path>`。
- **PigGo wiki 需 OAuth2 登录**：浏览器打开 wiki → 登录 → **PIGo OAuth2** → 授权后
  session 存在档案里，之后同档案直接可读。
- **LWP-Cookies-2.0 格式**（PANDA/海棠PT）：`Set-Cookie3: name=value; path=...; domain=...`，
  用正则 `Set-Cookie3:\s*([^=]+)="?([^";]*)"?;` 提取。
- **Netscape 格式**（SunnyPT）：制表符分隔 7 列，第 6/7 列是 name/value；
  注浏览器时同时设 `domain` 和 `.domain` 两种。
- **DiscFan / TL / PigGo 的规则都在独立 wiki 域名**，主站 `rules.php` 只是个跳转提示。

## 九、抓取方法与覆盖情况

### 第二轮补充（2026-09-28）

**新增抓到**：
- **TorrentLeech 官方 Wiki** `wiki.torrentleech.org`（DokuWiki，**48 页全抓**）——
  含 siterules / hnr / everything_about_warnings / vpn_usage / qbit_dht /
  seedboxes.all.you.need.to.know / reporting_a_seedbox / tl_points / user.ratio /
  user_classes / what.do.i.do.if.i.am.banned 等。
- **M-Team 官方 Wiki** `wiki.m-team.cc`（Wiki.js，63 页）——GraphQL 列目录 + HTML 取正文
  （★ 注意：GraphQL 的 `singleByPath` 需 `locale:"zh-tw"`，且内容读取需鉴权，
  所以正文要跑 HTML 路径）。
- **DiscFan 官方 Wiki** `wiki.discfan.net`（Wiki.js，但**只有 3 页**，站点自己还没建好）。
- **PANDA** rules.php 12160 字 + faq.php 18202 字（用 LWP-Cookies-2.0 格式 cookie）。
- **海棠PT** rules.php 5888 字 + faq.php 13235 字（cookie 现在
  `~/.pt-sessions/state/htpt_cookies.txt`）。
- **HDFans / SJTU葡萄 / 冬樱** rules.php **公开可读**（无需登录，urllib 即可）。

**仍未拿到**：
- **PigGo wiki** `wiki.piggo.me`：脚本直连回 **HTTP 468**（SafeLine 拦截），
  用浏览器访问则回 **Unauthorized**（wiki 需单独登录，与主站会话不通用）。
- **SunnyPT**：Next.js SPA，`/api/v1/rules` 返回的是外壳 HTML，需浏览器渲染。
- **BYR**：直连 403（教育网站），NAS 代理 `127.0.0.1:7890` 已失效（返回空）——
  **该代理当前出口是美国 VPS，对教育网站无效**。

**cookie 格式坑**：
- PANDA / 海棠PT 的 cookie 文件是 **LWP-Cookies-2.0**（`Set-Cookie3: name=value; ...`），
  不是 Netscape 也不是 JSON。用正则 `Set-Cookie3:\s*([^=]+)="?([^";]*)"?;` 提取。

### 第一轮（原）

**已抓到正文的站点**（20 站）：Audiences、CHDBits、HDDolby、HDHome、HDSky、HDU、
KEEPFRDS、MonikaDesign、OpenCD、OurBits、PTHOME、TTG、U2、UBits、大青虫、天雪、
织梦 + M-Team（官方 Wiki 63 页）。

**未抓到**：PigGo（URL 编码路径 404，需重找）、DiscFan（页面仅 356 字）、
海棠PT（会话过期，抓到登录页）、朱雀（另有 zhuque.md 专档）、
HDFans / PANDA / SJTU / 冬樱 / SunnyPT / TorrentLeech / BYR（无浏览器档案，纯脚本站）。

**重新抓取**：
```bash
cd ~/safeline-research
python3 pt_fetch_wikis.py <批次号>     # 批次 1-20 对应上表 SITES 列表
python3 fetch_mteam_wiki2.py           # M-Team 官方 Wiki（63 页）
python3 make_wiki_digest.py            # 生成 digest/*.md 摘要
```
