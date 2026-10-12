# HDHome（高清家园）`hdhome.org`

NexusPHP 站，与 M-Team 同一套账号密码。**无图形验证码、无 Cloudflare 挑战**，登录宽松。

## 登录

- 登录页 `https://hdhome.org/login.php`，首页 `https://hdhome.org/index.php`
- 表单：`POST takelogin.php`
  - `username` / `password`
  - `scode` — **两步验证码**，页面 placeholder 写明「未设置时不需要输入」，未开启就留空
  - 复选框：`logout`（15 分钟后自动登出）/ `securelogin`（限制 IP）/ `ssl` / `trackerssl`
- 站点语言可用 GET 参数切换：`/login.php?sitelanguage=...`
- 次数限制：`[ 20 ] 次连续登录失败将导致你的IP地址被禁用! 你还有 [20] 次尝试机会`——比 TTG 宽松，但同样**只提交一次，失败即停**。
- 成功判据：URL 变 `/index.php`，正文出现「欢迎回来, <用户名> (UID: xxxxx)」+「[退出]」。
- 凭据来源：`~/.pt-sessions/.env` 的 `MTEAM_USERNAME` / `MTEAM_PASSWORD`。
- 持久化档案：`~/.pt-sessions/hdhome-login-session`。

## 签到

**极其简单：`GET https://hdhome.org/attendance.php` 打开即自动签到**（不需要点按钮，页面上没有可点的签到控件）。

- 入口：用户栏的「**签到得魔力**」链接 → `/attendance.php`
- 已签到时页面显示：`签到成功 这是您的第 N 次签到，已连续签到 M 天，本次签到获得 X 个魔力值。`
- **用户栏标记变化**：未签到显示「签到得魔力」；签到后变为「魔力值 [使用]: N **(签到已得X)**」，签到入口消失。

### 实测样例

```
访问 /attendance.php 前: 魔力值 [使用]: 3,191,507.9    用户栏「签到得魔力」
访问后:                 "这是您的第 1241 次签到，已连续签到 194 天，本次签到获得 140 个魔力值。"
魔力值: 3,191,507.9 → 3,191,647.9  (+140，与消息完全一致)
用户栏: 魔力值 [使用]: 3,191,647.9 (签到已得140)
```

**判据**：页面出现「签到成功」+ 魔力值增加量等于消息里的数值（两处一致）。

## 数据（2026-09-26 首次登录）

| 项 | 值 |
|---|---|
| 用户名 / UID | PTUSER / 125276 |
| 分享率 | 70.550 |
| 上传量 / 下载量 | 717.937 TB / 10.176 TB |
| 魔力值 | 3,191,647.9（签到后）|
| 做种积分 | 2,375,654.2 |
| 当前活动 | 139 |
| 流量排名 | 90 / 1257 |
| 我的 HR | 0 |
| 邀请 | 0/1 |
| 连续签到 | 194 天（第 1241 次）|

## 脚本

- `scripts/hdhome_http.py` — 纯 HTTP 登录+签到（`attendance.php` 打开即自动签；2026-09-30 转）
- `scripts/hdhome_login.py` / `scripts/hdhome_signin.py` — 旧浏览器版（已归档 `_research/_superseded/`）
