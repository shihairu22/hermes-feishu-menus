# OurBits 登录

- 站点：`https://ourbits.club`；登录页 `/login.php`；成功后首页 `/index.php`
- 账号与 M-Team 相同（用户名 `PTUSER`）；密码从本机 M-Team `.env` 读取，不在聊天里索取或复述
- 用户确认该站没有二次验证；表单有 `2fa_code`（占位「如有设置则必填」），未设置时留空即可
- 会话目录曾用：`~/.pt-sessions/ourbits-login-session`（Camoufox 持久化 profile）
- 连续失败 10 次会封 IP，不要盲试

## 登录流程（已实测）

1. 用 Camoufox 打开 `/login.php`（本次 Cloudflare 可过，未装 CloakBrowser 也能进表单）
2. 表单：`input[name=username]`、`input[name=password]`、可选 `2fa_code`、提交按钮「登录」
3. 无图形验证码
4. 成功判据：跳到 `index.php`，页面出现「欢迎回来, PTUSER」和「退出」

## 签到流程（已实测）

1. 同一 Camoufox 会话打开 `https://ourbits.club/attendance.php`
2. 若已显示「签到成功 / 已经签到过了 / 签到已得」，不要再点
3. 成功文案示例：这是您的第 N 次签到，已连续签到 X 天，本次签到获得 Y 个魔力值

## 不要回归

- 不要把密码写进聊天
- 旧签到包曾写 OurBits 的 CF 对 Firefox 返 1034；本次 Camoufox 登录成功，不要据此默认必须 CloakBrowser，以实测为准
