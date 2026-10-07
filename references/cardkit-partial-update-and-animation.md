# 飞书卡片局部刷新（CardKit）与动画能力边界

## 一、结论先说

- **局部刷新可行**：能只替换卡片里的某一个组件，其余部分不重绘（不再整卡闪）。
- **连续动画不可行**：图表组件每次被更新都会**重新挂载**（客户端先转圈再出图），所以视觉上永远是「转圈 → 硬切」。密集推帧只会变成「翻页 + 一串转圈」，比硬切更难看。
- 想要「像水波一样连续起伏」的效果，**飞书卡片做不到**，不要再花时间试。

## 二、局部刷新的三个硬要求

1. 卡片必须是 **JSON 2.0**（`"schema": "2.0"`，组件放 `body.elements`）。1.0 卡片调不了这些接口。
2. `config.update_multi` 必须为 `true`（2.0 也只支持 true）。
3. 每次操作必须带 **`sequence`**：int32 正整数、**从 1 起、对同一张卡严格递增**。漏传 → `99992402 field validation failed`（报错完全不提 sequence，极易误判成参数格式错）。`sequence=0` 也会被拒。

## 三、调用链（三步）

```bash
# 1) 创建卡片实体（JSON 2.0 代码要转义成字符串）
POST https://open.feishu.cn/open-apis/cardkit/v1/cards
  {"type":"card_json","data":"{\"schema\":\"2.0\",...}"}   → data.card_id

# 2) 发送（msg_type 用 interactive，content 里放 card_id；不是 msg_type=card）
POST https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id
  {"receive_id":"oc_...","msg_type":"interactive",
   "content":"{\"type\":\"card\",\"data\":{\"card_id\":\"7692...\"}}"}

# 3) 只更新某一个组件
PUT https://open.feishu.cn/open-apis/cardkit/v1/cards/{card_id}/elements/{element_id}
  {"element":"{\"tag\":\"chart\",\"element_id\":\"chart_main\",...}","sequence":N}
```

- 权限：`cardkit:card:write`（tenant_access_token）。本机应用已开通。
- 组件 `element_id`：字母/数字/下划线、**必须以字母开头**、同一卡内唯一、≤20 字符。
- 一个卡片实体**只能发送一次**，有效期 14 天；只能由创建它的应用操作。
- 其他可用接口：`PUT /cards/{card_id}`（全量）、`PATCH .../settings`（改 config）、`POST .../batch_update`（多组件）、`PUT .../elements/{id}/content`（流式文本）。
- **200810**：用户点击卡片的回调交互进行中时不能更新，等交互结束再更新。

## 四、客户端版本与「假降级」陷阱

- JSON 2.0 需要**飞书客户端 7.20+**；低于此版本会显示「请升级至最新版本客户端」兜底文案。
- **陷阱**：`GET /open-apis/im/v1/messages/{message_id}` 回读 2.0 卡片消息时，`body.content` 返回的是**降级投影**（`img` + `text: 请升级至最新版本客户端`），**不能据此判断用户客户端不支持**——实测用户客户端正常渲染，回读照样是这段兜底文案。要确认只能问用户实际看到什么。

## 五、为什么动画做不到（实测记录）

| 试过的做法 | 结果 |
|---|---|
| 一次性换数据（硬切） | 转圈 → 新图，硬切 |
| 服务端补间：10 帧 × 0.2 秒 | 仍像图片切换 |
| 服务端补间：16 帧 × 0.3 秒（带倒计时） | 用户反馈「图片切换感，不是水波起伏」 |
| 密集帧 60 帧 × 0.07 秒 | 用户反馈「转圈圈然后切图感」——每帧都触发图表重挂载。**实测只有 2.1 帧/秒**（原以为 14 帧/秒） |
| 复用 keep-alive 连接推帧 | **没用**：组件更新接口单次 275～500 ms，是**飞书服务端处理耗时**（新建连接 286 ms vs 复用 314 ms，无差别）→ 单卡补间帧率天花板 ≈3 帧/秒 |
| `chart_spec` 里加 `animation/animationAppear/animationUpdate` | 客户端不放行，无过渡 |

- 服务端接口每次都是 `code=0`（**接口成功 ≠ 视觉有效**），判断观感只能靠真机看。
- 50 次/秒 的接口额度不是瓶颈，瓶颈是客户端每次更新都重建图表。

## 六、还没试过的一条路（未验证）

把图表的数据改成绑定**卡片变量**（图表组件支持 chart 变量，对应 `chart_spec` 的数据），用**模板卡片**（`type: template` + `template_variable`）发送。变量更新理论上可能不触发图表重挂载，从而拿到平滑过渡。

- 代价：需要在飞书卡片搭建工具里**手工建模板**，且 `template_id` 走搭建工具产出，纯 API 做不了。
- 未验证，别当作可行方案承诺给用户。

## 七、本机脚本

- `~/.hermes/cache/scratch/probe_cardkit_partial.py` — 建实体 → 发送 → 只更新图表/文字（视觉试验）。
- `~/.hermes/cache/scratch/probe_cardkit_body.py` — 探测更新接口的请求体格式（sequence 是必填）。
- `~/.hermes/cache/scratch/probe_cardkit_final.py` — 两张卡（普通 / streaming）带计数器同时跑，验证局部刷新是否真的生效。
- `~/.hermes/cache/scratch/probe_wave_morph.py` / `probe_wave_morph2.py` / `probe_morph_compare.py` — 补间帧 / 慢速 / 密集帧对比（均已证明做不到连续动画）。
- `~/.hermes/cache/scratch/measure_cardkit_latency.py` — 量组件更新接口延迟（结论：服务端 ~300 ms/次）。

## 八、GIF 路线（唯一没被堵死的动效方案）

思路：图片组件由**客户端原生渲染**，GIF 的动画是客户端解码器在放，完全绕开「图表组件每次更新都重新挂载」。把波形图做成 GIF，切换时换 `img_key` 即可播一段平滑过渡。

- 代价：图表变成图片 —— 没有悬浮数据提示；PC 端「独立窗口放大」变成放大图片；深浅色主题不再自适应。
- 图片组件限制：1500×3000 px 内、≤10 M、`高:宽` ≤ `16:9`；2.0 不再支持 `stretch_without_padding`，通栏用 `margin: "4px -12px"`。
- 上传：`POST /open-apis/im/v1/images`，multipart（`image_type=message` + `image` 文件）→ `image_key`。注意用标准库拼 multipart 时要手动写 boundary 和 `Content-Type: image/gif`。

本机生成 GIF 的工具链（都有，别再说没有）：

- **Pillow 12.3.0 可用**（`/usr/bin/python3 -c "import PIL"`）；`Image.ADAPTIVE` 量化 + `save(save_all=True, append_images=[...], duration=80, loop=N, disposal=2)` 即可出图。`loop=0` 无限循环、`loop=1` 只播一次（客户端是否遵守要真机验证）。
- ffmpeg：`~/.hermes/tools/ffmpeg-9.0.1-linux-x64/bin/ffmpeg`（不在 PATH 里）。
- 中文字体：`/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`（还有 Black/Medium、NotoSerifCJK-Bold）。
- Chrome：`/usr/bin/google-chrome --headless=new`。

试验脚本：`~/.hermes/cache/scratch/probe_gif_card.py`（画 24 帧波浪过渡 GIF → 上传 → 2.0 与 1.0 各发一张卡，内含「无限循环」和「只播一次」两张图，右上角带红色帧号便于判断是否真的在动）。

## 九、正式版配方（本机已落地，可直接复用）

生产脚本：`~/.hermes/tools/usage_wave.py`（`refresh` / `tap <档位>` / `send` / `card`），状态文件 `~/.hermes/state/usage_wave.json`，GIF 落在 `~/.hermes/state/usage_wave_gifs/`。

### 9.1 数据必须真值，且**定格帧**要等于真值

- 用户会核对：「别 gif 和数据显示都不同」。所以每张 GIF 的**最后一帧**必须是用该档位真实数据画的图，中间帧才是过渡。
- 验证办法（别靠肉眼、更别靠视觉模型，它对位置判断不准）：把参考帧过一遍**同一条量化流水线**（`convert('P', ADAPTIVE, 96).convert('RGB')`），再逐列找曲线像素比纵坐标 → 686 列零差异才算过。脚本：按同一流程自己写一个逐列比对脚本即可。

### 9.2 GIF 编码三条硬规则（违反会出现「定格帧和真值不一样」）

| 规则 | 原因 |
|---|---|
| `optimize=False`（整帧写入） | 增量优化后个别解码器会把最后一帧拼错 |
| `disposal=1`（**不要用 2**） | `disposal=2` + 增量帧实测让定格帧右端比真值低 **15 px**（≈6% 纵轴），肉眼可辨 |
| 全部帧共用**一张全局调色板** | 每帧各自 `ADAPTIVE` 会让帧间跳色；取中间帧做 base，其余 `frame.quantize(palette=base, dither=Image.NONE)` |

### 9.3 点按触发（不是自动轮播）

- 2.0 按钮的回调值走 **`behaviors: [{"type": "callback", "value": {...}}]`**，2.0 没有顶层 `value` 字段（1.0 才是 `value`）。
- **按钮 value 的键名必须以 `hermes_menu_` 开头**（本机插件 `_intercept_card_action` 有一行原始字符串快速过滤 `if "hermes_menu_" not in raw: return False`，不含该前缀的键会被**静默丢弃、连日志都不留**）。
- 插件侧加一个分支：`value.get("hermes_menu_wave")` → `subprocess` 调 `usage_wave.py tap <档位>`；**必须同时把 `hermes_menu_wave` 加进 `_is_our_value()`**，否则回调会被当外来的丢掉。
- 点按后只 `PUT` 图片组件（`wave_img`）+ 文字组件（`md_head`），卡片其余部分不动 —— 这才满足用户「卡片不动、只有波形在动」的要求。
- 回调在交互进行中不能更新卡片（`200810`），所以更新放后台异步做，先回 toast。

### 9.4 同一档位连点两次要能重播

`img_key` 不变时客户端不会重播动画。做法：每个过渡准备**两份** GIF，第二份多挂一帧相同画面（肉眼完全一致但文件不同 → 拿到不同 `image_key`），状态里记 `next` 交替使用。

### 9.5 过渡方向要跟「当前档位」走

GIF 是「上一档形状 → 本档形状」的过渡。若用户从 24 小时直接跳到 7 天，用预生成的「3 天→7 天」会起手就对不上。状态里记 `current`，点按时按 `current → 目标` 取/生成对应过渡（12 种组合，按需生成并缓存）。

### 9.6 按钮高亮必须一起更新

只更新文字和图片、不更新按钮组时，高亮会一直钉在初始档位，用户会描述成「按哪个都跳回 24」。每次点按要把按钮组（`el_btns(rng)`）一并更新。

### 9.7 客户端会忽略 GIF 的循环设置 → 必须「静止静态图 + 点按才播 + 播完换回」

实测把 `loop=1` 写进文件（服务端存的图拉回来验过，`loop=1` 在），客户端**照样无限循环**。靠「末帧给很长的 duration」只是把重播间隔拉长，用户仍然会**在没点按钮时看到它自己播**（原话：「我不点按钮的时候他也会播放这个就很破坏体验感」）：GIF 单帧时长上限是 65535 厘秒（≈10.9 分钟），而且任何一次重渲染都会从第一帧重播。

正确做法是**让静止态根本不是 GIF**：

1. 每个档位额外上传一张**静态 PNG**，内容 = 该档位 GIF 的定格帧（在 `save_gif` 里顺手 `ps[-1].convert('RGB').save(still_png, optimize=True)`，与 GIF 定格帧逐像素一致，换过去看不出差别）。
2. 卡片初始/静止时用**静态图**（`el_img(st, rng)` 默认取 `still_key`）。
3. 点按时才把图片换成**过渡 GIF**（`el_img(st, rng, anim=True)`）。
4. 点按同时记一个「定格令牌」`st['settle'] = {'rng': rng, 'seq': st['sequence']}`，再 `subprocess.Popen([sys.executable, __file__, 'settle', rng, str(seq)], stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)` 起一个**游离子进程**：睡 `SETTLE_S`（本机 4.5 秒，要 > 动画时长、< 动画+定格，避开循环点）后把图片换回静态图。
5. `settle` 子进程**先校验令牌**（`st['settle']` 的 rng/seq 与传入一致、`st['current'] == rng`）再动手，否则会把用户新点出来的画面覆盖掉；更新完**重新读一遍状态文件**再写，只合并 `sequence` 并清空 `settle`。

实测链路：点按 0.55s（图片=GIF）→ 6.5s 后 `settle={}`、`sequence` 已 +1，即静态图已自动归位。

## 十、点按性能：慢与空白（2026-10-04 实测数据）

### 10.1 一次请求改多个组件，别连着 PUT 三次

组件级 `PUT /cards/{card_id}/elements/{element_id}` 单次实测 **337～455ms**，改「文字+图片+按钮」三个就是 **1.2s**，用户会明确说「点按太慢、还会空白一会」。

改用**批量更新卡片实体** `POST /open-apis/cardkit/v1/cards/{card_id}/batch_update`：

```json
{"uuid": "<随机>", "sequence": 12,
 "actions": "[{\"action\":\"update_element\",\"params\":{\"element_id\":\"md_head\",\"element\":{...}}}, ...]"}
```

`actions` 是 JSON 字符串，支持 `partial_update_setting` / `add_elements` / `delete_elements` / `partial_update_element` / `update_element`。三个组件合并成一次请求后，端到端从 **1528ms → 425～535ms**。

### 10.2 点按路径上别做重复劳动

| 优化 | 省下 |
|---|---|
| 用状态文件里已算好的四档数据（`specs_from_state`），别每次点按都查库算 4 档 | ~150ms |
| 缓存 `tenant_access_token` 到状态文件（有效期约 2 小时，缓存 90 分钟；遇到 `99991661/99991663/99991664/99991668` 时 `force` 重取并重试一次） | ~150ms |
| `refresh` 时预生成**全部 12 个方向对**（只预生成相邻四对时，点到反向组合要现场渲染+上传，实测那次 1886ms） | ~1400ms |

### 10.3 序号（sequence）是**每张卡片一个共享计数器**

`sequence` 必须相对**上一次对同一张卡片的任何操作**严格递增。用固定高序号（如 9001/9002/9003）做计时或调试，会把计数器顶高，之后正常点按全部报 `300317 sequence number compare failed`。调试时用真实计数器，或事后把状态里的 `sequence` 抬到用过的最大值之上。

### 10.4 「code=0」不等于客户端改了

组件更新接口返回 `code=0`，客户端仍可能不生效（曾出现「文字更新了、图片没更新」，卡片上文字是「当前 3天」而图还是 24小时 那张）。判定办法：

- 让用户截图，再用**数据特征反查图上那一档**（纵轴上限、横轴标签格式：24小时 是 `05:00`，3天 是 `01日04时`，7天/30天 是 `09-28`），就能确定客户端显示的是哪一档。
- 官方 FAQ（[消息卡片](https://open.feishu.cn/document/common-capabilities/message-card/message-card)）明确：**接口更新卡片必须在「响应回调请求」之后执行，并行执行或提前执行会出现更新失败**。所以「先回 toast、后台再更新」是必须的顺序，不要为了抢速度把更新塞进回调响应之前。

### 10.5 服务端已经不慢了，剩下的「转圈圈」在客户端

把端到端压到 **400～500ms** 之后，用户仍会说「慢、转圈圈、空白一会」——瓶颈转到客户端：**整块替换组件（`update_element`）会让客户端重新挂载组件**，图片控件一重挂载就转圈等新图下载解码。两条针对性做法：

1. **改属性而不是换组件**：用 `partial_update_element`，`params: {element_id, partial_element: {属性}}`（或单组件 `PATCH /cards/{card_id}/elements/{element_id}`，请求体 `partial_element`）。只动 `content` / `img_key` / `columns` 这些属性，不重挂载。**注意：不能改 `tag`**（报 `300312`），组件级属性写错报 `300313`。兜底写法：`code != 0` 时退回 `update_element`，保证「点了必定换」。
2. **画布直接按显示宽度画，别整体缩小**：一开始为了省流量把 760px 的画布缩到 0.7（532px），结果**字也被一起缩小**，手机上数值/轴标签只剩 7～8px，用户说「不要点进去横过来，直接卡片上就能这个效果」。正确做法是把画布本身设成接近卡片显示宽度（本机最终 `W,H = 540,250`、`OUT_SCALE=1.0`、`OUT_COLORS=48`），字号按画布定（标题 23 / 轴标签 18 / 数值标签 19），出图静态 9～12KB、GIF 44～59KB——**既不缩字也不浪费带宽**。

**缩放后必须重验真值**：像素变了，旧的逐列自检结论不再适用。量法要用「**该列是否存在曲线像素落在真值点 ±2.5px 内**」，别用「第一个曲线像素」或「曲线重心」——缩放后的抗锯齿和近竖直段会让这两种量法在陡坡桶上虚报 10～15px 误差。**判据是拿「真值重画的参考图」走同一条量法做对照**：参考图偏差相同 ⇒ 是量法误差，不是数据错（本机实测 GIF 与参考图逐桶最大差 1.0px）。

## 十一、静态图也要「一眼看得见数」（2026-10-04 用户指定样式）

用户给的参考图是飞书图表风格，要求**不点进去、不横屏，卡片上直接看清数**。落地要点：

- **数值标签标在数据点上**：点少（≤8）全标；点多只标**峰值 + 最新值**（24/30 个点全标会糊成一片）。防碰撞：与上一个标签水平距离 < 46px 就跳过（最后一点永远保留）。
- **网格线用点线**（PIL 没有 dash 参数，自绘短划 + 间隔），颜色 `#D6DCE3` 左右；实线在手机上看太重。
- **绘图区左右各内缩 12px**：否则首点的数值标签会撞上纵轴刻度文字（实测出现过「50004260」连成一片）。
- 数值/轴标签用灰（`TXT`），曲线与圆点用主题色（本机 turquoise `#067062`），**不要红色高亮**——用户偏好克制的蓝灰/青绿体系。
- 用户对比过「带面积渐变填充」与「纯线条」两版，选定**带填充**：`draw_frame(..., fill=True)`（默认）；要出对照图传 `fill=False`。
- 自检流程：改完先只出图（`draw_frame` 直接存 PNG，不上传、不动卡片）→ 自己用 vision 看一遍有没有文字重叠/裁切 → 再 `refresh` 整套重建。

**重建整套时**：清 `st['pairs']`、清各档 `still_key`、删掉 `GIFDIR` 下的 gif/png，再跑 `refresh`（保留 `card_id`/`message_id`/`sequence`）；改完画法不重建的话，客户端拿到的还是旧图。
