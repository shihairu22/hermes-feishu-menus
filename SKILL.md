---
name: feishu-menus
description: Use when 配置或排查飞书菜单（悬浮菜单、卡片菜单、中文快捷命令）.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [feishu, bot-menu, interactive-card, quick-commands, console-ops]
    related_skills: [messaging-platform-operations]
---

# 飞书菜单全家桶（悬浮菜单 · 卡片菜单 · 中文快捷命令）

飞书里与“菜单”相关的能力共三件，先理解三者关系（一条链路）：

1. **机器人自定义菜单（悬浮菜单）**：控制台配置的入口按钮；用户点按 = **以用户身份发送一条文本**（响应动作也可为“跳转链接 / 推送事件”）。
2. **中文快捷命令 `quick_commands`**：Hermes 侧配置，把中文文本映射到真实命令（**文本级改写，不进模型，零 token**）。
3. **交互卡片菜单**（如“模型点选器”）：命令触发的富交互卡片——按钮点选、原地刷新、多级下钻（提供方→模型→切换）。

链路：点悬浮菜单 → 发出文本 → 网关命中 quick_commands / 原生命令 → 回复文本或交互卡片。

**分诊（“飞书卡片”类需求撞车时按这条走）**：① 改**菜单 / 快捷命令 / 入口** → 本技能；② 改**已发出卡片的原地刷新 / 补间** → `feishu-card-partial-update`。本技能只管 **Hermes 侧**菜单。

**本技能自带可直接安装的产出**（`assets/` + `scripts/`，见第五节），目标是任何人拿到就能在自己部署上复刻。

## When to Use
- 给飞书机器人新增/修改/删除悬浮菜单（官方无 API，只能控制台）
- 给某个命令做“点选卡片”式交互（不限模型切换）
- 中文命令不生效、菜单点了没反应、卡片点了没反应的排查
- 把整套菜单方案移植到新的飞书应用 / 新的 Hermes 部署

## 一、机器人自定义菜单（控制台）
### 代扫码登录（用户无设备登录时）
1. 打开/刷新：`https://accounts.feishu.cn/accounts/page/login?app_id=7&no_trap=1&redirect_uri=<urlencoded 应用管理页>`
2. 二维码画在页面 canvas：`canvas.toDataURL('image/png')` → base64 解码存 PNG → **立刻发送给用户**（时效仅几分钟）
   - ⚠️ **取到就原样发，别做任何重画/加白边/缩放**：多花的 1-2 分钟就足以让码过期，用户扫了会失败（实测踩过）。静区不够也照发，聊天客户端自带留白
   - ⚠️ 同一张码几秒内可重复取（canvas 内容不变）；**页面重载后会换新码**，旧码立即作废
3. ⚠️ **抓码后不要触碰那个标签页**：重导航/刷新会作废“待确认”的扫码会话（扫码后没人轮询 → 永远登录不上）
4. 用户扫码后，手机上如弹「确认登录」必须点确认；完成后该页签自动跳转进应用页
5. 控制台会话 **20–30 分钟**过期 → 扫码后一口气干完；被踢就重扫
6. **用 `agent-browser` 跑控制台，别用 `browser_exec`**（2026-10-01 实测）：先 `export AGENT_BROWSER_PROFILE=~/.feishu-console-browser`（配 `AGENT_BROWSER_SESSION_NAME=feishu-console`）→ 浏览器 daemon + 持久 profile，**登录态跨命令、跨会话存活**；`browser_exec` 的会话当天两次被整体重置到 about:blank、标签页清空，逼着反复扫码
   - 取码：`agent-browser screenshot canvas /path/qr.png`（canvas 元素截图，184×184）；码过期就 `agent-browser reload` 再截（新码 md5 必变，用 `md5sum` 校验是新的）
   - 其它常用：`snapshot -i`（无障碍树带 ref）、`set viewport 1600 1100`（视口调大，少踩坐标坑）、`scrollintoview <sel>`、`screenshot <sel> <png>`（**元素截图**——看清被内层滚动藏起来的面板/预览）、`eval`（可跑 fetch/XHR 调控制台内部 API）
   - 该页是**内层滚动**（`window.innerHeight == documentElement.scrollHeight`），`--full` 全页截图拍不到下半页，用元素截图或 `scrollintoview`
### 编辑器操作
- 入口：应用管理页 →「应用能力」→「机器人」→「机器人自定义菜单」区块，标题行右侧**铅笔图标**（直达 `https://open.feishu.cn/app/<APP_ID>/bot`）
- 开关：菜单状态=开启；展示形式=悬浮菜单 / 可切换菜单
- 容量：**≤5 个主菜单（=分组），每组 ≤10 条子菜单**（总 50）
  - 主菜单 = 容器（只有名称，textarea 字段）
  - 子菜单 = 一条命令：名称 + 响应动作（发送文字消息 / 跳转至指定链接 / 推送事件）
- 新建：主菜单条右侧 AddOutlined 加新组；点「新建子菜单」→ 弹窗「新建并转移」（原主菜单配置变为第一个子菜单）
- 改/删子条目：点预览里的条目行 → 右侧面板切到【子菜单配置】（名称输入框 + 删除按钮）→ 删除即时生效、无二次确认
- 删整组：点主菜单 → 【主菜单配置】（名称 + 删除）
- 保存：「保存」→ 出现「保存成功」toast = 草稿已存服务器
- ⚠️ **预览区里的主菜单块/子菜单行只能用 JS `.click()` 点**（2026-10-01 实测）：CDP 合成点击（`agent-browser click <sel>`）在这类块上无效（被遮挡/无命中），`document.querySelector(sel).click()` 才切得动弹层；切完用 `[aria-expanded="true"]` 校验归属（弹层 x 坐标 ≈ 主菜单块 x 坐标）
- ⚠️ **「新建子菜单」语义反直觉**：它新建一个**未命名主菜单**，并把当前主菜单**降级成它的第一个子菜单**（确认框：「主菜单『X』中的所有配置内容将被转移至新的子菜单」→「新建并转移」）。两个后果：① 新子菜单**不会自动选中**，必须再点它一下才切到【子菜单配置】；② 主菜单名字被搬进子菜单后**变空**，收尾必须回头给主菜单改名
- 推荐顺序（每组）：点「+」（AddOutlined）新建主菜单 → 命名 → 点「新建子菜单」（走转移）→ 给第一个子菜单改名 + 选「发送文字消息」→ 依次加其余子菜单（每个新子菜单**会自动选中**，直接改名即可）→ **最后回头重命名主菜单**。不这么做就会出现「名字张冠李戴」（实测：装着日常任务子菜单的块被命名成会话管理）
- 主菜单名称字段是 **textarea**，子菜单名称字段是 **input**（placeholder 都是「最多可输入 60 个字符」）
- 选「发送文字消息」后，面板里的 桌面端/移动端 链接字段消失（那是「跳转至指定链接」的字段）；展示形式切到「悬浮菜单」后，「默认展示（菜单/输入框）」整项消失——那是可切换菜单专属
- 删整组：点主菜单 → 右侧【主菜单配置】→「删除」，**无二次确认**、立即生效（2026-10-01 实测）
### 发布
1. 「创建版本」→ 进入 `/version/create`：**版本号自动预填**（上版本 +0.0.1）；更新说明默认“更新应用版本”，需替换为你的说明
2. 保存 → 版本详情页 →「确认发布」→ 弹窗「确认提交发布申请？」→ 再确认
3. 小范围自有应用提交即通过（控制台会标注是否免审核）
4. 验证：版本页「已发布」+ 审核结果「通过」+ 页面顶部「当前修改均已发布」
5. 客户端约 5 分钟同步；没出现就重启飞书 App
6. ⚠️ 坑：**「发布异常, 请刷新」多为假警报**——刷新后以版本页状态为准，别重复提交
7. ⚠️ 菜单条目「名称」= 实际发出的文本，**必须与命令逐字一致（含 `/`）**，且该命令要在 Hermes 侧存在（否则用户点了报 unknown command）

### API 直写（推荐：秒级铺完 50 项，不必点界面）
控制台前端有内部接口，可绕过「菜单无 API」的限制。**真正的门槛是请求头 `x-csrf-token`，不是 `fetch` 还是 `XMLHttpRequest`**——2026-09-30 做了 2×2 实测（同一读接口、同刻）：`fetch`+头 → `code:0`；`fetch` 无头 → `{"code":9499,"msg":"x-csrf-token not exist in header"}`；`XHR`+头 → `code:0`；`XHR` 无头 → 同样 9499。头值取页面全局 `window.csrfToken`（约 88 字符，登录态在就有）：
```js
const x = new XMLHttpRequest();
x.open('POST', '/developers/v1/robot/update_changed/<clientId>');
x.setRequestHeader('content-type', 'application/json;charset=UTF-8');
x.setRequestHeader('x-csrf-token', window.csrfToken || '');
x.setRequestHeader('X-Timezone-Offset', String(new Date().getTimezoneOffset()));
x.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
x.send(JSON.stringify({ menu: { botMenuEnable: true, botMenuDisplayStrategy: 3, botMenuConfig: [...] } }));
```
- 读：`POST /developers/v1/robot/<clientId>`，body `{}` → 返回 `botMenuConfig / botMenuEnable / botMenuDisplayStrategy / maxFloatingMenuCount / maxFloatingSubMenuCount`（**路径必须带 `/developers` 前缀**，漏了是 `404 page not found`）
- ⚠️ **在 `browser_exec` 里读回结果必须用异步 XHR**：把请求包成 `new Promise` 交给 `cdp('Runtime.evaluate', expression=..., awaitPromise=True, returnByValue=True)`；用 `js()` 发同步 XHR（`open(..., false)`）**实测返回空串**
- 写：`POST /developers/v1/robot/update_changed/<clientId>`，body **只包 `{menu:{...}}`**（前端包装层会把路径参数 `clientId` 从 body 里删掉）
- ⚠️ `menu` 里**必须带完整 `botMenuConfig`**；只发 `{botMenuEnable,botMenuDisplayStrategy}` 会失败（旧记录写作 9499，但那次没带 csrf 头，**真实原因未复核**）
- 条目字段（camelCase）：`botMenuID`、`defaultName`、`i18nBotMenuName{zh_cn}`、`menuContentType`（**1** 跳转链接 / **3** 展开子菜单 / **4** 发送文字消息）、`childNodes[]`
- 改已有项：复用其真实 `botMenuID`；**新增项用递增临时数字字符串**（前端 `"" + ++sc`，首个为 `"2"`），不能留空、不能给非数字占位
- 写完后**必须发布版本才生效**（见上「发布」）；发布走 API 共两步（2026-09-30 实测跑通 1.0.7）：
  1. 建版本：`POST /developers/v1/app_version/create/<clientId>`，body `{clientId, appVersion:'1.0.7', changeLog:'<更新说明>', remark:'', autoPublish:false, visibleSuggest:{}, blackVisibleSuggest:{}}` → `data.versionId`
  2. 提交发布：`POST /developers/v1/publish/commit/<clientId>/<versionId>`，body `{clientId, versionId, is_full_release:true}` → `data.isOk=true`，版本状态**立即变 `2`**（自建应用免审核）
  - **不要再调 `publish/release/<clientId>/<versionId>`**：自建应用没有这一步，实测 `{"code":10002,"msg":"参数不合法"}`（无害，但别当成失败重试）
- 版本状态（`POST /developers/v1/app_version/list/<clientId>` 返回 `data.versions[]`，字段 `appVersion / versionId / versionStatus / updateRemark / publishTime / createUser`）：`0` = 草稿、`2` = 已发布（当前生效）、`100` = 历史版本；建版本时填的 `changeLog` 回读时叫 `updateRemark`
- 其它内部接口：`/v1/manifest/get|upsert`（本应用类型恒返回 9499，仅 ISV/manifest 应用可用）、`/open-apis/block-kit/new_image/upload`（菜单图标，FormData `image` + `ClientID`）
- 9499 排查顺序（2026-09-30 更正）：**先看 `msg`**——`x-csrf-token not exist in header` = 漏头（最常见，别去改 payload）；其它 9499 才依次查 payload 结构/嵌套、clientId 位置、字段大小写、限流。`X-Requested-With`、`X-Timezone-Offset` 非必需（带上无害）

### 菜单精简/改版实战流程（2026-09-30 定稿）
1. **先取使用度证据**：`~/.hermes/logs/*` 里抓 `FeishuMenuBridge] rewrite '<名>'` 与 `card '<名>' sent`，按 `(秒级时间戳, 名)` 去重计数——**同一动作会被 hook 与 dispatcher 各记一次，原始计数约翻倍**，只比相对高低
2. **再用命令注册表逐项核验**：`hermes_cli.commands.COMMAND_REGISTRY` 的 `cli_only` / `gateway_only` / `argument_mode` / `args_hint` 是权威判据
   - `cli_only=True` 的命令**不能**做聊天菜单项（实测 `/cron`，聊天侧点了会被拒）
   - `args_hint` 非空且无结构化模式的，点了多半只回一句用法（实测 `/bg` 无参 `return usage`）
   - 例外：`/personality` 无参是**列出人格清单 + ✓ 标当前**，可作菜单项；`/model` 无参走本插件的选择器卡片
3. **选品铁律**：菜单只放「零参数就能用」的命令；需参数的（`/title`、`/resume`、`/branch`、`/loop`）手打或走卡片按钮
4. **与其它平台对齐**：Telegram 侧的 `platforms.telegram.extra.command_menu.priority` 名单是现成的「该放什么」参照；同一助手两边入口不一致属硬伤（本次据此补了「命令表」「重启」）
5. **改菜单结构 = 改插件 `GROUPS`**（插件表是唯一真源），并把 `_CODE_V` +1；热加载后看日志 `registered: N 命令 / M 卡片` 验证（N = 菜单项数 − 卡片数）。**给菜单项名称加图标不用改命令表**：入站改写会先精确命中、再退回剥掉开头图标后的名字
6. **自检脚本（改完必跑）**：逐项校验 `quick_commands[名].target` 的命令名在 `hermes_cli.commands.GATEWAY_KNOWN_COMMANDS` 里；再反向查 `COMMANDS` 里有没有缺别名的项
7. **发布**（2026-09-30 实测跑通 1.0.7）：API 直调更快——`app_version/create/<clientId>`（body `{clientId, appVersion:'1.0.7', changeLog:'<说明>', remark:'', autoPublish:false, visibleSuggest:{}, blackVisibleSuggest:{}}`）→ 拿 `data.versionId` → `publish/commit/<clientId>/<versionId>`（body `{clientId, versionId, is_full_release:true}`）→ `data.isOk=true` 即已发布（`versionStatus` 变 `2`）。UI 路径仍可兜底：`/app/<id>/version` →「创建版本」→ 版本号已预填（上版 +0.0.1）→ **更新说明 textarea 用 React 原生 setter + `input` 事件写入**（`Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(ta, txt)`；必填、上限 500）→「保存」→ 弹「确认提交发布申请？」→「确认发布」→ 版本页「已发布」+ 顶部「当前修改均已发布」
8. **改完 config 的别名需网关重载才生效**：`systemctl reload hermes-gateway.service`（ExecReload = SIGUSR1，**不换 PID**、等当前回合排空后才重启）
### 悬浮菜单项名称加 emoji（2026-10-02，Hermes 应用 1.0.9 已发布）

- **做了什么**：控制台菜单**结构不变**（5 组 × 23 项，type=3 文件夹 + type=4 子项），只把每一项名称加图标：
  `📊面板` `🖥系统` `📈用量` `🧰技能` `🌱PT` `❓帮助` ｜ `💬会话` `✨新会话` `📊状态` `🔁重试` `🗜压缩` ｜ `🎯任务` `📋任务` `⏹停止` `🏁目标` ｜ `⚙️设置` `🤖模型` `🧠推理` `🎭人格` `🔊语音` `🌙忙时` `🏠设主频道` ｜ `🔧运维` `📜命令表` `🏷版本` `⬆️更新` `♻️重启`。**卡片一律没动**（用户明确「不改卡片」）。
- **关键机制**：菜单项发出去的就是名字本身 → 带 emoji 的名字发出来也带 emoji（`✨新会话`）→ 插件必须认得。做法是 `_strip_lead_icon()`（`^[^\u4e00-\u9fa5A-Za-z0-9/]+` 剥开头图标/空白）+ 入站改写**先精确命中、再退回剥图标后的名字**：老中文名继续有效，以后加图标不必再动命令表。改完 `_CODE_V` +1（17），日志 `registered: 17 命令 / 6 卡片`。
- **发布顺序（重要）**：**先让插件热加载生效，再发布菜单**——否则点带 emoji 的菜单名会落进模型（老插件不认识这个名字）。热加载走控制套接字动词（不是重启、不中断当前轮次）：
  ```python
  from pathlib import Path
  from hermes_constants import get_hermes_home
  from gateway.control_socket import reload_gateway_plugins
  reload_gateway_plugins(Path(get_hermes_home()), timeout=60.0)
  # → {'reloaded': True, 'adapters_rewired': 3, 'activations': [... 'gateway_transforms': ['pre_gateway_dispatch'] ...]}
  ```
  存档脚本 `~/.hermes/cache/scratch/reload_plugins.sh`。
- **脚本存档**：`apply_hermes_menu_emoji.sh`（读备份 JSON → 加图标 → 写菜单 → 发 1.0.9）、`read_hermes_menu2.sh`（回读菜单 + 版本列表）、`verify_and_reload.sh`（图标剥离用例 + 23 个菜单项命中 + 热加载）、`revert_menu_bridge.py`（把插件回退到原样）。
- **两张主机卡分工（2026-10-02 去重）**：`build_panel_card` = 后台任务 + 模型 + 上下文 +「模型▾/新会话/停止/刷新」（**不再显示磁盘/内存/负载**）；`build_system_card` = 磁盘/内存/负载/运行 + 分区明细 +「刷新/详情/清理」（**「📊 详情」开的是 `build_system_detail_card`「🧾 系统详情」卡**；2026-10-08 修：它原先误指向「洞察」卡，点「详情」和点「洞察」是同一张）。原来两卡都画磁盘/内存/负载，用户点名「系统状态和控制台部分显示重复」→ 资源三件套只归系统卡。**改了卡片逻辑就要 `_CODE_V` +1**（本次 18→19），否则守卫 `_mk(cls, _MARKER_DO) >= _CODE_V` 判定「已装过」，分发器钩子不会重建——菜单点按会落进模型而不开卡（回退代码但版本号没变时最容易踩）。
- **走过的弯路（别再犯）**：曾把菜单压成「5 个叶子项、动作搬进卡片」做成 1.0.8（还顺手给卡片按钮加了图标）——**违反用户「不改卡片」**，已整体回退：插件回原样（只留图标剥离）、菜单回 5 组 × 23 项。要再提「叶子项 + 分组卡」方案，必须先拿到用户明确同意。
- **⚠️ 消息没进会话的坑**：2026-10-02 实测有一条 Feishu 消息（`不改卡片`）**只进了网关日志、没进当轮会话**（同一条日志里前后两条都正常）。所以当用户指令与自己的方案冲突时，**先去 `~/.hermes/logs/gateway.log` 搜 `Inbound dm message received` 核对最近几分钟的原文**，别只信会话里看到的那几条。
- **回退**：`hermes_menu_backup_20261002-005839.json` = 加图标前的原菜单；插件备份 `__init__.py.bak-20261002-005812`（原样）与 `__init__.py.bak-before-revert-*`。

9. **卡片里的任何「总数」都现算，别硬编码**：`_card(..., subtitle=...)` 曾留死数字 `5 组 × 10 项 · 共 50 项`，菜单瘦到 23 项后与卡内指标自相矛盾；改成 `f"5 组 × {sum(len(i) for _g, i in GROUPS)} 项"`，与卡内「菜单项」同一算法（改动只动渲染、不涉点击逻辑，`_CODE_V` 不必 +1）

### 斜杠确认卡（/new、/reload-mcp、切换昂贵模型）——按钮平台要精简卡面（2026-09-30）

- **来源**：官方 `_request_slash_confirm`（`gateway/run_busy.py`）把**同一段 message** 既交给按钮卡、又留给纯文本兜底。三个触发点：破坏性命令（`/new`、`/reset`、`/undo`、`/clear`，开关 `approvals.destructive_slash_confirm` 默认 true）、`/reload-mcp`、模型选择守卫（昂贵价格 / 数据策略）。
- **症状**：飞书卡面 = 标题 + 说明 + **与按钮重复的选项清单** + **「_文本方式：回复 /approve、/always 或 /cancel_」**。用户看到的是一张「让你回斜杠」的卡，而不是「点按钮」的卡 → 体感不如 exec 审批卡（`_send_exec_approval_prompt` 的卡面只有标题 + 说明 + 4 按钮，因为它的文本兜底是另一个函数，没混进卡面）。
- **修法（插件侧、零官方改动）**：`feishu-menu-bridge` 包装 `FeishuAdapter.send_slash_confirm`，渲染前用 `_lean_confirm_text()` 去掉尾部**斜体兜底行**（各语言都写作 `_…_`）与**数量等于按钮数的尾部 bullet 块 + 其「请选择：」引导行**。只动卡面；网关的纯文本兜底路径拿到的仍是原文，微信等无按钮平台不受影响。
- **别改 `locales/zh.yaml`**：那段文案就是给无按钮平台用的，改掉会让它们不知道要回 `/approve`。
- **测试**：`_lean_confirm_text` 拿 zh 真实文案跑三条（destructive / reload-mcp / model guard）→ 断言无 `•`、无 `approve`、标题与说明保留；反例（bullet 数 ≠ 按钮数）不误删；再真机发一张预览卡确认渲染（`~/.hermes/cache/scratch/send_lean_confirm_preview.py`）。

## 二、权限开通（控制台，扫码后一次干完）
- 入口：应用管理 →「权限管理」→ 表格上方「**去开通权限**」→ 右侧抽屉（抽屉锚在视口外，用 JS 直接点，勿依赖坐标）
- ⚠️ **坑1：抽屉默认停在「用户身份权限」标签页**。我们要的是 **应用身份权限（tenant_access_token）**。切页签必须对标签内层 `span` 与标签本身依次分发 `PointerEvent(pointerdown/up)` + `MouseEvent(mousedown/up)` + `click()`；只调 `.click()` 不生效
- ⚠️ **坑2：搜索框写入**用 React 原生 setter（`HTMLInputElement.prototype.value` 的 setter）+ `input` 事件 + `Enter`；且搜索**只返回部分结果**——`sheets` 查不到但中文「电子表格」能查到，优先中文关键词
- ⚠️ **坑3：行内 `input.checked` 不可信**（点完仍为 false）。唯一可信状态是抽屉底部「**已选：应用身份权限(N)**」计数
- 选完点「确认开通权限」。**免审权限即时生效**，不需要发布版本就能调 API
- **优先细粒度 scope**，别开 `drive:drive`（云空间全量）：云文档 `docx:document:create`、电子表格 `sheets:spreadsheet:create`、协作者 `docs:permission.member:create`、任务 `task:task:read`+`task:task:write`、日历 `calendar:calendar:readonly`+`calendar:calendar.event:create`
- ⚠️ **云文档必须配 `docs:permission.member:create`**：应用建的文档归应用所有，不把用户加为协作者，用户打不开链接

## 三、中文快捷命令 quick_commands（Hermes 侧）
- 位置：`~/.hermes/config.yaml` 顶层；**改完需网关重载生效**
- 两种类型：
  ```yaml
  quick_commands:
    # 文本改写直达原生命令：零 token、毫秒级（源码注释：bypass agent loop, no LLM call）
    用国内线: {type: alias, target: /model cn:xxx --provider custom}
    # 执行本机 shell（约 30s 超时），输出直接回会话
    磁盘: {type: exec, command: "df -h /"}
  ```
- 命令名：可全中文；解析仅做**小写化**；避免包含 `/`
- alias 的 target 必须是**已存在的原生命令**（可用 `/commands` 查看清单）
- 与悬浮菜单配合：菜单项名称 = 命令名 → 点按即触发；名称可带 emoji（插件会剥掉开头图标再匹配）
- 验证：直接发命令看回复；或离线用网关代码解析一遍（构造 MessageEvent → `get_command()` → 展开 alias）

## 三、交互卡片菜单（完整范例：模型点选器）
### 效果
`/model`（无参数）→「选择提供方」卡片 → 点提供方 → 模型列表（每页 10 个、可翻页、当前项带 ✓）→ 点模型 → 卡片原地「正在切换…」→「✅ 已切换」。全对齐 Telegram 的按钮选择器体验。

### 架构（三层，全部运行期打补丁；不改官方文件；官方更新后自动重挂）
1. **发送层**：网关对 `/model` 无参数时探测 `getattr(type(adapter), "send_model_picker", None)`；存在则调用它发卡片，否则退回文字列表。插件给适配器类挂上 `send_model_picker` 异步方法。
2. **点击层（关键）**：钩住 lark 库 `EventDispatcherHandlerBuilder.register_p2_card_action_trigger`——适配器每次连接都会构建事件分发器并经过这里；包装函数识别动作值 `{"hermes_model_pick": {...}}`，并用 `f.__self__` 取回适配器实例。**与连接时序无关**（任何时候安装都能接住点击）。
3. **保底层**：类级补丁（覆盖 `_on_card_action_trigger` / `send_model_picker`，类属性标记防重复）+ 守护线程（0.5s~10s 轮询补装）。应对官方插件**惰性加载**（bundled platform defer：平台启动时才 import）与热重载。

### 卡片按钮点击：四层拦截与「只认自己的按钮」（2026-09 实测，踩坑最多的一处）
官方适配器的卡片点击链路有两个入口，**只补类方法是不够的**：
- `_on_card_action_trigger`：`connect()` 时以**绑定方法**注册进 lark 分发器 → 绑定方法在注册那刻就固定，之后打类补丁**改不到它**；
- `_handle_card_action_event`：WS 卡片动作**根本不走它**（补了也没用，实测点击仍落到官方通用路径变成未知命令 `/card`，回复因 message_id 非法静默失败 `99992354`）。

可靠做法 = **在 SDK 事件总入口上拦**：
```python
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler as EDH
orig = EDH._do_without_validation          # 所有事件（含卡片动作）的唯一入口
# 补丁里：解析 payload（bytes JSON）→ header.event_type == "card.action.trigger"
#          → event.action.value 命中自己的键 → 执行副作用 → return {"code": 0} 短路
def _patched_do(self, payload): ...
EDH._do_without_validation = _patched_do
```
为什么它一定生效：`ws/client.py` 每帧都调 `self._event_handler._do_without_validation(pl)`，**方法在调用期按实例的类查找**，与分发器何时构建、何时注册无关。
- 拿回适配器：`handler._callback_processor_map["p2.card.action.trigger"].f`。**若 `f` 是我们包装过的普通函数**（没有 `__self__`），注册包装时必须挂上引用（如 `wrapped._hermes_adapter = adapter`），再兜底扫 `f.__closure__`
- 只需副作用（发卡/撤回/注入命令）时返回 `{"code": 0}` 即可；想原地更新卡片才需要同步响应
- ⚠️ **`gc.get_objects()` 扫不到线上适配器实例**：网关进程调用过 `gc.freeze()`（冻结对象不再由 `gc.get_objects()` 返回），启动时创建的适配器全在里面 → 鸭子类型也扫不到。拿活对象的可靠途径是 `pre_gateway_dispatch` 钩子的 `gateway` 参数（每次入站都补一次补丁，10s 节流）
- ⚠️ **多次热加载会留下多份插件模块实例**（各有自己的 watcher 线程），旧实例会不断把旧补丁覆盖到新补丁外面 → 版本标记用 **int 子类守卫**（`__eq__` 对 ≤ 自身版本号都返回 True），旧实例即判定「已安装」而停手，新版本仍能升级
- 已经装好的分发器**不要重建**（rewire）：分发器层拦截已即时生效，重建反而可能换上由旧包装器构建的分发器

### 卡片回调「没反应 / 客户端报 200671」的排查顺序（实测有效）
飞书客户端交互失败时会弹 `出错了，请稍后重试 code: 200671` —— 官方定义是「卡片回调服务返回了非 HTTP 200 状态码」，长连接模式下等价于**客户端没拿到有效回执**。按下面顺序查，别一上来就怀疑回调配置：

1. **看原始帧**：在 `lark_oapi.ws.client.Client._handle_data_frame` 上挂观测（该方法是所有数据帧的入口，帧头 `type` + payload JSON 里的 `header.event_type` 都看得到）。
   - 卡片按钮点击在长连接里是 `type=event` + `event_type=card.action.trigger`（**不是** `MessageType.CARD` 帧——后者 SDK 直接 `return` 丢弃）；
   - 帧到了却没处理 → 是补丁层的问题；帧根本没到 → 才去查后台「事件与回调」配置。
2. **拦截层拿不到适配器**：日志出现 `card click: dispatcher has no bound adapter` 说明 `_callback_processor_map` 里的 `f` 不是绑定方法（被包装成普通函数，没有 `__self__`）。兜底：在 `pre_gateway_dispatch` 钩子拿到 `gateway` → 取活适配器后**存全局变量**（如 `_LIVE_ADAPTER`），拦截时用它。
3. **回执格式**：同步回执要返回官方 `P2CardActionTriggerResponse()`（官方适配器同款），裸 `{"code": 0}` 可能被判「响应体格式错误」。
4. **补丁链收敛**：多份插件实例反复给同一个类打补丁会把包装层叠到十几层，最终 `RecursionError`。安装时沿函数属性 `_hermes_orig` 回找到 SDK 原始实现再包一层，并在每次包装时写下 `_hermes_orig`。
5. **别重建分发器**：分发器层拦截对已连接连接即时生效，重建只会把坏补丁换上去。

### 卡片排版：手机宽度下的硬约束（实测）

飞书手机端卡片宽度固定 **302px**，可用内容宽约 **278px**（去掉 body padding 12px×2）。按这个宽度算，下面几条是踩过坑的结论：

| 坑 | 后果 | 正确做法 |
|---|---|---|
| 指标排 **1×3 三列** | 每格只剩约 65px 文字宽，「33G / 124G」折行、负载三个值被拆成两行（语义都变了） | 改 **2×2 网格**，每格约 119px，数值单行放得下 |
| 按钮塞 `column_set` 且 `weight: 0` | `weight` 必须 ≥1，非法值让列宽塌陷 → 中文被压成**竖排单字**，右侧还空一大片 | 删掉 `weight: 0` |
| 按钮用 `width: auto` | 每个按钮按内容宽自适应 → **四个宽度各不相同**，还会换行成两层 | 列用 `width: weighted, weight: 1` 等分 + 按钮 `width: fill` → 一行等宽 |
| 一行塞 4 个三字标签按钮 | 302px 下按钮内边距吃掉宽度，文字折行 | 标签压到**两字**（新建/状态/刷新/收起） |
| 按钮用默认 `size: medium` | 即使两字标签也被截成「新…」（Feishu 用省略号截断，不是折行） | 改 **`size: "small"`**（字号与内边距同时变小，实测一行四个两字标签刚好不挤）；仍紧就降到 `tiny` 或改成一行 3 个 |
| 用 `action` 标签 | schema 2.0 已废弃，直接报 `unsupported tag action` | 用 `column_set` + `flex_mode: flow/none` + `width: auto/weighted` |
| 卡片整体背景 | 固定白，改不了 | 用 `column.background_style`（`grey-50`/`blue-50`）+ `collapsible_panel.background_color` 做分层 |
| 组件间距靠 `hr` | 官方明确「大量分割线导致版面凌乱」 | 全卡 ≤1 条 `hr`，其余用 `body.vertical_spacing` + 块底差异 |

**只有 schema 2.0 才有** `background_style` / `body.padding` / `body.vertical_spacing` / `collapsible_panel` 的 `background_color` —— 1.0 卡片（`config.wide_screen_mode` + 根级 `elements` + `action` 标签）吃不到这些，要美化必须先迁到 2.0。

**`markdown` 元素不支持 `text_color`**（只支持 `text_size`），颜色要写在内容里：`<font color='grey-600'>`、`<text_tag color='green'>`。

### 卡片改版前的自检办法（看不到手机屏也能查排版）
把卡片 JSON 用 **302px 宽**渲染成 HTML 样张 → `google-chrome --headless=new --screenshot` 截图 → `vision_analyze` 逐条问「按钮是否竖排/等宽、数值是否折行、有无贴边」。

样张渲染器自己的坑（会把假象当成真问题）：
- **先 `html.escape` 再正则匹配**，且匹配「已转义」的标签（`&lt;font ...&gt;`）；`html.escape(..., quote=False)` 否则单引号变 `&#x27;` 匹配不到。
- 颜色名正则要用 `[\w-]+`，`\w+` 匹配不到 `grey-600`。
- 按钮 `width: auto` 要按**内容宽**（`flex:none; white-space:nowrap`），`fill` 才等分 —— 否则四个按钮全被等分压成竖排，误判成飞书的问题。

### 卡片交互协议（复用到其他卡片菜单）
- 按钮 value 携带动作：`{"hermes_model_pick": {"a": "p|pg|b|x|m", "pid": N, "i": 提供方序号, "mi": 模型全局序号, "pg": 页码}}`；`pid` 索引内存中的选择器状态
- **同步返回** `adapter._card_response(card_json)`：原地更新卡片（翻页/下钻零延迟）
- **异步结果**（切换完成后）：SDK `im.v1.message.patch`（`PatchMessageRequest`，PATCH）原地更新——对 interactive 走 PUT `message.update` 会报 `230001 invalid msg_type`（与菜单卡翻页同坑，见 menu-bridge `_patch_card`）；失败兜底发一条文本
- 卡片 JSON 结构：`config.wide_screen_mode`、`header{title{content,tag},template}`、`elements[]`（`{"tag":"markdown","content":...}` 文本行；`{"tag":"action","actions":[按钮们]}` 按钮行）；按钮 `{tag:button,text:{tag:plain_text,content},type:default|primary|danger,value:{...}}`；label ≤60 字符
- 状态管理：`{chat_id, message_id, providers, session_key, on_model_selected, current_*}`；1 小时陈旧清理；过期点按回「已过期」卡
- 固定“当前值”高亮：label 前缀 ✓ + primary 样式

### 宿主接口（Hermes 侧，其他平台适配器实现同样接口即可复用交互）
- 发送：适配器实现 `send_model_picker(chat_id, providers, current_model, current_provider, session_key, on_model_selected, metadata=None)`
- 回调：**三参** `on_model_selected(_chat_id, model_id, provider_slug)`（漏参报 `missing 1 required positional argument: 'provider_slug'`——实测踩过）
- 点按鉴权：`adapter._is_interactive_operator_authorized(open_id)`
- 斜杠确认卡：适配器实现 `send_slash_confirm(chat_id, title, message, session_key, confirm_id, metadata)`（按钮 value 用 `hermes_action: slash_once|slash_always|slash_cancel` + `confirm_id`；点按调 `tools.slash_confirm.resolve()`，把返回文本发回会话）。Telegram/WhatsApp 原生有，**飞书原版缺**（退化为纯文本、无法点按）——本地补丁已补齐。

### 部署清单（飞书 / Hermes）
1. 放插件：`~/.hermes/plugins/feishu-model-picker/{plugin.yaml,__init__.py,keeper.py}`（**源码在本技能 `assets/`，已与线上同步（见 `assets/feishu-model-picker/SHA256SUMS`）；改插件后必须把修复同步回 assets，否则重装会复现旧 bug**；或运行 `scripts/install-feishu-model-picker.sh`，同步状态可用 `scripts/check-assets-sync.sh` 对账）
2. 启用：`hermes plugins enable feishu-model-picker`（**用户插件白名单制**，会写入 config `plugins.enabled`）
3. 重载：`systemctl reload hermes-gateway.service`（SIGUSR1 优雅排空后重启；**不要用 restart**）
   - ⚠️ **重载≠插件被加载**：网关只在启动那一刻读 `plugins.enabled`；启用后若只 reload，插件可能根本没进网关（实测：网关 21:21 启动只加载了旧插件，新插件到 22:05 手动热加载才上）
   - ⚠️ **别被 CLI 日志骗了**：`hermes plugins list` / `plugins doctor` 里的 `[Xxx] registered` 行来自 **CLI 进程**；网关侧是否真加载，只看 `gateway.log` 里同一行 + `gateway.run_plugin_rewire: Re-wired plugin handlers on N adapter(s)`
   - ✅ **重启后确认「插件真进了新网关进程」的三条硬证据**（2026-10-05 实测固化，别再靠猜）：
     1. **日志落点**：插件 INFO/WARNING 写的是 `~/.hermes/logs/agent.log`，**不进 journald**——`journalctl -u hermes-gateway | grep FeishuMenuBridge` 空是正常的，别据此判定没加载。查 `agent.log` 里该进程启动时刻后的 `hook installed` 行，**行尾版本号 `(vN)` 就是已加载的真源**（`dispatcher hook installed ... (vN)` / `busy hook installed on GatewayRunner (vN)` / `batch hook installed on FeishuAdapter (vN)`）。
     2. **线程证据（最硬）**：`for t in /proc/<网关pid>/task/*; do cat $t/comm; done | sort | uniq -c` 里出现 `feishu-menu-bri` + `fmb-watchdog`（选单器是 `feishu-model-pi` + `fmp-watchdog`）＝模块已 import、`register()` 已跑。内核线程名只取前 15 字符。
     3. **版本/哈希**：`grep '^_CODE_V'` + `sha256sum` 对回滚点；`ps -o lstart= -p <pid>` 的启动时刻必须**晚于**插件文件 mtime。
   - ⚠️ **`health UNHEALTHY: {...'batch': None, 'sendfinal': False...}` 是假警报，别追**：短命 CLI 进程（`hermes plugins list/doctor/show`）也会 import 插件并跑巡检，此时 `GatewayRunner`/`feishu.adapter` 根本不在场 → 各家族 None、`sendfinal`/`ptgate` 因模块名不同源而 False → 必报 UNHEALTHY。`_patch_health()` 只用于打日志（唯一副作用是「连续 5 次全 None 强制重装」自愈），**全历史日志里 `health HEALTHY` 出现 0 次**。判别是不是 CLI 进程：看同刻上下文有没有 `hermes_cli.plugins: Plugin '...' registered ...` 行。**2026-10-05 补充：仪表盘进程（`hermes dashboard`，长命进程）同样 import 插件，且它不连平台 → `feishu.adapter`/`GatewayRunner` 不在 `sys.modules` → 家族全 None、`sendfinal`/`ptgate` False，也会打 UNHEALTHY**，所以「全 None」不能只往短命 CLI 上归。`_HEALTHCHECK` 触发文件（`~/.hermes/cache/scratch/menu_bridge_healthcheck.json`）是**谁先 tick 谁消费**，`health(file)` 读数同样可能出自仪表盘 → 拿到读数先**归属进程**再判读：查该进程自己的加载组里有没有 `adapter hook installed` / `busy hook installed on GatewayRunner`（有＝网关真身，无＝仪表盘或 CLI），别拿仪表盘的读数去追网关的锅。
   - 判据补充：网关进程内若巡检真的不健康，`_warn_once` 只在 `bad` 元组**变化**时再打一条 → 安装完成后再无新 UNHEALTHY 行 ＝ 该进程已健康。
   - ✅ **热加载插件（不重启网关）**：
     ```python
     import sys; sys.path.insert(0, "/usr/local/lib/hermes-agent")
     from pathlib import Path
     from gateway.control_socket import reload_gateway_plugins
     print(reload_gateway_plugins(Path(os.path.expanduser("~/.hermes"))))   # {"reloaded": True, "activations": [...]}
     ```
     `hermes plugins enable` 内部也会发这条控制套接字请求；`reloaded=True` + `gateway.log` 的 rewire 行 = 已生效（网关进程 PID 不变）
   - ⚠️ 铁律：**重载与发附件（图片/文件）分回合**——排空会掐断正在上传的附件
4. 验证 journal 三行（顺序必须早于飞书 WS 连接 `[Lark] connected to wss://`）：
   - `[FeishuModelPicker] lark builder hook installed`
   - `[FeishuModelPicker] registered; watcher started`
   - `[FeishuModelPicker] installed into hermes_plugins.platforms__feishu.adapter`
5. 自测：`scripts/feishu-model-picker-selftest.py`（7 项：卡片构建/翻页下钻/点击路由/补丁机制/lark 拦截/三参调用）
6. 真机：飞书发 `/model` → 点提供方 → 点模型；journal 出现 `click a=...`、`switch ... ok=True`

### 命令存在的权威校验（必做）
- 卡片按钮注入的斜杠命令、菜单项的改写目标，必须用 Hermes 权威命令表校验：`from hermes_cli.commands import GATEWAY_KNOWN_COMMANDS`（约 85 条）。`gateway/relay/command_manifest.py` 里的 `_cmd(...)` 只是子集（约 28 条），拿它当全集会误报「死按钮」。导入要用 venv python（tools python 缺 `ruamel`）。
- 未知命令会走 `gateway/run_inbound.py` 的 `Unrecognized slash command` 分支，只回一句「Unknown command」——用户点下去像没反应。实测已抓到一枚：系统卡「清理」注入 `/清理磁盘`，权威表里不存在。
- 按钮要触发「需判断/需确认」的动作时，不要注入斜杠命令，直接注入自然语言并写入约束（例：「清理磁盘：先只做只读盘点并告诉我能回收多少，等我确认再删」）。

### 诊断日志间隔异常小 = 多代守护线程
- 设定 20s 却实测每 4.2s 一条，不是节流写错，而是多个插件实例的守护线程同时在跑（重载后旧线程未退）。先数线程再改节流；自检上报要带 `threading.enumerate()` 的本插件线程计数（线程名要与创建时一致，否则永远为 0）。
- 热加载日志里可能出现 `AttributeError: partially initialized module ... has no attribute '<Adapter>'`；重载后必须回看日志确认出现 `registered: N 命令 / M 卡片`。

### 守护线程生命周期：keeper 单例（2026-09-30 定稿，**取代**「注入 SystemExit 退役旧代」）
- **别用异常注入退役旧代线程**：`PyThreadState_SetAsyncExc(SystemExit)` 会被网关的 `threading.excepthook`（`tui_gateway/server.py:82`，它记录一切线程异常）记成 `[gateway-crash] thread feishu-menu-bridge raised SystemExit`，并写进 `~/.hermes/logs/tui_gateway_crash.log` —— 每次热重载一条**假崩溃**。而且注入对**卡在 C 层调用**的线程无效（实测线程躺在 `time.sleep(8)` 里，注入后要 **7.00 秒**才生效），所以「加宽限期」治不了本。CPython 默认钩子对 SystemExit 是静默的，上游只是没开这个例外——功能上全是插件自己的问题。
- **正解：让「第二代线程」根本不存在。** 插件目录下的 `keeper.py` 是**跨重载单例**：
  · 模块名 `hermes_plugins._fmb_keeper` 不在 `hermes_plugins.<slug>` 前缀下 → `_evict_modules()` 清不到它（重载只删 `<slug>` 与其子模块）；
  · 它持有**唯一一条** watcher 线程 + 看门狗线程 + 跨代共享容器（插件的 `_SOURCES`/`_SOURCES_TS`/`_QUOTA_CACHE` 用 `_shared(...)` 别名过去 → 重载不再丢卡片按钮回注的会话上下文）；
  · `register()` 只做交班：`keeper.boot(sys.modules[__name__])` 把 `generation` 指向当前模块（微秒级，**不占** `plugins.load_timeout_seconds`=10s 的加载硬超时）→ 线程每轮取当前代跑它的 `_watch_once()`，**永远执行最新代码**；旧模块对象无人引用 → 可被 gc 回收。
- **三条收尾/自愈机制**（缺一不可）：
  1. `ctx.on_unload(lambda: keeper.request_stop(token))` —— 官方生命周期钩子，卸载/禁用/强制重载都会跑（台账按注册逆序 dispose）；**令牌比对 + 1 秒确认窗**（`_STOP_CONFIRM`）：热重载的 unload→load 只隔几十毫秒，当场置 `stop` 会让看门狗每次重载白换一条线程。
  2. **自我让位** —— 每轮检查 `sys.modules.get(module_name) is generation`，不成立就干净退出（即使 `on_unload` 没跑到也不会变僵尸）。
  3. **看门狗** —— 30 秒心跳，watcher 意外死亡才拉起；代已失效**不救**（否则每 30 秒空转拉一条立刻又退出的线程），连续两轮无有效代自行收摊。
- **老式线程一次性迁移**：`_retire_legacy_threads()` 只给旧线程的 `_target.__globals__` 置 `_STOP`/`_RETIRED`（**不注入**）；2.5 秒后仍活着的（不认标志的更旧版本）才由**异步 reaper 线程**兜底注入，绝不在 `register()` 里等待。迁移那次日志会看到 `已请 N 个上一代守护线程退出（置标志，不注入）`，之后不再出现。
- **改 `keeper.py` 不必重启网关**：keeper 带 `KEEPER_VERSION`，插件侧同号常量（`_KEEPER_VERSION`）不一致就换版重载 + 搬走共享容器 + 用**旧 keeper 自己的 `stop` 标志**请它收摊（仍不注入）。两个常量要一起加。
- **判据（怎么确认没退化成旧行为）**：热重载后 `journalctl -u hermes-gateway | grep -c gateway-crash` 与 `tui_gateway_crash.log` 的记录数**都不该增加**；`ps -T -p <网关pid>` 里 `feishu-menu-bri` 恒 1 条**且 TID 不变**（看门狗 `fmb-watchdog` 同理）。内核线程名只取前 15 字符，所以两个线程名必须前缀可区分。
- **线程逻辑改动不需要动 `_CODE_V`**（那个标记只管卡片/点击逻辑的分发器重建）。
- 历史教训（别重蹈）：异步异常只在**字节码边界**生效，对卡在 C 层（`subprocess.run`/`urlopen`）的线程注入无效；旧实现为此引入 `_STOP` + `_sleep_interruptible` 分片睡眠，那套现在只用于「退化路径（keeper.py 缺失）」与「请旧代退出」。
- 实测留档：离线 `test_keeper_real.py` 26/26（用改造前原件先跑起来复现迁移）；线上 4 次热重载 crash log `20→20→20→20`、journal `4→4→4→4`、线程恒 2 条且 TID 不变。

### 同一模式已推广：feishu-model-picker（2026-09-30 22:20）
- 该插件旧版每次重载泄漏一条 `while True` 且**不认任何停止标志**的 `_watch` 线程 —— 实测网关上同时活着 **13 条** `feishu-model-pi`（占网关 78 条线程的 17%），每条把上一代的模块命名空间（含 `_PICKERS` 卡片状态）钉在内存里，永不回收。
- **更隐蔽的一层（本次新发现，改任何「运行期打补丁」插件都要查）**：补丁标记 `_MARKER`/`_MARKER_LARK` 是**粘性布尔值** → 新一代 `_try_install()` 看到标记就 `return True`，**不重装自己的 hook**，类属性仍指向第一代的闭包 → **改这个插件后热重载根本不生效，必须重启网关**。修法：标记加**代际戳** `setattr(cls, _STAMP, f"v{_KEEPER_VERSION}.g{keeper.token}")`，比对「标记为真 **且** 戳相同」才算装好；同时做掉「原始方法只记一次」（`_fmp_orig_trigger` / `_fmp_orig_register`，wrapper 带 `_fmp_wrapper` / `__fmp_orig__`），补丁层才不会每次重载多包一层。
- keeper 命名：模块 `hermes_plugins._fmp_keeper`、`WATCHER_NAME="feishu-model-picker"`、`WATCHDOG_NAME="fmp-watchdog"`、`KEEPER_VERSION=1`；共享容器放 `_PICKERS`（卡片状态）与 `_PID`（序号——不共享会让新代 pid 从 1 重号，点旧卡片会命中错的那张）。
- **老式线程不认标志时不要注入**：本插件旧版 `_watch` 连 `_STOP` 都不读，注入 SystemExit 只会凭空造 13 条 `[gateway-crash]`（与本节的初衷直接相悖）→ 正确做法是**留着**（它们看到粘性标记后不会重装 hook，每 10 秒空转一次，无害）并明确告知用户「重启网关即清零」。识别信号：日志出现 `发现 N 个 keeper 之前的老式守护线程：不认停止标志，只能等网关重启；本次不注入异常以免产生假崩溃记录`。
- 实测：离线 `test_picker_keeper.py` **38/38**（真实插件文件 + 真实 keeper，模拟 evict→exec→register 两代 + 改造前原件迁移）；线上 3 次热重载 crash log `0→0→0→0`、journal `0→0→0→0`、线程 `13→15→15→15`（13 老式 + watcher + 看门狗，TID 不变、不再增长），日志里代际戳 `v1.g1→v1.g2→v1.g3`。
- **通用判据（判断一个插件是否已踩坑）**：看它有没有 ①`ctx.on_unload` ②停止标志 ③代际戳。三者缺一就可能「线程泄漏 + 热重载不生效」。三个已知同类插件已全部改造完毕：`feishu-menu-bridge`(v2)、`feishu-model-picker`(v1)、`memory-rewind`(v1，快照队列类 keeper：把待办队列搬进 keeper，插件类退化成无状态门面；代际必须在**出队瞬间**解析——读 `generation` 与用它之间不能跨阻塞点，否则会用旧代代码处理新请求)。以后按此判据扫其它插件即可，不要等用户点名。

### 卡片底部按钮布局（2026-09-30 用户定稿）
- **底部按钮一律 2×2**：302px 手机宽度下四个按钮同排，每格只剩约 63px，**文字会被挤扁**（实心按钮如 `danger` 的「停止」最明显，用户原话「太拥挤了看不见」）。
- 实现：`_rows(buttons, per_row=2)`（插件里的默认值就是 2），每格约 135px；自检脚本断言「2 行 × 每行 2 个」。
- 标签用**两字** + `size: "small"`（medium 会被截成「新…」）；列 `weighted weight:1` + 按钮 `width: fill` 保证同排等宽。
- 改完卡片样式必须跑真机自检（离线断言 + 真机发送）并热加载，再让用户看一眼确认。
- **按钮数 >4 时**：前 4 个仍走 2×2，第 5 个（通常「收起」）**单独一行占满宽**（同「用量」卡）。用户 2026-09-30 明确要求控制台卡补回设计稿里没有的「收起」——宁可多一行也别丢功能。
- **对齐设计稿别硬砍功能**：设计稿是版式目标，不是功能清单；设计稿缺的实用按钮（收起/刷新）追加为单独一行，比删掉它们安全。

### 「用量」卡：chart 折线 + 数据源 + 原地刷新（2026-09-30 按设计稿 v4 重做）
- **规格**：近 7 天 token 折线图（飞书 `chart` 元素）+「今日/本周/额度」三行式三格 +「刷新」（原地更新）「洞察」「收起」。
- **数据源**：折线/今日/本周 = `state.db` 的 `sessions` 表按 `date(started_at,'unixepoch','localtime')` 聚合 `input_tokens+output_tokens`（本地日、口径同 `/洞察`）；额度 = 中转站 `GET {base_url}/dashboard/billing/subscription` 只读探测（10 分钟缓存，失败给「—」，绝不打印密钥）。
- **原地刷新**：按钮 value 用 `{"hermes_menu_refresh": "<卡名>"}`；点击分支走 **PATCH**（`PatchMessageRequest` → `adapter._client.im.v1.message.patch`，见 menu-bridge `_patch_card`）原地更新，失败退回 `_send_card` 发新卡。**改卡片/点击逻辑必须把 `_CODE_V` +1**（强制重建已连接分发器）；热重载后日志应出现 `dispatcher hook installed ... (vN)`（N＝新值）。
- **chart 元素**（JSON 2.0 专属，官方文档已核）：`{"tag":"chart","aspect_ratio":"2:1","color_theme":"brand","height":"150px","chart_spec":{"type":"line","title":{"text":...},"data":{"values":[{"day":..,"tokens":..}]},"xField":"day","yField":"tokens"}}`；数值先换算成 M 再进图（大数字挤爆手机端坐标轴）。`_send_card` 退化链：被拒 → 去 `collapsible_panel` → 再去 `chart`。
- **真机自检**：离线断言（全卡结构）→ 302px 样张（`mock_card.py` 已支持 chart 近似渲染）→ 直接 API 试发本会话 → 热重载。补丁存档：本机补丁目录（清单见你的补丁仓库）。

### 卡片点击链路必守的不变量（2026-09-30 全链路审计后固化）
- **绝不能拿卡片 token 当 message_id**：官方 adapter 就是这么写的（`_handle_card_action_event` 里 `message_id=token or uuid4()`）→ 飞书返 `99992354 invalid open_message_id`，降级重投又复用坏 id 再失败，用户端**完全静默**。正解：`context.open_message_id`（需打上游适配器补丁，见本包 README 的「本地补丁」一节）。
- 插件拦到自己卡片后，**处理异常也绝不落回官方路径**（否则走上面那条坏 id 路径）。三处入口都要 `return _ack()`：register 钩子包装、dispatcher `_handle_card_action_trigger`、`_handle_card_action_event`。
- **拿不到适配器/loop 时不许静默**：至少 ERROR + 计数（暴露丢弃率）；回执要如实，不能用「已收起」这类成功文案掩盖未送达。
- 插件**全文件零锁**是隐患：`_SOURCES` 迭代中被 pop 会抛 dict changed size；`_HEAL_TS` 读改写会节流失效；ad/ws 双写 handler 有不一致窗口 → 用一把 `_STATE_LOCK`，补丁安装用 `_INSTALL_LOCK` 串行化（防重入导致包装叠加）。
- `gc.get_objects()` 全堆扫描必须带 TTL 缓存（稳态 5 秒一次），否则持 GIL 卡事件循环，表现为单轮响应数百秒。
- 僵尸线程退役必须校验 `PyThreadState_SetAsyncExc` 返回值 ==1，并轮询 `is_alive()` 复检；返回 >1 要立刻用 `None` 撤销。不校验就会出现「上一代 watcher 还在跑」→ 多代并存。
- 上游日志会泄露凭据：Lark SDK 在 INFO 级打印带 `access_key`/`ticket` 的 wss URL → 在 `register()` 里 `logging.getLogger("Lark").setLevel(WARNING)`。

### 排查表
- `/model` 回文字列表 → `send_model_picker` 没挂上：查 journal 安装线、`plugins.enabled` 是否含该插件
- 卡片发了点不动 → journal 无 `click` 行：检查开放平台后台「事件与回调」是否订阅了「卡片回传交互」（**长连接模式同样需要**）
- 按钮点了没反应 / 日志出现 `unknown command /card`、`99992354` → 点击穿到官方通用路径：按上文「四层拦截」在 `EventDispatcherHandler._do_without_validation` 上拦，别指望类方法补丁
- 客户端弹 `200671` → 先看 WS 原始帧：`type=event event_type=card.action.trigger` 到没到；到了就是拦截层/回执格式问题，没到才是回调配置问题
- 点了显示「切换失败：…」→ 看卡片文字里的异常（历史案例：回调签名漏参）
- 卡片不原地更新、另收到文字结果 → message_id 为空或 update 接口失败（看日志 warning）
- 「用量」卡点「刷新」没动静 → 日志 `刷新未送达`（loop/message_id 取不到）或 `刷新原地更新失败`（会自动改发新卡；仍不来就查适配器 update 接口权限）
- 鉴权/发布类错误 → 控制台「权限管理」核对 scope
- 飞书收到「Confirm /new … Text fallback: reply /approve …」**纯文本、没有可点按钮** → 上游适配器未实现 `send_slash_confirm`（斜杠确认三按钮卡；/new、/reload-mcp、/model 成本确认都会走它），已由本地补丁 `feishu-slash-confirm-card.patch` 补齐（**重启网关后生效**）。未重启时的绕过 = 按提示回复文本 `/approve`、`/always` 或 `/cancel`（5 分钟内有效）。

## 四、控制台自动化小抄（browser_exec）
- 视口：CDP `Emulation.setDeviceMetricsOverride` 宽 1280 × 高 ≥2400（否则下方按钮点不到）；截图易超时，先 `clearDeviceMetricsOverride` 用小视口重截
- 改已有字段值：React 原生 setter + `input` 事件（普通注入只会追加）
- 元素坐标随内容位移：每次先动态定位，用**中心坐标**（`r.x + r.width/2`）点击；删除按钮等易点空
- 页面文本检查比截图快：`document.body.innerText` 关键字断言
- 主菜单 chip 悬停有删除按钮（勿误点）；条目删除在【子菜单配置】面板内
- 长流程拆步并逐段校验；定时任务（`systemd-run --on-active`）用于“延迟重载 + 自检”解耦

## 五、移植与安装（别人到手就用）
- **前置**：目标部署已有 Hermes + 飞书渠道（应连、能收发消息）；飞书应用已开「机器人」能力并订阅长连接事件
- **菜单桥插件是 2 个文件**：`feishu-menu-bridge/__init__.py` + `feishu-menu-bridge/keeper.py`，**两个都要拷**。缺 `keeper.py` 会自动退化为「插件自带守护线程」（仍不注入异常、仍认 `_STOP`），但没有看门狗、也没有跨重载共享状态。
- **一键安装点选器**：
  ```bash
  bash scripts/install-feishu-model-picker.sh   # 复制插件 → hermes plugins enable → reload 网关
  ```
- **验证**：按第三节“部署清单”；再发 `/model` 实测
- **自定义菜单**：按第一节在控制台配置；条目名称对照你的 quick_commands / 原生命令
- **换平台做主菜单**（Telegram 等）：Telegram 菜单由客户端自动生成，无需控制台；`send_model_picker` 在 Telegram 适配器是原生的
- 所有路径默认 `~/.hermes`（可用环境变量 `HERMES_HOME` 覆盖）

## 附：已知边角（勿漏）
- 飞书控制台菜单**官方文档层无 API**，但**控制台内部接口可用**（见第一节「API 直写」）；发布有 v7 发布 API（`application:application:patch` scope）但菜单内容不可经它改
- 机器人菜单点按 = 发文本；**不会**触发卡片回调（回调订阅是卡片按钮的事）
- 「卡片回传交互」回调在控制台「事件与回调」添加；新版与旧版两种，选新版（结构 = 事件订阅一致）
- 悬浮菜单在手机内显示于输入框上方；发布后 5 分钟内客户端同步
- **改 quick_commands 只能走 `hermes config set 'quick_commands.<名>' '{"type":"alias","target":"/xxx"}'`**：`patch`/`write_file` 会被安全策略拒绝（"Refusing to write to Hermes config file"）
- ⚠️ `systemctl reload hermes-gateway.service` **不换 PID**（原地 exec），且会**等当前回合排空**才真正重载配置 → 改完配置必须等下一回合再验证，别在同一回合断言已生效
- ⚠️ 控制台区块的「编辑」铅笔图标在**合成 hover 下不出现**（`getBoundingClientRect().width === 0`）：`mouseover/mouseenter/mousemove` 都无效，需 CDP `Input.dispatchMouseEvent` 真实鼠标移动或人工点一下
- 卡片交互能力（2026-09 实测）：`cardkit:card:write` 该应用**已开通**，创建卡片实体 / 开流式 / 流式写文本全部 code 0；消息**表情回复**（`im/v1/messages/{id}/reactions` 加/撤）也已可用且**零额外权限**，适合做「收到/完成/失败」的静默状态反馈

## 批量清理/重构脚本的铁律（2026-10-04 血泪教训）

对 __init__.py 这类超大文件做批量编辑（死代码清理/日志降级/批量改名）时：

1. **行号删除必须先于内容删除**——内容删除会移动行号，混在一起必出事。
2. **每处改动带前置断言**（旧文本实得数 == 期望数），不满足即中止、不写盘。
3. **写盘前用 `compile(source_str, path, 'exec')` 做内存语法检查**——千万别写完再 py_compile（一个删空 `try:` 会把好文件写坏，只能靠备份还原）。
4. **删「未用导入」前先看上下文**——有些 import 是故意留着跑副作用的（如 `import hermes_bootstrap` 在 try 里先引导，后面的 import 才能成功），pyflakes 报 unused ≠ 可删。
5. 改完必过三关：内存 compile → `python3 -m pyflakes` → 行为回归套件（`~/.hermes/cache/scratch/verify_auditfix.py`）。
6. 备份先行：`__init__.py.bak-<tag>` 本地 + `~/.hermes/backups/feishu-menu-bridge/` 双份。批量脚本产物（如 `cleanup_batch1b.py`）都是带断言的可重跑脚本，保留在 scratch 供查。

## 六、卡片翻页框架（2026-10-02 落地，第一张翻页卡 = 命令表）
- **就地翻页，不叠卡**：卡内按钮 value 用 `{"hermes_menu_page": {"card": "<卡名>", "page": N}}`；插件在点击处理器里
  `build_card(card, chat_id, page)` 重建，然后走 **PATCH**（`PatchMessageRequest` → `adapter._client.im.v1.message.patch`）原地更新——**别用 `message.update`（PUT）**：它对 interactive 会报 230001 `invalid msg_type`（2026-10-04 已在菜单卡与选单器两处修实）。
  （`_patch_card` → `PatchMessageRequest`）**原地刷新同一条消息** —— 与「刷新」按钮同一条路。
- **导航行**：`_nav_row(card, page, pages)` 生成 `column_set` 两列（`‹ 上一页` / `下一页 ›`）；首页不渲染「上一页」、
  末页不渲染「下一页」（不用 disabled 字段，少一个客户端兼容风险）。
- **注册三步（漏一步就点不开卡）**：
  1. `CARD_BUILDERS["<卡名>"] = build_x_card`；
  2. 带页码的卡再进 `PAGED_CARDS`（`build_card` 据此多传一个 `page`）；
  3. **同时**把名字加进 `CARD_NAMES` —— `COMMANDS` 是 `GROUPS` 减去 `CARD_NAMES` 得来的；只加 `CARD_BUILDERS`
     不加 `CARD_NAMES`，菜单点按仍走「改写命令」而不是开卡。
- 卡头副标题放「第 N/M 页 · 共 X 条」，页内 `_PAGE_SIZE = 15` 条一页。
- 改完照例 `_CODE_V` +1 再 reload，否则 dispatcher 钩子不重建（点按落进模型）。

## 七、命令表卡的数据源（踩过的坑）
- **别在插件里 `import hermes_cli.commands`**：它 → `utils` → `hermes_yaml` → `ruamel.yaml`，而 Hermes 运行时
  （`~/.hermes/tools/python-3.14.x/bin/python3`）在**裸 shell 里没有 ruamel**（只有走过 `hermes_bootstrap` 的网关进程才有）
  → 插件里 import 会失败、卡片变空。
- 正解：**用 `ast` 静态解析** `/usr/local/lib/hermes-agent/hermes_cli/commands.py` 里的 `CommandDef(...)` 字面量
  （取 name / description / category / args_hint / cli_only）—— 零依赖、只读、无副作用。
- 中文化：先 `import hermes_bootstrap`，再 `from agent.i18n import t`，用 `slash.<name>.description` 与
  `slash.category.<slug>` 取中文；拿不到就退回英文原文（分类另有 `_CMD_CAT_ZH` 兜底）。
- 解析不出来时退化为「悬浮菜单 23 项」，保证卡片不空。实测：聊天可用命令 67 条 / 5 页。

## 八、技能全表卡 / 人格卡的数据源（2026-10-02 落地，第 2、3 张）
- **技能全表**（`_skills_flat()`）：`Path(HERMES_HOME or ~/.hermes)/skills` 下 glob `*/*/SKILL.md`（分类/技能名）
  与 `*/SKILL.md`（归到 `(未分类)`）；分类按技能数降序、分类内按名字排序。实测 85 个 / 13 类 / 6 页（每页 15）。
  每个技能 = 一个全宽按钮（点了发 `/技能名`）+ 一行描述，描述取自 `SKILL.md` frontmatter 的
  `^description:\s*(.+)$`（`_skill_desc()` 只读前 1500 字符，够用且快）。
- **人格卡**：内置人格表在 `/usr/local/lib/hermes-agent/hermes_cli/personality.py` 的
  `BUILTIN_PERSONALITIES: Dict[str, str] = {...}`（14 个：helpful/concise/technical/creative/teacher/
  kawaii/catgirl/pirate/shakespeare/surfer/noir/uwu/philosopher/hype）。同样 **ast 静态解析**。
  - ⚠️ **坑（已踩）**：它是**带类型注解的赋值** → AST 里是 `ast.AnnAssign`，**不是 `ast.Assign`**；
    只判 `ast.Assign` 会解析出 0 个（卡片显示「共 0 个内置」）。取目标要写：
    `targets = node.targets if isinstance(node, ast.Assign) else ([node.target] if isinstance(node, ast.AnnAssign) else [])`。
  - **当前人格** = `config.yaml` 的 `display.personality`（空 = 未设置）。设置只走
    `hermes_cli.personality.persist_personality()`（唯一合法写入口，原子写、保留注释）。
    插件里不 import（同样会拖进 ruamel），直接正则扫 `^\s{2}personality:\s*(.*)$` 读值。
  - **切换按钮** = 发 `/personality <英文名>`；`/personality none` 关闭。
  - **注意**：用户的自定义人设（`SOUL.md` / `agent.system_prompt` 里定义的名字），**不受** `display.personality` 影响
    —— 卡片里要写明这句，否则会误导。
- **把文字型菜单项改成开卡**：`CARD_NAMES` 加名字即可（`COMMANDS = GROUPS − CARD_NAMES`），命令数会随之减少。
  实测：加「人格」后 16 命令/7 卡片 → 15 命令/8 卡片，同时修掉「点 🎭人格 没反应、落进模型」的老问题。

## 九、菜单项「显示中文、实际发命令」＋忙时失灵（2026-10-02 定案）
- **硬结论（实测证伪，别再试）**：飞书悬浮菜单**显示什么就发什么**。叶子项只有 `defaultName` /
  `i18nBotMenuName` 两个名字字段，没有独立内容字段 —— 把 `defaultName` 改成 `/stop`、`i18nBotMenuName.zh_cn`
  保持「⏹停止」并发布新版本后，客户端**照旧发中文显示名**（日志 `type=text text='⏹停止'`）。
  想要「显示中文、实发指令」**只能在服务端转换**，客户端做不到。
- **忙时失灵的真根因（源码级）**：`plugins/platforms/feishu/adapter.py` 的 `_dispatch_inbound_event`：
  `if event.message_type == TEXT and not event.is_command(): await self._enqueue_text_event(event)`。
  纯文本一律进批处理（静默期 + **每会话锁** `_handle_message_with_guards` → `handle_message`），会话忙时
  被正在跑的回合挡在锁后面；**命令不进批处理**，直通 `_hm_handle_running_session_message` 的忙时快通道
  （`_hm_busy_slash_or_photo` → `_dispatch_busy_slash_command`）。这就是「手打 `/stop` 忙时也灵、
  菜单「⏹停止」忙时失灵」的全部原因。
  - **补钉①（2026-10-02 03:32 实证）——忙时快通道只认内置命令**：忙时解析走 `hermes_cli.commands.resolve_command`，**中文快捷命令忙时不展开**（quick_commands 展开只发生在冷路径 `_hm_resolve_command`）。所以菜单改写**必须直接映射英文内置命令**（`/stop`、`/new`…）；写 `/停止` 这类忙时会被当未识别命令、掉回普通消息流被排队，点了没反应。v35 全改英文后实测全链路成功：`帧层改写 '⏹停止' → '/stop'` → `Invalidated run generation (stop_command)` → `STOP for session … agent interrupted, session lock released` → `Sending command '/stop' response`。
- **有效解法（唯一实测成功的一层）= 在 SDK 的 ws 数据帧层就地改写**：插件 `_patch_ws_class(lark_oapi.ws.client.Client)`
  的 `_handle_data_frame` 包装里，把 `event.message.content` 的 `{"text":"⏹停止"}` 改成 `{"text":"/停止"}`，
  再 `frame.payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")`；之后整条链把它当命令看待。
  - SDK 依据：`lark_oapi/ws/client.py:291 _handle_data_frame` 直接 `pl = frame.payload` →
    `self._event_handler._do_without_validation(pl)`；消息链路上**没有校验和验证**（`sum` 头只用于
    `sum_>1` 的分包重组）→ 改过的 payload 被原样采纳。
  - 实测证据（2026-10-02 修正版）：`03:18:08` 点「⏹停止」→ 帧层改写与 `type=command` 都发生了，**但那一轮并没有被打断**（45.9s 正常跑完；旧稿「随即被打断」系误判——忙时只认内置命令，中文 `/停止` 不展开）。同段两次点击还撞上压缩在跑、被 `Demoting busy_input_mode 'interrupt' to 'queue'` 降级排队。真正首次成功 = `03:32:50`（改英文 `/stop` 后，见补钉①）。
- **失败过的两层（别再走）**：① 包装网关忙时方法 `GatewayRunner._hm_handle_running_session_message` ——
  文本被会话锁挡住，根本到不了那里；② 包装适配器 `_dispatch_inbound_event` —— 实测未生效
  （怀疑 live 适配器类与补丁类不是同一个对象）。帧层最上游、最稳。v35 的 batch hook 同理：`03:24:53` 日志「batch hook installed on FeishuAdapter (v35)」，但 `03:25:43` 点「📊面板」时它没有任何拦截动作（原文本照旧批处理→进模型）。
- 映射复用插件自己的表：`COMMANDS = {name: "/" + name for GROUPS 项 if name not in CARD_NAMES}`；
  菜单名带 emoji 时先 `_strip_lead_icon()`（`_ICON_LEAD_RE = ^[^\u4e00-\u9fa5A-Za-z0-9/]+`，'⏹停止' → '停止'）。
- 顺带：帧层也可以顺路处理卡片型菜单项（忙时直接开卡）；命令类走改写即可。
- ✅ **「点卡片＝零模型」已闭环（2026-10-04 复核）**：批处理钩子 `_patch_batch_class` 包装 `FeishuAdapter._dispatch_inbound_event`，命中卡片名 → 发卡后 **`return None` 吞掉原文**（`__init__.py` L2166-2177），不进模型。日志佐证：`菜单项直接开卡 '📊面板'（跳过批处理）`；`agent.log` 里菜单名出现 **0 次**。忙时另有 `_hm_handle_running_session_message` 包装（busy hook）兜住。**旧记录「原文仍会流进模型」已不成立，勿再照它返工。**
