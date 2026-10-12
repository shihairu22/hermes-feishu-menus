# 葡萄 PT（`pt.sjtu.edu.cn`）—— 上海交大

**Nexus Project** 框架（不是 NexusPHP！），2026-09-27 接入，例行第 22 站。**该站无签到 → 例行只做登录保活**。

## 站点特征

- 域名 `pt.sjtu.edu.cn` → **202.120.2.198**（教育网 IP，非 Cloudflare），**家宽电信可直连**（0.17s），**无 IP 限制**
- 登录表单极简：`<form method="post" action="takelogin.php">`，字段只有：
  - `username`、`password`
  - `hidden checkcode=XxXx`（**固定令牌**，不是动态的；直接从登录页 DOM 取就行）
  - `logout` checkbox
- **无图形验证码、无 JS 密码加密、无 CF** → `urllib` 直连即可（比 HDU 简单得多）
- ⚠️ **没有「自动登录/记住我」选项**（只有 logout checkbox），且站点提示 **15 分钟不活动自动登出** → 例行每次登一次就行，不必追求持久 cookie
- 站点提示「如果因长期未登录，账号不存在的用户，不会回复邮件」→ **长期不登录会清号，保活确有必要**
- 用户栏文本：`PTUSER … 等级：Insane User 分享率：30.126 上传量：17.210 TB 下载量：584.99 GB … 魔力值 (714911) … 邀请 (2)`

## 账号现状（2026-09-27 实测）

| 项 | 值 |
|---|---|
| 等级 | **Insane User** |
| 上传 / 下载 | 17.210 TB / 584.99 GB |
| 分享率 | 30.126 |
| 魔力值 | 714,911 |
| 做种 | 173 |
| 邀请 | 2 |

## 签到：没有

- `attendance.php` / `qiandao.php` / `signin.php` 全部 **404**；首页无任何签到链接
- `mybonus.php` 是魔力值页（200），不含签到
- 首页有「游戏」入口（未验证是否有积分机制，不影响保活）
- → **例行动作 = 登录一次保活**（刷新 last visit）

## 脚本

`scripts/sjtu_login.py` —— 单阶段：取 `checkcode` → 提交 → 打印用户栏与账号信息 → 探测签到入口（便于下次快速确认）。
