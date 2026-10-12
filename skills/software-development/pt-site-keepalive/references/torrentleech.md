# TorrentLeech（TL，torrentleech.org）

国外知名综合私有 PT（英文社区，0day/影视/剧集/游戏为主）。**与 M-Team 同一套账号密码**（用户名 `PTUSER`）。

## 1. 网络：DNS 被污染，必须走 hosts

国内解析被污染：DoH（阿里/doh.pub/DNSPod）返回的全部是伪 IP（`104.244.46.9`、`108.160.169.179`、`31.13.67.41` 等 Twitter/Facebook/Dropbox 段），系统解析还会给假 IPv6 `face:b00c:0:25de`。真实服务在 **Cloudflare** 后面（NS `nia/pablo.ns.cloudflare.com`）。

真实 IP（写入 `/etc/hosts`，已验证可用，TLS 证书 `CN=torrentleech.org`）：

```
172.66.134.33 www.torrentleech.org
172.66.134.33 torrentleech.org
172.66.134.33 wiki.torrentleech.org
```

- 备用 IP：`172.66.137.109`（同为 CF 泛播，实测同样 200）。
- **Cloudflare 按 SNI 路由**：即使分给该站的 IP 变了，连 CF 泛播 IP（172.66.x/104.2x.x/172.67.x 段）+ 正确 SNI 通常也能到达；逐个试比找“真实 IP”更实用。
- 注意：`104.20.76.38`、`172.67.33.94` 等历史 CF IP 现在**不通**（TCP 超时），别照抄旧记录。
- 排查顺序：`curl --resolve <域名>:443:<ip>` 试连 → `openssl s_client -connect <ip>:443 -servername www.torrentleech.org -brief` 看证书；TCP 通 + TLS OK 而 200 就说明只是 DNS 问题。

## 2. 登录（最简单的一个站）

- 表单：`POST /user/account/login/`，字段只有 `username` / `password`，**无验证码、无 2FA、无 CSRF token、无 cloudflare 挑战**；curl 直接 POST 即可，无需 Camoufox。
- 预取一次 `/user/account/login/` 建立 `PHPSESSID`，带 `-c/-b` cookie jar 提交，`-L` 跟随跳转。
- **成功判据（三条同时满足）**：首页出现用户名 `PTUSER` + 存在 `/user/account/logout` 链接 + **不存在** `name="login-form"`。不要只看“有没有跳转”。
- 失败重试成本低（无验证码配额），但仍应先确认字段齐全再提交。

## 3. 账号现状（2026-09-27 实测）

| 项 | 值 |
|---|---|
| 用户名 / 等级 | `PTUSER` / **Power User** |
| 注册 | 2023-04-23（受邀于 TORRENTLEECH，非用户邀请） |
| 上传 / 下载 / 比率 | 284.55 GB / 6.56 GB / **43.401** |
| TL Points | 3,541.14 |
| 邀请 | 5 |
| Seedbox | No |
| 成就 | 13/83（刚解锁 “Member for 3 years”，奖励 300 点） |

个人页：`/profile/PTUSER/`（`/user/index` 同内容），成就 `/profile/PTUSER/achievements`，市场 `/profile/PTUSER/marketplace`。注意 `/user/account/`、`/profile/`、`/rules`、`/faq` 这些路径都是 **404**。

## 4. 签到 / 保活

- **该站没有每日签到**，例行应做的是**登录保活**（登录一次即刷新 `Last visit`）。
- **TL Points** 靠做种时长/体积/做种人数/等级加成与成就获得；可在 marketplace 兑换上传量（1 GB=90 点，2.5 GB=180，5 GB=300，10 GB=540，100 GB=5,000，250 GB=12,000）。
- HnR：每个下载的种子都要回传到 **1:1 或达到该等级的最短做种时间**（`Registered` 10 天 / `Power User` 8 天 / `Super User` 7 天 / `Extreme User` 6 天…，FreeLeech 也算）。
- 最低整体比率 **0.4**（下载超 6 GB 后）；低于 0.4 先警告、7 天内修复，否则封号。违规下载会限制 slot。

## 5. 风险提示（重要，动手前先说）

- 站规明确**禁止账号共享**（“给家人以外的人在你的账号上下载”属违规）；VPN 页面也写明：账号可能因为“疑似他人使用/共享”被封。
- 因此**如果用户本人在欧洲也会登录同一账号**，让 Hermes 从国内家宽定期登录会造成**两地 IP**，有被判共享的风险——例行保活前必须与用户确认这一点（要么只用 Hermes 登，要么不纳例行）。

## 6. 复现命令

```bash
# 一次性登录探测（凭据从本机 M-Team .env 读取，不打印）
cd /tmp && python3 /tmp/tl_login_probe.py
# 逻辑：GET 登录页建 cookie → POST username/password → GET / 验证用户名 + logout 链接
```

wiki（也是 CF，需 hosts）：`https://wiki.torrentleech.org/doku.php?id=siterules`、`?id=user_classes`、`?id=hnr`、`?id=tl_points`、`?id=vpn_usage`、`?id=account_sharing`。
