# HDFans（`hdfans.org`）

NexusPHP 站的**登录 + 签到**，2026-09-27 首次接入并并入「签到pt」例行（第 19 站）。

## 基本信息

- 域名 `hdfans.org`，**Cloudflare** 承载；国内解析正常（未污染，与 TL 不同），直连 1.2 秒可达
- **无 Cloudflare 挑战** → `urllib`/`curl` 即可完成登录，**不需要 Camoufox**
- 账号与其它站同一套（用户名 `PTUSER`），凭据仍从 `.env` 读取、不进聊天

## 账号现状（2026-09-27 实测）

| 项 | 值 |
|---|---|
| 上传量 | 138.406 TB |
| 下载量 | 10.077 TB |
| 分享率 | 13.735 |
| 魔力值 | 4,098,176.8 |
| 做种数 | 359 |
| 签到 | 第 1197 次，连续 4 天，补签卡 186 张 |

## 登录流程

1. `GET https://hdfans.org/login.php` —— 表单 `action=takelogin.php` `method=post`
2. 表单字段：`secret`(hidden，**实测为空串**)、`username`、`password`、`two_step_code`(可空)、`imagestring`(验证码)、`imagehash`(hidden)、`logout` / `securelogin` / `ssl` / `trackerssl`
3. 取验证码图：`GET image.php?action=regimage&imagehash=<imagehash>&secret=<secret>`
4. 提交时带上 **`securelogin=yes`**（这就是该站的「自动登录」，保证后续 cookie 持久）
5. **成功判据**：跳转 `index.php` + 页面出现用户名 + 存在 `logout.php`/「退出」+ **不存在 `name="username"`**（回登录页即失败）
6. 失败提示与其它 NexusPHP 站一样含糊（验证码错也报同一套词），所以**验证码没把握不要提交**

## 验证码识图（与 OpenCD 同类）

- NexusPHP regimage：文字**纯黑 `RGB(0,0,0)`**，干扰是彩色噪点 + 彩色几何块
- 直接颜色分离：`(R<100)&(G<100)&(B<100)`，610~620 个黑像素，六位字符边界清楚
- **双路交叉**：视觉模型 + ASCII 点阵逐字核对，两者一致再提交
  - 实测两轮都对得上：第一轮 `DCA6N8`、第二轮 `3P6HDM`
  - 点阵读法参考技能正文的 ASCII 打印片段（150×40 图，逐行 `#`/`.`）

## 签到

- `GET /attendance.php` —— **打开即自动签到**（与 HDHome、PTHOME 相同，无需 POST、无需按钮）
- 已签到文案：「这是您的第 N 次签到，已连续签到 X 天，本次签到获得 40 个魔力值」+「今日签到排名：M / M」
- 用户栏会显示 `[签到已得 40, 补签卡: 186]`
- 站点自带**补签卡**机制（点白色圆点补签），但例行只做当天签到即可
- 判定：页面含「第 N 次签到」或用户栏「签到已得」即完成，**不要再点**

## 脚本

★ **先试会话复用，别急着读验证码（2026-10-04 实测）**：`~/.pt-sessions/state/hdfans_cookies.txt` 里的 `c_secure_uid`/`c_secure_pass` 是**持久 cookie**，跨日仍有效。直接带这个 jar `GET https://hdfans.org/index.php`：无 `name="username"` + 有「欢迎回来」即已登录，再 `GET attendance.php` 就完成签到（实测第 1202 次签到、连续 2 天、+20，全程无验证码）。

反例（当次实测）：先走验证码路，`--stage1` → 点阵/视觉双读提交 **3 次全被回「图片代码无效！」**（失败页文案是「图片代码无效！不要返回，图片代码已被清除！」——**失败后码即作废，每次都得重新取图**）；同一账号换到会话复用 1 秒即成功。另外 `--stage1` 短时间连续取图多次后，站点会返回**退化成噪点的空图**（纯黑像素从 600+ 降到 380，点阵 `segs=0`，视觉也读不出字）——此时不要再提交，直接走会话复用。

`scripts/hdfans_login.py` —— 两阶段调用：

```bash
# 阶段1：取图（不提交，零消耗）
~/.pt-sessions/venv/bin/python scripts/hdfans_login.py --stage1
#   → 保存 /tmp/hdfans_captcha.png，打印 CAPTCHA_READY（此时用视觉+点阵读码）
# 阶段2：提交登录 → 看账号 → 签到
... scripts/hdfans_login.py --stage2 <六位验证码>
```

- 只在阶段 2 消耗提交次数，阶段 1 完全无害（可反复取图）
- 会话 cookie 落盘 `/tmp/hdfans_cookies.txt`，同日重复运行时可直接复用
