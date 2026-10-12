# PT@KEEPFRDS 登录

- 站点：`https://pt.keepfrds.com`；登录页 `/login.php`；成功后首页 `/`
- 页面标题登录页为 `Starship`；成功后为 `首页 :: PT@KEEPFRDS`
- 账号与 M-Team 相同（用户名 `PTUSER`）；密码从本机 M-Team `.env` 读取，不在聊天里索取或复述
- 用户确认该站没有二次验证；表单有 `token`（TOTP），未设置时留空即可
- 会话目录曾用：`~/.pt-sessions/keepfrds-login-session`（Camoufox 持久化 profile）

## 登录流程（已实测）

1. 用 Camoufox 打开 `/login.php`
2. 表单：`#username` / `input[name=username]`、`#password`、可选 `#token`（TOTP）、提交按钮「登入」
3. 可能有 Cloudflare Turnstile（隐藏字段 `cf-turnstile-response`）；Camoufox 本次可过
4. 无图形验证码
5. 成功判据：跳到首页，页面出现「欢迎回来, PTUSER」和「退出」
6. **不签到**：用户确认该站不用签到

## 不要回归

- 不要把密码写进聊天
- 未设置 TOTP 时不要填 `token`
