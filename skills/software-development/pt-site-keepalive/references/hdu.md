# HDU（`pt.hdupt.com`）

杭电 PT（“高清有你，你有 UPXIN”），**NexusPHP 深度定制站**。2026-09-27 接入，例行第 20 站。
> **2026-09-30 更新**：已实现**纯 HTTP 登录**（`scripts/hdu_http.py`，urllib+LWPCookieJar；此前「必须 Camoufox，curl 永远登不上」的结论已推翻——根因是旧探测脚本未保持 cookie 会话）。下文 Camoufox 路径保留备用。

## 为什么 curl 登不上（原因已更正，别再归给「前端加密」）

登录页里确实能看到一段 bcrypt 代码，但它**位于 HTML 注释内**，是站点给「维护期临时密钥登录」用的**死代码**：

```php
<!-- $options = [ 'cost' => 10, 'salt' => "weloveupxinweloveupxinweloveupxin", ];
     $a = date("Y-m-d H", time()); $b = $a;
     $tempkey = password_hash($b, PASSWORD_BCRYPT, $options); ?>
     <script> function password() { prompt('站点维护中，请输入临时密钥登录', ''); } </script> -->
```

- 它按**小时**生成临时密钥、盐值硬编码在页面里，属站点运维功能，**与正常登录无关**；已被注释停用。
- **不要**再把它当成「密码在前端 JS 加密后才提交」的依据 —— 该说法已被实测推翻（表单就是 `POST takelogin.php` 的 `username` / `password` / `imagestring` / `imagehash` 明文提交）。
- curl/urllib 真正登不上的原因是**验证码与 imagehash/会话绑定**，以及**站点强制 cookie**。实测报错依次为：
  - 前几次：`失败 图片代码无效！不要返回，图片代码已被清除！`
  - 后面：`注意：你需要启用cookies才能登录或切换语言 [30] 次`
- **2026-09-30 更新（已推翻「curl 永远登不上」）**：根因确系**旧探测脚本未保持 cookie 会话**——`scripts/hdu_http.py`（urllib + LWPCookieJar）已实现**纯 HTTP 登录：空 jar 冷启动一次过**（验证码双路读 `7765G4` 被接受；分享率 13.251 / 签到次数 966）。另签到端点已挖出：`POST added.php`（body `action=qiandao`，出自 `common.js` 的 `qiandao()`）→ `hdu_http.py --stage4`。Camoufox 路径（下文）保留备用。

## 账号现状（2026-09-27 实测）

| 项 | 值 |
|---|---|
| 用户名 | PTUSER（**2014-12-27 注册的老号**）|
| 上传 / 下载 | 41.710 TB / 3.148 TB |
| 分享率 | 13.251 |
| 魔力值 | 138,514.6 |
| 邀请 | 11 |
| 签到次数 | 962 |

## 登录步骤（Camoufox）

1. 启动（**必须 xvfb-run**，否则报 `no DISPLAY environment variable specified`）：
   ```bash
   cd /tmp && MTEAM_NO_DELAY=1 xvfb-run -a --server-args="-screen 0 1280x900x24" \
     ~/.pt-sessions/venv/bin/python scripts/hdu_login.py
   ```
2. `Camoufox(headless=False, os="windows", humanize=True, persistent_context=True, user_data_dir="~/.pt-sessions/hdu-login-session")`
3. 打开 `login.php` → `fill` 用户名 → `type` 密码（delay≈60） → 尝试勾 `securelogin`
   - 已知无关紧要的异常：`is_checked('input[name="securelogin"]')` 会 30s 超时 → **不影响登录成功**，不要为它卡住
4. 导出验证码：canvas 取 `img[src*="image.php"]` 的 dataURL（比页面截图干净）
5. **验证码时效极短**（服务端存 memcached）：提交窗口按秒争 —— 实测 36.8s ✅ / 82.7s ✅ / 113.7s ❌「图片代码无效」；**目标 ≤60 秒**，压时办法见文末「验证码窗口极短」节
6. 提交：`form[action*="takelogin"] input[type=submit]`
7. 成功判据：URL → `index.php` 且用户栏出现「欢迎回来, PTUSER」+「退出」

## 验证码识图

- 黑字纯黑 `RGB(0,0,0)`（`(R<100)&(G<100)&(B<100)` 分离），彩色噪点
- **双路读**：视觉模型 + ASCII 点阵。易混对：**D/0**（左侧是否直竖）、**G/C**（右侧下部有无竖段）、B/8、**4/A**、**9/g**、**S/9**（S 左下角有底弧收尾、9 左下为空、右竖到底）
- 实测三道：`E2NF49`（第 5 位是数字 4、第 6 位数字 9）、`NE2R19`（两路一致）、`7765G4`（2026-09-30 纯 HTTP 首试过，两路逐位一致）

## 签到

- **不要找 `attendance.php`** —— 该站返回 404（`plugin_sign-in.php` / `plugin.php?id=dsu_paulsign:sign` 也全都 404）
- 签到入口在**首页用户栏的 `[签到]` 按钮**：
  ```html
  <span id="qiandao"><a href="#" onclick="javascript:qiandao('qiandao')">[签到]</a></span>
  ```
- 已签到后按钮变 `[已签到]`，用户栏同时显示 `签到次数：962`
- 例行做法：打开首页 → 用户栏是 `[签到]` 就点它（`page.query_selector("a:has-text('签到')")` 后 click，或直接 `page.evaluate` 里 `a.click()`），显示 `[已签到]` 即完成；已是 `[已签到]` 就跳过
- 参考：`mybonus.php` / `userdetails.php` 都是 200，但里面出现的“签到”只是导航栏文字，不能当签到页

## 脚本

`scripts/hdu_http.py` —— **纯 HTTP 首选**（无浏览器）：`--stage1` 取验证码（自动收集 `imagehash` + hidden 字段）→ `--stage2 <验证码>` 提交 → `--stage4` 签到（`POST added.php`，form body `action=qiandao`，返回消息 + `[已签到]`/`签到次数` 复核）；`--stage3` 为发现用（打印 qiandao 上下文）。登录段已实测；**签到段待未签日首跑**。

`scripts/hdu_login.py`（已归档 `_research/_superseded/`）—— Camoufox 后备两阶段：导出验证码 → 等 `/tmp/hdu_answer.txt` → 填入提交 → 输出账号信息 / 检查签到并按需点击；现行 = `hdu_http.py` 纯 HTTP。

### ⚠️ 验证码窗口极短（2026-09-30 实测）

- 提交超时报「**图片代码无效！不要返回，图片代码已被清除！**」（服务端 memcached）。实测：**36.8s ✅ / 82.7s ✅ / ~80s ✅（2026-09-30 纯 HTTP）**；**113.7s ❌ 已失效**——上界约 110s，目标仍压 **≤60 秒**。
- 压时办法：READY 后用**单次调用**「轮询等 png 出现 → 立即跑净化脚本 `scripts/captcha_clean_blacktext.py`（hdu 模式）」一气呵成，再直接写入答案；**不要**在窗口内安排视觉二次复核（多轮往返浪费时间）。
- 本字体**允许重复字符**（实测 `DN4N4G`，两对重复照过）——看到重复别自我怀疑。
- 圆环按站规读 **D**（字符集无 0/O）。
- `hdu_login.py`（已归档）曾打补丁：失败时 dump 页面正文 + JS dialog 内容（靠它才定位到「图片代码无效」根因）。
