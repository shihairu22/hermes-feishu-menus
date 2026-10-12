# UBits 登录与签到

- 站点：`https://ubits.club`（NexusPHP）；登录页 `/login.php`；提交到 `takelogin.php`；成功后首页 `/index.php`
- 账号与 M-Team 相同（用户名 `PTUSER`）；密码从本机 M-Team `.env` 读取，不在聊天里索取或复述
- 会话目录：`~/.pt-sessions/ubits-login-session`（Camoufox 持久化 profile）
- 计量单位叫「U币」，另有「魔力大转盘」功能

## Cloudflare

- 首页会先遇 Cloudflare 人机验证（标题 `Just a moment...`），**Camoufox 约 6 秒自动通过**
- ⚠️ 探测时不要“一看到有正文就退出”——挑战页本身也有正文。要**等标题不再含 `just a moment`** 才算过
- 登录表单还有 **Cloudflare Turnstile**（隐藏字段 `cf-turnstile-response`）

## 登录流程（已实测成功）

1. Camoufox 打开 `/login.php`，等 `input[name=username]` 出现
2. 填 `input[name=username]`、`input[name=password]`；`input[name=two_step_code]`（两步验证）未设置时留空
3. **提交前必须等 Turnstile 令牌就绪**：轮询 `input[name="cf-turnstile-response"]` 的 value 非空（实测 2 秒、666 字符）
4. 提交：`input[type=submit]`
5. 成功判据：跳到 `/index.php`，页面出现「欢迎回来, PTUSER」和「退出」

## ⚠️ 尝试次数极少

登录页会显示 `[N] 次连续登录失败将导致你的IP地址被禁用! 你还有 [N] 次尝试机会`——实测**只剩 6 次**。因此：
- 令牌未就绪绝不提交
- 不要盲试密码或两步验证码

## 签到

- 签到状态看用户栏：已签到会显示 `[签到已得 N, 补签卡: N]`；未签则显示 `[签到得魔力]` 之类的入口
- 是否签到以用户当场说明为准
