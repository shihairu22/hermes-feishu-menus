# Hermes 飞书菜单：卡头配色规范 + 已实测可用的组件

来源：2026-10-04 真机实测与落地（用户批准「动」）。调研全文见 `~/feishu-card-visual-research-20261003.md`。

## 一、卡头色：3 个功能域色（已落地）

收敛前 8 张卡用了 7 种卡头色，其中 **4 对 OKLab 色差 < 0.10**（面板↔技能仅 0.043，肉眼等同）。
现收敛为 3 个功能域色，定义在 `feishu-menu-bridge/__init__.py` 模块级：

```python
_DOM_ENTRY = "blue"        # 入口/总览：面板、菜单速查、命令表
_DOM_DATA  = "turquoise"   # 状态/数据：系统、用量、PT
_DOM_TOOL  = "grey"        # 工具/个人：技能、人格
```

两两色差 0.247 / 0.223 / 0.092（在飞书 12 色卡头里选的最优解）。
**改配色只改这三个常量即可**；`_usage_cell(tone=...)` 的底色/数字色跟着走。

注意：卡头色是 `_card(title, template, ...)` 的**第二个位置参数**，不是 `"template"` 键——
用 grep 找 `_card("` 才扫得全。

## 二、已实测可用的卡片组件（真机截图确认，2026-10-04）

| 组件 | 结论 | 备注 |
|---|---|---|
| `chart` + `line`/`area`/`bar` | ✅ 全可渲染 | 坐标轴、日期标签、**数值标签默认显示**、网格线齐全 |
| `table` | ✅ 可渲染 | 表头/分隔线/右对齐数字/彩色标签都正常 |
| `table` 的 `options` 列 | ✅ 彩色标签 | 值必须是数组：`[{"text": "偏高", "color": "orange"}]` |
| `table` 的 `number` 列 | ✅ 右对齐 | 值必须是**数字**不是字符串 |
| `column_set` / `collapsible_panel` / `hr` | ✅ 早已在用 | 面板卡的 KPI 瓦片、按钮行就是 `column_set` |
| `interactive_container` / `overflow` / `audio` / `text_tag` | ❌ 未用 | 备用 |

**含 `chart` 的卡片，按钮仍然可点**（用量卡的 `hermes_menu_refresh`、`hermes_menu_cmd` 历史上真被点动过）——
图表不会把卡片变成不可交互的图片。

## 三、测新组件的铁律：发送成功 ≠ 能渲染

- 飞书**不校验** `chart_spec.type`：传一个不存在的类型，接口照样回 `code=0 success`，
  客户端渲染时才显示「图表加载失败」占位。
- 所以**必须真机截图确认**，`code=0` 只能证明接口收下了。
- 读回消息（`GET /im/v1/messages/:id`）时卡片正文会退化成 `img` + 「请升级至最新版本客户端」——
  这是**读回接口的表示**，不代表真机渲染成图片，别被它误导。

## 四、改完怎么让网关生效（**必须重启，热重载不够**）

**2026-10-04 实测教训**：改了卡片构造/配色后只调 `reload_gateway_plugins()`，返回 `reloaded: true`，
**但线上跑的仍是旧代码**（卡片还是旧配色）——而且变成「点一次菜单蹦两张卡」。

原因：插件用 `_CODE_V`（本文件 L1554）当「已安装」标记写进被 patch 的类上
（`_MARKER_WS` / `_MARKER_BUSY` / `_MARKER_BATCH`）。**不升 `_CODE_V`，钩子就不重建**，
已连接的适配器继续跑旧模块的闭包（旧的 `build_card` → 旧配色）。

正确流程：

1. **改代码的同时把 `_CODE_V` +1**（注释原话：改本文件里任何「卡片/点击」逻辑时 +1）。
2. **重启网关**：`hermes gateway restart`（systemd 单元 `hermes-gateway.service`）。
   重启后日志应出现 `hook installed ... (v<新版本号>)`。
3. 想延迟重启（自己先回话再重启）用一次性定时器，不要用 `sleep &`：
   `systemd-run --on-active=30 --unit=hermes-gw-restart-once --collect ~/.local/bin/hermes gateway restart`

改前必备份：`cp -p __init__.py "__init__.py.bak-<tag>-$(date +%Y%m%d-%H%M%S)"`。

## 四之二、开卡只能有一条路径（否则一次点击蹦两张卡）

本插件里有**三条**都可能在「收到菜单名文本」时开卡，全装上的话就会重复：

| 钩子 | 挂在 | 行为 |
|---|---|---|
| 帧层 `_patch_ws_class` | `FeishuAdapter._handle_data_frame` | 发卡后**不阻止**原文派发 ⚠️ |
| 忙线 `_patch_busy_class` | `GatewayRunner._hm_handle_running_session_message` | 发卡后 `return None` |
| 批处理 `_patch_batch_class` | `FeishuAdapter._dispatch_inbound_event` | 发卡后 `return None` ✅ 主力 |

**结论：开卡只由批处理钩子负责**（它在最前面且会掐断后续派发），帧层只做命令改写。
2026-10-04 已按此删掉帧层的开卡分支，实测前「帧层+菜单项」成对出现 = 两张卡。

改这类逻辑后**必看日志验证**：点一次菜单只应出现一条开卡记录。

## 五、验证脚本（都在 `~/.hermes/cache/scratch/`）

- `send_chart_test.py` —— 三种图表类型 + 兜底文字的最小测试卡
- `send_table_test.py` —— 表格（text/number/options 三列）测试卡
- `chart_control_test.py` —— 对照测试：故意传非法图表类型
- `build_and_send_new_cards.py` —— 用新代码生成卡片并发到飞书（改完配色的端到端验证）
- `test_pt_table.py` —— PT 卡异常站表格的两个分支单测（有失败 / 全通过）
- `apply_palette_v2.py` —— 配色收敛的原子替换脚本（每处校验命中次数，全通过才写盘）

**原子替换脚本的写法值得复用**：把每处替换写成 `(old, new, 期望命中数)`，
命中数不符就整体放弃并打印差异；写盘前先 `ast.parse` 自检。比逐处 patch 更安全。
