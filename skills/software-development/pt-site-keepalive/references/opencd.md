# OpenCD `www.open.cd`

NexusPHP 站，与 M-Team 同一套账号密码。**无 Cloudflare**（`Server: nginx`），但**登录与签到都需要图形验证码**。

## 登录

- 登录页 `https://www.open.cd/login.php`，首页 `https://www.open.cd/index.php`
- 表单：`POST takelogin.php`
  - `username` / `password`
  - `imagestring`（验证码） + `imagehash`（隐藏）
  - 复选框：`logout` / `securelogin` / `ssl`(默认勾) / `trackerssl`(默认勾)
- 验证图：`https://www.open.cd/image.php?action=regimage&imagehash=<md5>`（**150×40**）
- 次数限制：`[ 11 ] 次連續登錄失敗將導致你的IP位址被禁用! 你還有 [11] 次嘗試機會`——验证码读错不扣次数，密码错才扣。
- 成功判据：URL 变 `/index.php`，正文出现 `<用户名> , 歡迎回來` + `[退出]`。
- 凭据来源：`~/.pt-sessions/.env` 的 `MTEAM_USERNAME` / `MTEAM_PASSWORD`。
- 持久化档案：`~/.pt-sessions/opencd-login-session`。

## 验证码识读：按颜色分离（重要技巧）

NexusPHP 的 regimage 是 150×40、**带彩色噪点**的图，直接用灰度阈值分割会被噪点淹没。

**关键：文字是纯黑 `RGB(0,0,0)`，噪点是彩色（如 `(237,150,150)` `(176,219,120)` `(239,188,134)`）。** 所以：

```python
from PIL import Image; import numpy as np
g = np.array(Image.open(png).convert('L')).astype(int)
dark = g < 100          # 纯黑文字 → 噪点全被滤掉，字符形状非常干净
```

实测一次就分出 776 个纯黑像素，6 个字符的笔画完全可读（而灰度阈值法得到的是噪声一团）。

**识读组合**：点阵图（上面方法）+ 视觉模型交叉。实测两者前 5 位完全一致（`A4RFN`），仅末位视觉判 `M`、点阵不确定（`H/N/M`）——按视觉取 `M`，服务器接受。

## 签到（两步：插件页 + 验证码）

1. 首页用户栏 `[簽到]` → `<a href="#" onclick="javascript:signin(this);">簽到</a>`（红色）
2. `signin()` 会加载 **`https://www.open.cd/plugin_sign-in.php`**（模态框/iframe）
3. 插件页内容：`签到` / `算了` 两个按钮 + 一个验证码图 + `imagestring` 输入框
   - 表单：`POST plugin_sign-in.php?cmd=signin`，字段 `imagehash` + `imagestring`
   - 验证图同样是 `image.php?action=regimage&imagehash=...`（150×40，同样颜色分离可读）
   - 直接点「签到」而不填验证码会弹 `请输入验证码`
4. 填好验证码后点按钮（`onclick="javascript:do_signin(this)"`）
5. **服务器返回 JSON**（在页面 body 里）：
   ```json
   {"state":"success","signindays":"0","integral":"10"}
   ```

### 实测样例

```
魔力值: 2,070,114.0 → 2,070,124.0   (+10，与 integral 完全一致)
用户栏: [簽到] → [查看簽到記錄]      ← 签到后的标记
```

**判定顺序（从硬到软）**：

1. **签到记录页 `https://www.open.cd/plugin_sign-in.php?cmd=show-log` 里出现当天日期** ← 最硬（记录页列「签到时间 / 签到人 / 连续天数」）
2. 用户栏变成 `[查看簽到記錄]`（签到前是 `[簽到]`）
3. 魔力值增加（增量通常等于 JSON 里的 `integral`）
4. ~~JSON 的 `state` 字段~~ ← **会误报，不能单独作准**

**实测过 `state` 误报**：接口返回 `{"state":"false"}`，但签到其实已经成功 —— 魔力值 2,072,685.3 → 2,072,763.0（+77.7）、用户栏变 `[查看簽到記錄]`、签到记录页出现当天记录。**判「失败」之前先看记录页**，不要因为一个字段就重复点签到。

**另一种情形：登录后用户栏已直接显示 `[查看簽到記錄]`（2026-09-30 实测）** —— 说明当天已签过（例行或早前会话完成）。此时再调签到不会有增量、`state` 可能为 `false`，属正常。**别重复提交**：用 `scripts/opencd_check_log.py`（只读）看最新记录日期是当天即定案。

签到记录链接就在用户栏那个 `[查看簽到記錄]`（`plugin_sign-in.php?cmd=show-log`）；记录页会列「签到时间 / 签到人 / 连续天数」。

## 数据（2026-09-26 首次登录）

| 项 | 值 |
|---|---|
| 用户名 | PTUSER |
| 分享率 | 8.115 |
| 上传量 / 下载量 | 4.777 TB / 602.81 GB |
| 魔力值 | 2,070,124.0（签到后）|
| 邀请 | 10 |
| H&R | 0 |
| 当前活动 | 555 |

## 脚本

- `scripts/opencd_http.py` — 纯 HTTP 登录+签到（三段式；2026-09-30 转）
- `scripts/opencd_login.py` / `scripts/opencd_do_signin.py` — 旧浏览器版（已归档 `_research/_superseded/`）
