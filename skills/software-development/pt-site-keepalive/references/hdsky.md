# HDSky 登录

- 站点：`https://hdsky.me`；登录页 `/login.php`；成功后首页 `/index.php`
- 账号与 M-Team 相同（用户名 `PTUSER`）；密码从本机 M-Team `.env` 读取，不在聊天里索取或复述
- 会话目录曾用：`~/.pt-sessions/hdsky-login-session`（Camoufox 持久化 profile）
- 连续失败 10 次会封 IP，不要盲试

## 登录流程（已实测）

1. 用 Camoufox 打开 `/login.php`
2. 表单：`input[name=username]`、`input[name=password]`、可选 `oneCode`（Two-step，未开启可空）、图形验证码 `imagestring`（图在 `img[src*="image.php"]`）
3. 图形验证码空提交会报「图片代码无效」并消耗失败次数；净化放大后**双路自读**（点阵+视觉），一致就在**同一会话**填入提交
4. 成功判据：跳到 `index.php`，页面出现「欢迎回来 , PTUSER」和「退出」
5. 首页有「[签到]」入口；例行里照常参与签到（流程见下节），用户栏已是 `[已签到(Showed Up)]` 就跳过

## 签到流程（部分实测）

1. 同一会话打开首页，点 `#showup`（文案「[签到]」），不是 `/attendance.php`（该路径是 File not found）
2. 弹出 layui 层「签到(Show Up)」：验证码图 `#showupimg`（同样是 `image.php?action=regimage`）、输入 `#imagestring`、按钮 `#showupbutton`（Let's Go）
3. 签到码历史上有连续两次「验证码错误(Wrong CAPTCHA)」的记录 → 双路自读（点阵逐字 + 视觉逐字）各自确认后再提交；读不定就**换图重读**（错一次图会刷新），不要连续盲试；自读确实读不定才把放大图发用户代读（用户要求优先自读）

## 验证码为什么容易识错

- 图很小（约 150×40），黑字 + 灰点噪 + 青/绿/黄/橙/品红色块盖在笔画上
- 字符是字母数字混排 6 位；易混：5/S、C/G/0/O/D、F/E、H/N、1/I、8/B
- Tesseract 即使用去色块、放大、psm 7/8/13 也对不上正确串，不能当主路径
- 视觉模型会给出看起来完整的 6 位串但仍然错（实测：CD1PBF、C98D15 都被站点判错）
- 错一次验证码会刷新；同一张图不能反复提交

## 正确识别做法

1. 只截 `#showupimg` / 登录页 `img[src*="image.php"]` 本体，不要整页
2. 先去掉高饱和色块、只保留深色低彩度笔画、放大 3–4 倍（`captcha_clean.py` 净化），再**双路自读**：点阵逐字 + 视觉逐字
3. 两路一致 → 同一会话填 `#imagestring` 提交；不一致 → 按字形判据/判别表裁决，仍不定就换图重读。**不要把「找用户确认」当默认步骤**（用户原话：「你自己识别」）；错一次即停手重读新图，不要连试

## 不要回归

- 不要把密码写进聊天
- 不要空验证码提交
- 不要在验证码读不定时连续盲试——先换图重读，确认后再提交

## 纯 HTTP 版 `scripts/hdsky_http.py`（2026-09-30，已转）

- 无 CF；登录页 /login.php 表单 POST takelogin.php（username/password/imagestring/imagehash/oneCode + 隐藏项自动收集）。
- `--stage1` 取验证码（`image.php?action=regimage&imagehash=`）→ `/tmp/hdsky_captcha.png` → `captcha_clean.py` 净化放大；`--stage2 <6位码>` 提交登录。
- **识读纪律**：视觉单路历史上有判错记录（CD1PBF、C98D15）→ 必须与点阵交叉；分歧先按字形判据裁决、读不定就换图；**自读确实读不定才升级用户**（用户要求优先自读）。登录码实测 `19G172` 一次提交即被接受。
- 2026-09-30 实测：双路一致 `19G172` **一次过**（分享率 1.569 / 上传 2.503 TB / 魔力值 2,578,815.6）；10 次额度未损。[已签到] 状态识别正常。
- **2026-10-02 签到弹层 HTTP 端点已打通（原待办完成）**：`POST image_code_ajax.php` 带 `action=new` → `{"success":true,"code":"<32位hex>"}` → 取图 `image.php?action=regimage&imagehash=<code>` → 读码后 `POST showup.php`：`{action:'showup', imagehash:<code>, imagestring:<6位码>}`（表单编码）→ `{"success":true,"message":N}`（N=本次魔力，连续天数=(N-10)/2+1）→ 打开 index.php 复核 `[已签到(Showed Up)]`。
  2026-10-02 实跑：点阵+视觉双读 `P53DN6` 一致、一次过、+10 魔力、复核通过。**全程纯 HTTP，签到不再需要浏览器。**
- 注意：Camoufox 档案 `hdsky-login-session` 的登录态已失效（2026-10-02 实测直接回登录页）；但 HTTP jar（`state/hdsky_cookies.txt`）仍有效且更持久——**以 HTTP 版为准**（浏览器路径仅当 HTTP jar 也失效且需重登时再考虑）。
