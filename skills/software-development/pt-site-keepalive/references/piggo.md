# PigGo（猪猪）登录与签到

- 站点：`https://piggo.me`；登录页 `/login.php`；成功后首页 `/index.php`
- 账号与 M-Team 相同（用户名 `PTUSER`）；密码从本机 M-Team `.env` 读取，不在聊天里索取或复述
- 会话目录：`~/.pt-sessions/piggo-login-session`（Camoufox 持久化 profile）
- 验证机制：前端带 SafeLine WAF（雷池），Camoufox 渲染 2-4 秒后自动验证通过进入表单
- 二步验证：该站开启了 2FA（`input[name=two_step_code]`，占位符「如有设置必须填写」），需要 6 位 TOTP 动态码

## 登录流程（已实测）

1. 用 Camoufox 打开 `/login.php`，等待 SafeLine 质询完成跳入真实表单
2. 填写 `input[name=username]` 和 `input[name=password]`
3. 填入 2FA 动态验证码（`two_step_code`）
4. 提交登录，成功跳转到 `https://piggo.me/index.php`
5. 成功判据：页面出现 `欢迎回来, PTUSER[🆔:19717]` 及 `[退出]`

## 从零会话（cookie 被清后）的正确顺序 —— 先登录、再签到

- 干净档案直接跑 `piggo_signin.py`：`attendance.php` 会 **302 到 `login.php?returnto=attendance.php`**；而**登录表单本身就带 `two_step_code` 字段**，脚本的「有没有 two_step_code」检测于是把登录页误报成 `two_step_form=True` / `NEED_2FA`。**此时千万别写动态码** —— 脚本会把它填进登录表单并提交，等于用空用户名/密码登录，白费一个码。
- 正确顺序：① `nexusphp_login.py --site piggo`（配置表里 piggo 的 `need_2fa=True`）：填用户名/密码 → 打印 `NEED_2FA` → 等 `/tmp/nx_piggo_2fa.txt` → 填 `two_step_code` 提交；② 登录成功后再跑 `piggo_signin.py` 处理公告弹窗 + 签到。
- 判别口诀：**页面 URL 含 `login.php` = 还没登录**，先补登录。`piggo_signin.py` 已加守卫：检到登录页会直接输出 `state: need_login` 并以 exit 3 结束。

## 签到入口

- 首页顶部栏有 `[签到得魔力]`（悬浮菜单里的 `<a class="faqlink" href="attendance.php">`，直接 `.click()` 会超时，不要依赖点击）。
- ⚠️ **不要用无状态的裸请求直连 `attendance.php`**：直连会触发「异地登录安全验证 / 二级验证」拦截，页面只返回一个要求 2FA 的表单。必须用持久化 Camoufox 会话。

## 签到流程（已实测成功）

1. 持久化会话打开 `https://piggo.me/attendance.php`。
2. **先处理「重要公告」弹窗**：`.layui-layer` 里标题为「2026喜迎中秋国庆 收到 1 条的重要公告」，按钮「确定」初始带 `layui-layer-btn0 disabled` 类 + 文案「请等待 (10) 秒」。
   - 必须先**轮询等它去掉 `disabled` 类**（约 10–20 秒）再点，否则点击无效。
   - 点早了或没点就提交 2FA，页面会报「**错误 请阅读公告!**」——这个报错指的是公告，不是 2FA 码错，不要误判。
3. 公告确认后，2FA 表单（`#input-form-box`）出现：填 6 位动态码，提交。
4. 验证通过后页面标题变为「猪猪 :: 签到」，**自动完成签到**，无需再点按钮。
5. 成功文案：「签到成功 这是您的第 N 次签到，已连续签到 X 天，本次签到获得 Y 个魔力值」；用户栏魔力值旁会出现 `[签到已得N, 补签卡: N]`。

## 判定要点

- 成功判据：页面标题含「签到」且正文含「签到成功」+「本次签到获得」；魔力值数字会比签到前增加。
- 若看到「异地登录安全验证」标题或「忘记二级验证? 点击这里自助解绑」，说明 2FA 未过，需要用户提供动态码。
- 判定已签：用户栏出现 `[签到已得...]` 标记；否则仍显示 `[签到得魔力]` 入口。

## 登录 IP / 异地登录审计（用户问「看看我站点的登录 IP / 异地登陆消息」时照此做）

- **横幅**：首页/签到页出「你有 N 条新异地登陆！点击查看」，链接指向 **`messages.php?box=202`**（短讯箱的「异地登陆」分类）。这是站内**唯一的登录审计视图**——`/log.php` 要总版主及以上权限，普通用户打不开（原话「只有 总版主 及以上等级的用户才能查看日志」）。
- **消息格式**：「你于: <时间> 进行了登录操作。IP：<ip>，位置：<geo>。上次登录时间：<上一条时间>，IP：<ip>，位置：<geo>。」按「本次登录 vs 上次登录」的地理差异触发——从境外切回家里也会生成一条「回归」提醒。站点时间约北京时间（UTC+8），报给用户时按需换算（欧洲 = 减 6 小时）。
- **个人资料页** `/userdetails.php?id=19717`（点首页用户名进入）显示：**当前IP**（当前会话出口；家里会显示为路由 WAN 的 IPv6，`240e:3a3:...` 开头）、**BT 客户端 IPV4/IPV6**（NAS Transmission 上报的做种地址）、**最近动向**（最近访问时间）。
- **现成脚本 `scripts/piggo_seclog.py`**：一次读 ①box=202 全部消息（时间+IP+位置+上次登录）②资料页 IP 区块。运行：`cd /tmp && xvfb-run -a --server-args="-screen 0 1280x900x24" ~/.pt-sessions/venv/bin/python <脚本路径>`。
- ⚠️ **打开消息即标已读**，横幅计数随之递减直至消失——预期行为，不是异常。
- **判读**：家里出口 = IPv4 `117.90.15.0`（江苏电信）+ 路由 WAN IPv6 `240e:3a3:...`；境外 IP 用 `http://ip-api.com/json/<ip>?fields=status,country,isp,as,hosting,proxy` 复核性质（机房 `proxy:true` ≈ 机场/VPN 节点；运营商 CGNAT 的移动网络 ≈ 真实手机流量）。用户可能承认是「自己误代理」——核对无误后不必再升级为「密码泄露」结论。
- **抓取坑**：页面横幅是**相对 href**（`messages.php?box=202`），自动跟进前拼绝对 URL（`BASE + '/' + href`）；`javascript:` 开头的 href 直接跳过。
