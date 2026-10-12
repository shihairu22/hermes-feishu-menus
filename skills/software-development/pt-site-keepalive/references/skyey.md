---
name: skyey
description: 天雪 Skyey Snow (skyey2.com) 登录保活：Discuz 魔改站，skfaid 反爬令牌，无签到
---

# 天雪 Skyey Snow（www.skyey2.com / skyeysnow.com）

主打日本动画的私有 PT，**Discuz! X3.4 魔改**，前置 Cloudflare。
凭据**与馒头一致**（用户名 `PTUSER`），从 M-Team 的 `.env` 读取（`MTEAM_USERNAME` / `MTEAM_PASSWORD`）。

- 登录尝试：**5 次**（登录页显示 `5 TRY REMAINED`），用完封 IP → **只提交一次**。
- 无图形验证码、无 2FA。
- 站点规则：「新种和很多老种都是 Free，只要不做 H&R 生存很容易」。

## 1. 登录

表单：

```
POST /member.php?mod=logging&action=login&loginsubmit=yes&loginhash=<随机>
  formhash=<8位hex>      hidden
  referer=/              hidden
  skfaid=<64位hex>       ★ JS 现算的反爬令牌，必须带着提交
  loginfield=username    select（隐藏）
  username / password
  cookietime=2592000     勾上「AUTOLOGIN」保 30 天会话（★ 务必勾）
  loginsubmit=true       按钮
```

### ⚠️ skfaid 不是蜜罐，是必填令牌

HTML 源码里 `skfaid` 的 `value=""`，但**页面 JS 会把它填成 64 位十六进制**（实测 `AD844509D8E253D5...`）。
把它当蜜罐、提交时留空 → 登录必然失败。**提交前校验它匹配 `[0-9A-Fa-f]{32,}`，不匹配就中止**。

### 旧脚本：`scripts/skyey_login.py`（已归档 `_research/_superseded/`；现行 = `skyey_http.py`）

两个 Playwright 坑必须避开：

| 坑 | 现象 | 解法 |
|---|---|---|
| 页面有资源长期挂住 | `goto(wait_until="domcontentloaded")` 60 秒超时 | 改 `wait_until="commit"` + `wait_for_selector("input[name='username']")` |
| 点击等待导航 | `click()` 卡在「performing click action」15 秒超时 | 用 `page.evaluate` 里 `button.click()` / `form.submit()` 直接提交 |

提交前硬校验：用户名相符 + 密码长度相符 + `cookietime` 已勾 + `skfaid` 为 64 位 hex。

**成功判据（两个都要看）**：
- 出现 cookie **`rkvl_2132_auth`**（实测 4 秒内出现）
- 页面用户栏出现 `PTUSER |我的 |金币: N |消息 |提醒 |连接性 | 设置` + `积分: N |用户组: Lv.N ...`

> 注意：该站成功页面**没有「退出」字样**，用「退出/控制面板」当判据会得到假阴性（踩过）。

持久档案：`~/.pt-sessions/skyey-login-session`。

## 2. 没有签到，也没有任务

- `/plugin.php?id=dsu_paulsign:sign` → 「**插件不存在或已关闭**」（DSU 签到插件不存在）
- `home.php?mod=task` → 「**任务关闭**」

所以天雪**不进入「签到pt」例行**，只需保活。

## 3. 保活方式：模拟下载字幕

社区脚本 `nuthx/auto-sign` 对天雪用的是「模拟下载字幕」（而不是签到）：

1. 打开字幕区 `forum.php?mod=forumdisplay&fid=75`（**字幕区(新)**，233 主题）
2. 取帖子列表 `tbody[id^='normalthread_'] a.s`
3. 进帖子，找附件链接并 GET 一次（模拟下载）
4. 读积分/金币核对

**附件结构（新版字幕区，与旧版不同）**：

```html
<dl class="tattl">超时空辉夜姬.2026.BD.Disc02.CHS.zip  1.8 MB, 下载次数: 56</dl>
<a id="aid20002" href="forum.php?mod=attachment&aid=MjAwMDJ8Mzk0YzQ0Mzd8MTc5MDQ0OTcyMHw2OTU5Mnw2NzUyMQ%3D%3D">
```

选择器：`dl.tattl` + `a[id^='aid']`。
**社区脚本用的 `#filelistn + div a` 在本站已失效**（`#filelistn` 不存在）。

相关版块：字幕区(新) fid=75 ｜ RAW/Rip fid=10 ｜ RAW/ISO fid=11 ｜ 活动&启事 fid=36 ｜ 水区 fid=8。

### 实测（2026-09-26，保活脚本 `scripts/skyey_keepalive.py`〔旧浏览器版，已归档；现行 = `skyey_http.py --stage3`〕）

- **下载动作 = 带 referer（帖子 URL）GET 附件链接**：
  ```python
  page.request.get(dl_url, headers={"referer": post_url}, timeout=60000)
  ```
  实测返回 `200`、`content-type: application/octet-stream`、`1,890,642` 字节，
  **服务器「下载次数」每次立即 +1（实测 56→57→58→59，共 3 次）** —— 这是下载被记录的硬证据。
- **附件免费**：下载前后 `金币 440` / `积分 79345` 均不变。
- **⚠️ 字幕区附件分布**（2026-09-30 重扫修正）：部分帖子走网盘不带附件，但**字幕区(新) fid=75 一版就能扫出 9 个附件**
  （tid=1299 五个 SubRenamer zip；tid=67521 三个「超时空辉夜姬 Disc02」分包；tid=67652 一个 Date A Live S3.zip）。
  **旧结论「只有 1 个」是旧脚本窗口截断造成的误判**——按 `<tbody>…</tbody>` 整块配对帖号就不会漏。
  备用来源池：**RAW/Rip fid=10、网盘区 fid=18**（`skyey_http.py --stage3` 候选不足时自动扩展）。
  **扫几个版块仍找不到就停，直接报告**，不要无限扫（旧探测：一般字幕区 fid=16、字幕工具交流 fid=71 基本无附件）。
- 列表页的附件图标**不可靠**（Discuz 该模板下 imgs 为空、仅靠 `attach` 关键字误命中），不能拿它筛选，还是要点进帖子查 `a[id^='aid']`。
- 下载地址里的 token（`aid=MjAwMDJ8...`）是 **base64 的 `附件号|hash|时间戳|uid|帖号`**
  （例：`20002|2d48012b|1790740788|69592|67521`），与当前会话/时间绑定，必须从刚打开的帖子页现取。
  **时间戳每刷必变 → 去重只能用第一个字段「附件号」**（用整串 token 或末段帖号做键会跨天失效）。

## 4. 状态基线（2026-09-26）

- 登录成功：`PTUSER`，金币 440，积分 79345，用户组 **Lv.5 大雪**
- cookie 前缀 `rkvl_2132_`；登录后共有 14 个 cookie（含 `rkvl_2132_auth`）

## 5. 纯 HTTP 版 `scripts/skyey_http.py`（2026-09-30，已转）

- **skfaid 之谜已解**：`/static/js/skfaid.js` = **FingerprintJS Pro v3.3.0**（"upgrade to Pro: fpjs.dev"）。令牌 = 指纹组件串联 + 时间种子混合哈希，输出 **64 位 hex**。
- **解法**：`scripts/skyey_fp.js` —— 在 Node（本机 v26 可用）里桩好浏览器全局（navigator/screen/document/canvas.toDataURL 等）后直接 eval 官方 skfaid.js → `skfaid().then(fp=>fp.get())` → `skfaId`。服务端无法核验组件真伪；实测**被接受**。
- 流程：`--stage1` 取登录页（formhash/loginhash/questionid）→ Node 现算 skfaid（格式校验 `[0-9A-Fa-f]{32,}` 不过即停）→ `--stage2` 提交（5 次额度，脚本结构上「只提交一次」）。成功判据：`rkvl_2132_auth` + 用户栏（**无「退出」字样**）。2026-09-30 实测一次过：Lv.5、金币/积分正常。
- `--stage3` 保活（**2026-09-30 已重写 = 候选池 + 历史去重随机换**，用户要求「附件别每天一样」）：
  - `_collect_source` 按 SOURCES 顺序扫版块（字幕区(新) 75 → RAW/Rip 10 → 网盘区 18），`<tbody>…</tbody>` 整块配对帖号收集候选
    （每项 = {key=`a<附件号>`, tid, label, url, ref}）；
  - 从「近 20 次未用过」的候选里**随机挑**（历史 `ka_aids`）；返回 HTML 的候选拉黑（`ka_blocked`）；下载上限 **25MB**（超出截断）；
  - 实测 2026-09-30：重写前 a528（11307B，连跑两次都是它）→ 重写后 9 个候选中选出 `a20013`
    （超时空辉夜姬…Disc02.CHS.V2.part2.rar，1,306,156 字节，octet-stream ✓，tid=67521）；
  - 状态：`~/.pt-sessions/state/skyey_state.json` 的 `ka_aids / ka_tids / ka_blocked / ka_last`。
- CF 仅被动 jsd 层，GET/POST 都不拦（与 TTG 不同）。

## 6. ⚠️ 字幕区附件「站点侧故障」（2026-10-06 起，保活退化为纯登录）

**症状**：字幕区(新) fid=75 的论坛附件全部返回 Discuz「**抱歉，该附件无法读取**」（HTTP 200 + text/html，
即 `attachment_nonexistence`：附件记录或物理文件读不到），帖子里「下载次数」不再增长。

**已排除「账号被拉黑」**（2026-10-09 实测取证）：
- 账号一切正常：Lv.5 大雪、金币 440、积分 79345、分享率 229.819、上传 2.24 TB、保种 117.69 Thh；无警告/违规通知。
- **小黑屋**（`forum.php?mod=misc&action=showdarkroom`）18 条封禁记录里没有 PTUSER（注意：页面头部有本人用户名，
  判定要只看 `id="darkroomtable"` 表体，别整页 grep）。
- 报错是通用「无法读取」，**不是权限类文案**（Discuz 权限不足会显示 `attachment_nopermission` 那一套）。
- **真实浏览器**（Camoufox，同一 cookie 注入）打开帖子点附件链接 → 同样这句 ⇒ 不是脚本/反爬/请求头问题。
- **站内他人同报**：灌水&讨论区 tid=67710（2026-10-08）「求助：下载字幕区的压缩包字幕文件时，他说该附件无法读取」，
  回帖称「新字幕区有 bug，等大佬们修复吧」。→ 站点侧问题。
- 时间线：2026-10-04 22:28 仍成功（a20013，1,306,156 字节 octet-stream），**2026-10-06 01:52 起全站候选全失败**。
- 站点本身活跃（首页「今日: N」有正常发帖量），只是该版块附件坏了。

**处理**：
- 保活＝纯登录保活即可（登录态一直有效）；`--stage3` 会白扫一轮并把候选全拉黑，**站点修好前不必反复重试**，每天例行一次。
- 判断是否恢复：GET 任一 `a[id^=aid]` 链接看是否回 `application/octet-stream`，或看帖内「下载次数」是否增长。
- 站内检索线索：`search.php?mod=forum`（先取 formhash）搜「附件无法读取」能直接找到同类求助帖。

**档案现状**：HTTP cookie 档 `~/.pt-sessions/state/skyey_cookies.txt` 有效；
持久浏览器档 `skyey-login-session` **已掉登录**（2026-10-09 打开帖子被重定向 `login.php`），别拿它当已登录档用。

**状态文件坑（已修）**：`--stage1` 原先整份覆盖 `skyey_state.json`，会把 `ka_aids/ka_tids/ka_blocked/ka_last` 保活历史冲掉
（2026-10-09 04:30 重登时实际发生过）→ 现改为读旧状态再 update 合并写入。
