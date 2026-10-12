# TTG（TotheGlory）`totheglory.im`

与 M-Team 同一套账号密码（用户确认），**登录无验证码**，但次数限制极严；**CF JSD 被动层存在——放行 GET、挑战 POST**（详见文末「纯 HTTP 实测结论」节）。

## ⚠️ 登录次数限制（最重要）

登录页写明：

> **[6] 次失败登录会导致你的 IP 被禁止。你还有 6 次登录机会。**

所以**绝不能盲试**：一次干净提交即可；失败就停下报告，不要重试。

## 登录

- 登录页 `https://totheglory.im/login.php`，首页 `https://totheglory.im/index.php`
- 表单：`POST takelogin.php`（`enctype=multipart/form-data`）
  - `username`（`#login-name`）/ `password`（`#login-pass`）
  - `passan`（安全问题答案，**未设置则留空**，页面提示「安全提问（未设置请忽略）」）
  - `passid`（隐藏，`0` = 未设置）/ `lang`（隐藏，`0`=简体 / `1`=繁体 / `2`=English）
- **页面同时有 4 个 `takelogin.php` 表单**（简/繁/英/韩各一个），字段 id 重复！填表必须**按 `input[name=lang][value="0"]` 定位到简体那个表单**再填。
- **无客户端密码哈希**（页面只有 jquery + bootstrap，无 md5/hash 代码），明文密码直接提交。
- 成功判据：URL 变 `/index.php`，标题 `TTG :: <用户名> 的个人页面`，正文出现「欢迎回来，<用户名>」+「退出」。
- 凭据来源：`~/.pt-sessions/.env` 的 `MTEAM_USERNAME` / `MTEAM_PASSWORD`。
- 持久化档案：`~/.pt-sessions/ttg-login-session`。

## 签到（AJAX，接口 `signed.php`）

用户栏是 `<span id="sp_signed">`：

- 未签到：`<a href="javascript:void(0);" id="signed"><b style="color:red;">签到</b></a>`
- 已签到：`<b style="color:green;">已签到</b>`

页面内联 JS：

```js
$("a#signed").click(function(){
    $.post("signed.php", {signed_timestamp: "<10位时间戳>", signed_token: "<32位md5>"}, function(data) {
        $('#sp_signed').html("<b style=\"color:green;\">已签到</b>");
        alert(data);
    });
});
```

**做法（最忠实）**：`page.click("a#signed")` 触发站点自己的 POST，并注册 `page.on("dialog", ...)` **捕获 alert 文本**——那就是服务器返回的结果消息（Playwright 默认会自动 dismiss，不注册 handler 就拿不到消息）。

备用做法：从页面 HTML 正则抓 `signed_timestamp` / `signed_token`，直接 `fetch('signed.php', POST)`。注意 **token 每次加载页面都会变**，必须当场取。

### 实测样例

```
点击前: 签到
弹窗:   "您已连续签到6天，奖励15积分，明天继续签到将获得16积分奖励。"
点击后: 已签到
积分:   1,158,511.60 → 1,158,526.60  (+15，与弹窗一致)
```

**判据**：用户栏变「已签到」+ 积分增加 + 弹窗消息三处一致才算真签到成功。

## 数据（2026-09-26 首次登录）

| 项 | 值 |
|---|---|
| 用户名 | PTUSER |
| 分享率 | 6.058 |
| 上传量 | 21.499 TB |
| 下载量 | 3.549 TB |
| 做种活动 | 165 |
| HP | 15 |
| 积分 | 1,158,526.60（签到后）|
| 邀请 | 0 |
| 连续签到 | 6 天 |

## 其它

- Cookie：`PHPSESSID` / `uid` / `pass` / `laccess` / `user_info_hash` / `cf_clearance`
- 站点支持「双重验证」（用户栏有入口），但本账号未开启——登录不需要动态码。
- 404 的路径：`attendance.php` / `sign.php` / `qiandao.php`（签到只走 `signed.php` AJAX）。

## 脚本

- `scripts/ttg_http.py` — 登录页勘察（只读；取代旧 `ttg_probe.py`，后者已归档）
- `scripts/ttg_login.py` — 登录（只提交一次，失败即停）
- `scripts/ttg_signin.py` — 签到（点击 + 捕获弹窗 + 复核积分）

## 纯 HTTP 实测结论（2026-09-30）：维持浏览器 ❌

- GET `login.php`：**放行**（完整真页面；CF 仅被动 jsd 脚本内嵌，无墙）。
- POST `takelogin.php`（multipart，字段/头全按浏览器）：**被 CF 拦截**（响应含 challenge-platform 特征；无任何会话 cookie 产生 → 应用层未收到，登录次数未消耗）。
- 判定：TTG 的 CF 对 POST 强制挑战 → **纯脚本不可行，登录保持 Camoufox**（`scripts/ttg_login.py`）。
- `scripts/ttg_http.py` 保留：`--stage1` 勘察（干净判定已修正：challenge-platform 单现≠墙）/ `--stage2`（如需再试，单次）/ `--stage3` 签到 token 解析（signed_timestamp/signed_token 提取可复用）。
- 不要为了「试试」重复 POST——额度 6 次，不值。
