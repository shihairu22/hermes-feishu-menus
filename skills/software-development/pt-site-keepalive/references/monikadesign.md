---
name: monikadesign
description: MonikaDesign 莫妮卡 (monikadesign.uk) 登录保活：UNIT3D 框架，无签到，易被 DNS 污染
---

# MonikaDesign / 莫妮卡（MD / MDU，`monikadesign.uk`）

中文私有 PT，以**动画**为主体（含日剧日影、ACG Live），基于 **UNIT3D**（Laravel）。
凭据**与馒头一致**（用户名 `PTUSER`），从 M-Team 的 `.env` 读取。

## 0. ⚠️ 容易被 DNS 污染 —— 先做 hosts 加固

用户明确提醒该站容易被 DNS 污染。用 DoH 拿真实 CF IP 写 hosts（与 U2 同一套手法）：

```bash
curl -s -H "accept: application/dns-json" \
  "https://dns.alidns.com/resolve?name=monikadesign.uk&type=A"
# 实测 2026-09-26：104.21.13.219 / 172.67.133.75
```

```
# /etc/hosts（先备份 /etc/hosts.bak.YYYYMMDD）
104.21.13.219 monikadesign.uk
104.21.41.35  anime-no-index.com
```

注意：`www.monikadesign.uk` **不解析**，只有裸域；别去加 www。

## 1. 域名说明

| 域名 | 用途 |
|---|---|
| `monikadesign.uk` | 主站（网页 + 登录） |
| `anime-no-index.com` | **Tracker 域名**（网页 `/login` 返回 404，不要当备站用） |
| `tracker.` / `daisuki.` / `daikirai.` `monikadesign.uk` | 备用 Tracker 域名 |

## 2. 登录（UNIT3D / Laravel）

```
POST https://monikadesign.uk/login
  _token=<40位>     CSRF，必须从登录页现取
  username / password
  remember          记住我（建议勾，得 remember_web_* cookie）
```

- **无图形验证码、无 2FA**。站点支持「通行密钥登录」（`#loginWithPasskey-button`），但脚本走密码。
- 脚本：`scripts/monika_http.py`（纯 HTTP，2026-09-30 转）；旧 `monika_login.py`（提交前硬校验 `_token` + 页面内 JS 点 `#login-button`）已归档。
- 持久档案：`~/.pt-sessions/monika-login-session`。

### 成功判据

- URL 通常离开 `/login` 跳到 `/`；**但实测登录成功后 `url_after` 仍可能停在 `/login` —— 这不是失败信号**，别只看 URL
- cookie 出现 **`monikadesign_session`** + **`remember_web_...`** + `XSRF-TOKEN`
- 导航出现用户名 `PTUSER` / 个人资料 / 设置

> ⚠️ **该站中文界面里没有「登出」二字**，用「登出/退出/Logout」当判据会得到假阴性（踩过）。
> 判据改成：**cookie（`monikadesign_session` + `remember_web_*` + `XSRF-TOKEN`）+ 导航/正文出现用户名或个人数据（分享率/上传量等）**。URL 可能停在 /login（实测），不单独作判据。

## 3. 没有签到

- `/bonus` → **404**（`The route bonus could not be found`）
- 导航里没有任何签到/打卡/每日奖励入口
- 社区配置（pre-dessert-sites）也写明 `"required": { "cookie": true, "sign_in": false }`

页面上那个 `bonus` 链接是 UNIT3D 的**积分商店**（`/users/<name>/bonus/transactions/create`），不是每日签到。

所以例行里对它做的是「**登录保活**」。

## 4. 状态基线（2026-09-26）

- 登录成功：`PTUSER`
- 上传 33.81 TiB / 下载 304.35 GiB / 分享率 113.77 / BON 9,056,001
- 导航：资源 / 求种区 / 字幕区 / 论坛 / 媒体中心 / 我的成就 / 死种区 / Top 10 / 投票
