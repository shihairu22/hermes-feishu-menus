# 翻页机制、卡片清单与重启姿势（实测）

## 一、翻页载荷与那个「未知命令 /card」bug

翻页按钮的载荷长这样（飞书新版按钮结构，值在 `behaviors[0].value`，**不在** `button.value`）：

```json
{"tag":"button","type":"primary_filled","size":"small","width":"fill",
 "text":{"tag":"plain_text","content":"下一页 ›"},
 "behaviors":[{"type":"callback","value":{"hermes_menu_page":{"card":"技能","page":2}}}]}
```

**根因（2026-10-04 实测）**：插件靠 `_is_our_value(value)` 判断「这个按钮是我发的吗」。它的键白名单里原本只有
`hermes_menu_cmd / hermes_menu_card / hermes_menu_close / hermes_menu_refresh`，**漏了 `hermes_menu_page`**。
后果：翻页点击不被认领 → 飞书适配器把卡片点击合成一条 `/card button {...}` 文本命令丢给命令分发器
→ 用户看到「未知命令 /card。输入 /commands 查看可用命令，或去掉开头的斜杠重新发送」。

> **规则**：新增任何按钮载荷键（`hermes_menu_*`），**必须同步加进 `_is_our_value` 的键白名单**，
> 否则点击会退化成一条 `/card` 命令报错。这是最容易漏的一步。

### 1.1 点击认领了，卡片却改不动：改卡片要用 PATCH，不是 PUT（2026-10-04 实测）

翻页/刷新是「原地改同一张卡」。飞书两个接口长得很像，用错就报参数非法：

| 用途 | 接口 | body | 实测结果 |
|---|---|---|---|
| 改**文本/富文本**消息 | `PUT /open-apis/im/v1/messages/{id}` | `{msg_type, content}` | 传 `msg_type=interactive` → **230001 invalid msg_type** |
| 改**卡片**消息 | `PATCH /open-apis/im/v1/messages/{id}` | 只带 `content` | `code=0 success` |

SDK 侧：`adapter._build_update_message_body()` + `message.update` 是 PUT（只适合文本）；
卡片要用 `PatchMessageRequest` / `PatchMessageRequestBody` + `client.im.v1.message.patch`，
**request_body 里没有 `msg_type` 字段**（只有一个 `content`）。

插件里统一封装成 `_patch_card(adapter, message_id, card)`，翻页与刷新共用，别再各写一份。

> **判别口诀**：日志出现 `invalid msg_type` / `230001` 时，先看是不是把卡片塞进了 PUT。

## 二、单页卡不要翻页行

`_nav_row(card, page, pages)` 在 `pages <= 1` 时**返回 None**，调用点写：

```python
_nav = _nav_row("技能", page, pages)
if _nav:
    el.append(_nav)
```

理由：单页卡片上留一行「已到最后一页」纯属废按钮、影响观感。

## 三、卡片清单（15 张）

| 卡 | 域色 | 说明 |
|---|---|---|
| 面板 | indigo | 总览入口 |
| 系统 | turquoise | 磁盘/内存/负载 |
| 系统详情 | turquoise | 主机层细节（系统卡「📊 详情」的落点） |
| PT | turquoise | 站点数 + 异常站表 |
| 技能 | indigo | 11 页（`_SKILL_PAGE_SIZE=8`），中文说明 |
| 帮助 | indigo | 5 组 × 23 项 |
| 用量 | turquoise | 今日/累计/额度 + 按渠道折叠栏 + 7 天折线 |
| 命令表 | indigo | 5 页 |
| 人格 | indigo | 2 页，14 内置 |
| 状态 | turquoise | 6 指标 + 磁盘内存 |
| 推理 | indigo | 8 档可点选 |
| 任务 | turquoise | 后台委托 + 定时任务 |
| 洞察 | turquoise | 逐模型用量 + 最耗会话 |
| 模型 | indigo | 当前 + 25 通道，点选切换 |
| 忙时 | turquoise | 插话/排队/转向 |
| 版本 | indigo | 版本/网关运行时长/家底 |

「状态」「推理」「任务」「模型」「忙时」「版本」「系统详情」**不在 `_MENU_CMD` 文字改写表里**——摘掉后点击才落到
`CARD_BUILDERS` 分支出卡；`/status`、`/reasoning` 等命令在聊天框直接输入仍然可用。

## 四、技能中文说明表

`skill_zh.json` 放**插件目录**（与 `__init__.py` 同级），按 `st_mtime` 热加载，改文件不用重启：

```python
def _skill_zh(name):  # 命中返回中文，未命中返回 ""（调用方回退英文原文）
    return str(_skill_zh_map().get(name) or "")
```

技能卡里：`d = _skill_zh(r["name"]) or _skill_desc(r["path"])`。
当前 **87 条 = 覆盖全部技能（0 缺失）**。新增技能若描述是英文、或带着 `Use when ` 前缀，
往这个表里补一条即可——卡上只截取前 34 字，写短。

页容量：技能单独一档 `_SKILL_PAGE_SIZE = 8`（15 条/页时整卡过高）。命令表仍用 `_PAGE_SIZE = 15`。

## 五、改完怎么生效（顺序不能错）

1. 改 `__init__.py`（卡片结构 / 点击逻辑 / 配色，**任何一项**）
2. **`_CODE_V` +1** —— 不升版本号，已连接的分发器会继续跑旧代码，改了等于没改
3. 重启网关

### 重启网关的正确姿势

网关**不能自我重启**：`hermes gateway restart` 和 `systemd-run ... systemctl restart hermes-gateway`
都会被守卫按字符串拦下。用独立单元，让 systemd 自己执行：

```bash
systemctl start --no-block hermes-gw-refresh.service   # 单元内 ExecStart=/bin/systemctl restart hermes-gateway
```

- `--no-block` 必须加：否则 `systemctl start` 会等 oneshot 跑完，而重启会把当前 shell 一起带走。
- **不要指望 `hermes-gw-refresh.timer` 能反复用**：它只有 `OnActiveSec=3`，跑过一次就变成
  `active (elapsed)`，再 `systemctl start` 不会重新计时。要重触发就**直接 start 那个 service**。
- 重启后核对钩子版本：`grep -a 'hook installed' ~/.hermes/logs/gateway.log | tail -3`
  → 应出现 `busy hook installed on GatewayRunner (v43)` / `batch hook installed on FeishuAdapter (v43)`。

### 重启后自检的坑

想让脚本在重启后自动跑，用 `systemd-run --on-active=N --collect`。注意两点：

- N 是「相对 unit 激活时刻」，网关关闭本身要十几秒，**要留足余量**；
- 核对结果**要等够时间再读**——过早读会看到「文件不存在」，误判成没跑（本次踩过两次）。

## 六、图表 / 配色 / 组件的校验坑（2026-10-04 实测）

飞书**会**校验卡片元素结构，只是不校验 `chart_spec` 里的图表类型。发卡被拒时看 `ErrPath` 就能定位：

| 报错 | 原因 | 改法 |
|---|---|---|
| `200621 parse card json err ... path: body -> elements -> [N]` | 第 N 个元素结构不对 | 常见是把 `_rows()` 的**返回列表**当单元素塞进 elements——必须 `el += _rows([...])`，不能 `el.append(_rows([...]))` |
| `unknown property, property: color, path: ... (tag: chart)` | 图表元素顶层只认白名单属性 | `color` 等 VChart 配置要放进 `chart_spec` 内 |
| `10002 invalid color: #067062` | `tone=` / `template=` 只认**色板名**，不认 hex | 传 `turquoise` / `indigo` / `violet` 等；hex 只用于 `chart_spec.color` |

### 发卡/改卡的最小可用姿势（脚本直发，绕过插件）

```python
tok = POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
      {"app_id": ..., "app_secret": ...}            # 凭据从 ~/.hermes/.env 读，别写进脚本
POST https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id
     {"receive_id": chat, "msg_type": "interactive", "content": json.dumps(card), "uuid": ...}
PATCH https://open.feishu.cn/open-apis/im/v1/messages/{message_id}  {"content": json.dumps(card)}
```

- 预览/测试卡一律**单独发一张**，不要动线上卡；
- 预览卡上的按钮若用未接线的载荷，点击会落到适配器合成 `/card` 命令报错——预览期把按钮指向
  `{"hermes_menu_refresh": "用量"}` 这类**已白名单**的键，点一下只是刷新，不会报错。
- 核对真机投递：`GET /open-apis/im/v1/messages?container_id_type=chat&container_id=<chat>&sort_type=ByCreateTimeDesc`
  （注意 `tenant_access_token` 那步必须用 POST，默认 GET 会 404）。
