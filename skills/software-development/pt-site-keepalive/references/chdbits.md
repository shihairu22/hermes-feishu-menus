# CHDBits 登录与签到

- 站点：`https://ptchdbits.co`（NexusPHP）；登录页 `/login.php`；提交到 `takelogin.php`；成功后首页 `/index.php`
- 账号与 M-Team 相同（用户名 `PTUSER`）；密码从本机 M-Team `.env` 读取（`MTEAM_USERNAME` / `MTEAM_PASSWORD`），不在聊天里索取或复述
- 会话目录：`~/.pt-sessions/chdbits-login-session`（Camoufox 持久化 profile）
- 普通浏览器可直连，不需 Cloudflare 绕过

## 登录流程（已实测成功）

1. Camoufox 打开 `/login.php`
2. 表单字段：`input[name=username]`、`input[name=password]`、`input[name=imagestring]`（图形验证码）、`input[name=imagehash]`（隐藏）、复选框 `logout`/`securelogin`/`ssl`/`trackerssl`（保持默认）
3. 验证码图：`img[src*="image.php"]`，形如 `image.php?action=regimage&imagehash=<md5>`，尺寸约 151×41
4. 提交：`input[type=submit]`
5. 成功判据：跳到 `/index.php`，页面出现「欢迎回来, PTUSER」和「退出」

## 验证码处理（已实测可行）

- 只截 `img[src*="image.php"]` 本体，**不要截整页**
- 用视觉模型读图，**两次独立辨认交叉验证**（原图 + 放大 5 倍后重读），结果一致再提交
- 实测：两次均得 `PG9AC3`，一次通过
- 放大做法：PIL `resize((w*5, h*5), Image.LANCZOS)` 后另存再读
- ⚠️ **错一次验证码会刷新，同一张图不能重复提交**；连续 10 次登录失败会封 IP

## 答题（bakatest）的坑 —— 必读

- **选项顺序每次刷新都随机打乱**，而且 **「value ↔ 文案」的配对随题目变化**：value 只是「该题内的选项槽位」，不是固定含义。
  → ❌ **绝不要硬编码 value**。把某一题的 `1 = 10毫米以下` 当成通则记下来，换个题就会选错（实测同一站不同题：`老年痴呆症=2 / 肠胃疾病=8 / 癌症=4 / 甲状腺肿大=1`，与降雨量那题完全不同）。
  → ✅ **每题都先把整题映射读出来，再按「文案」精确匹配取 value**：

```python
mapping = page.evaluate("""() => {
  const out = [];
  for (const r of document.querySelectorAll('input[name="choice[]"]')) {
    let label = '', n = r.nextSibling, hops = 0;
    while (n && hops < 4) {            // 每个 radio 的文案是自己的兄弟节点，逐个读才准
      if (n.textContent && n.textContent.trim()) { label = n.textContent.trim(); break; }
      n = n.nextSibling; hops++;
    }
    out.push({ value: r.value, label: label.slice(0, 60) });
  }
  return out;
}""")
# 归一化空白后**仅完全相等**才算命中；命中不到就返回不提交
picked = next((i for i in mapping if re.sub(r'\s+', ' ', i['label']).strip() == TARGET_LABEL), None)
if not picked:
    raise SystemExit(0)                # 宁可不答，也别赌索引
page.locator(f"input[name='choice[]'][value='{picked['value']}']").first.check()
```

- ❌ **不要用「容器文本匹配」选选项**：四个 radio 全在同一个 `<td>` 里，`closest()` 拿到的是同一段拼接文本，匹配会命中第一个 radio → 选错。
- ❌ **不要用「回答正确/答错」关键词判断结果**：规则说明里本身就写着“不会却回答**正确**额外获得…”和“**回答错误**，将扣除…”，会误判。
- ❌ **不要用「题目变没变 / 魔力值变没变」反推对错**：提交后站点会接着出下一道题（这是正常流程，不是答错的信号）；魔力值同时受做种积分持续增长影响，变动不可靠。
- ⚠️ **站点不给出个人判定**，只在页面上放「签到记录」总表（时间/用户/题号/回答/最后/连续/魔力）——表里能看到自己的行才有一点参考价值，且要重开页面才可能出现。
- ✅ **判定「今天答完了」看表单消失**：`input[name=questionid]` 不再存在、也没有新题，就是当日额度用尽。不要靠报错文案判断。
- 结论：**答题不确定性高，先问用户是否要答；不要在无法确认判定时反复重试**（每次提交都可能消耗当日机会或扣分）。

## 签到（2026-09-27 实测修正）

- 首页导航栏有「**每日签到**」入口（另有「21点」）→ `bakatest.php`
- ★ **签到 = 提交答题表单本身**。打开页面只会看到题目（不会有「今天已经签过到了」这类文案）；**提交后**才出现签到成功文案与记录行：
  - 成功判据：页面出现「**连续N天签到,获得X点魔力值**」；签到记录表里出现自己的行（`时间 用户 题目 回答 最后 连续 魔力`）
  - 已签到时再打开页面会直接显示「今天已经签过到了(已连续 N 天签到)」
- 表单 POST 到 `/bakatest.php`：`input[name=questionid]`（hidden）+ 一组 `input[name="choice[]"]` 单选 + `input[name=submit]`（提交）/ `wantchange`（仅可换一题）/ `wantskip`（不会）
- ★ **选项定位坑**：四个 radio 的**父元素文字都包含全部选项**（`parentElement.innerText` 无区分度）→ 必须用 **`radio.nextSibling.textContent`** 匹配选项文字。另外**选项顺序每次刷新都随机**，不能按位置取。
- 奖励：答对得 `连续天数 ~ 连续天数×2` 魔力值；答错扣 1 魔力且**该题会重考**；点「不会」得 5 魔力值。
- **用户已授权：直接自己答题，不用先问**（2026-09-27）。实测答「蚓无爪牙之利」（定语后置 vs 其余宾语前置）得 333 魔力。
- **例行走纯 HTTP `scripts/chdbits_http.py`**（浏览器流程只用于溯源）：`--stage1` 探登录态（已登录会直接说明，无需登录码）→ `--stage3` 抓题（打印 questionid / question / 4 个选项文案）→ `--stage4 <答案文案>` 提交。成功判据同浏览器版：页面出现「连续N天签到,获得X点魔力值」。
- **已答对的题**（一律按**文案**匹配选项，绝不记 value）：`银河护卫队1最后彩蛋出现一只鸭子，是谁？` → **霍华德**（Howard the Duck；提示语「漫威早期还拍过它的真人超级英雄电影」指的就是它）。

## 不要回归

- 不要把密码写进聊天或一次性脚本长期保留
- 不要在验证码上反复盲试（会消耗失败次数直至封 IP）
