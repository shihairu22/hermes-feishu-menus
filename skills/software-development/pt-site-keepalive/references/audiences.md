# Audiences.me 登录与签到

- 站点：`https://audiences.me`；登录页 `/login.php`；签到页 `/attendance.php`；成功后首页 `/index.php`
- 账号与 M-Team 相同（用户名 `PTUSER`）；密码从本机 M-Team `.env` 读取，不在聊天里索取或复述
- 会话目录曾用：`~/.pt-sessions/audiences-login-session`（Camoufox 持久化 profile）

## 登录流程

1. 普通 Hermes 浏览器会卡在 Cloudflare「请验证您是真人」，点验证框通常过不去
2. 用 Camoufox 打开 `/login.php` 才能到真正登录表单
3. 表单：`input[name=username]`、`input[name=password]`、两步验证 `scode`（未设置可空）、图形验证码 `imagestring`（图在 `img[src*="image.php"]`）
4. 图形验证码 OCR 不可靠，会报「图片代码无效」；正确做法是截验证码图、识图后在**同一会话**填入再提交
5. 连续失败 20 次会封 IP，不要盲试
6. 成功判据：跳到 `index.php` 且页面出现用户名（该站用户栏不一定有「退出」二字）

## 签到流程

1. 保持同一 Camoufox 持久化会话，打开 `https://audiences.me/attendance.php`
2. 若页面已有「已签到 / 签到成功 / 本次签到奖励已发放」，不要再点按钮
3. 否则点 `a[href*="attendance.php?action=sign"]` 或文案含「签到」的按钮
4. 成功时页面会出现「签到成功」和「本次获得爆米花」；顶部可能显示「已签到 +N」

## 不要回归

- 不要用普通浏览器硬点 Cloudflare 复选框当主路径
- 不要把验证码 OCR 失败后的空字符串提交（浪费失败次数）
- 不要把密码写进聊天或一次性脚本长期保留
