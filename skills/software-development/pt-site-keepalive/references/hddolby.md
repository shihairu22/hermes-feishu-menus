# HDDolby 登录与签到

- 站点：`https://www.hddolby.com`（NexusPHP）；登录页 `/login.php`；提交到 `takelogin.php`；成功后首页 `/index.php`
- 账号与 M-Team 相同（用户名 `PTUSER`，UID 37370）；密码从本机 M-Team `.env` 读取，不在聊天里索取或复述
- 会话目录：`~/.pt-sessions/hddolby-login-session`（Camoufox 持久化 profile）
- 计量单位叫「**鲸币**」

## Cloudflare

- 首页/登录页会先遇 Cloudflare 挑战（标题 `Just a moment...`），Camoufox 约 6 秒自动通过（轮询 2/4/6 秒后拿到正文）
- 不要“一看到有正文就退出”：挑战页本身也有正文，要等标题不再含 `just a moment`

## 登录流程（已实测成功）

1. Camoufox 打开 `/login.php`，等 `input[name=username]` 出现
2. 填 `input[name=username]`、`input[name=password]`
3. **图形验证码** `input[name=imagestring]`：图在 `img[src*="image.php"]`（约 151×41，`image.php?action=regimage&imagehash=<md5>`）。用视觉模型两次交叉验证（原图 + 放大 5 倍）后再填
4. **两步验证码 `input[name=2fa]`：本站已开启，必须填**（只填验证码会返回「失败 两步验证码未输入！」）
5. 提交：`input[type=submit]`
6. 成功判据：跳到 `/index.php`，页面出现「欢迎回来, PTUSER ( UID: 37370 )」和「退出」

## 两步验证码的时序（重要）

TOTP 30 秒一变，因此采用**两阶段等待**（脚本 `hddolby_login2.py`）：
1. 填账号密码 → 导出验证码图 → 打印 `CAPTCHA_READY` → 等识图结果文件
2. 填入验证码后 → 打印 `NEED_2FA` → **这时才向用户要动态码** → 写入文件后立即提交

这样动态码从「用户发出」到「提交」只有几秒，不会白白浪费尝试次数。

## ⚠️ 尝试次数有限

登录页显示 `[N] 次连续登录失败将导致你的IP地址被禁用! 你还有 [N] 次尝试机会`。实测**初始 20 次**，失败一次扣一次（首次因未填 2FA 失败，降到 19）。因此不要盲试。

## 签到

- 签到页：`https://www.hddolby.com/attendance.php`（用户栏入口文案「**签到得鲸币**」）
- **签到不需要验证码，也不需要两步验证码**——直接打开/点击即完成（2FA 只在登录时用）
- 成功页显示：`签到成功 这是您的第 N 次签到，已连续签到 M 天，本次签到获得 X 个鲸币。`
- 已签过时显示：`抱歉 您今天已经签到过了，请勿重复刷新。`
- 核实方法：对比首页/签到页的「鲸币 [使用]」余额是否增加（与奖励数额对得上才算成功），且用户栏的「签到得鲸币」入口消失
- 奖励规则：首次 20，每次 +2 至 300 封顶；连续 10/20/…/80 天额外 +10/20/…/80
- 是否签到以用户当场说明为准
