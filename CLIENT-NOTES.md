# CLIENT-NOTES —— 客户端交接/踩坑记录（聊天 C + 画板 D + F 完善）

> 面向后续接手客户端的人。协议以 `delta_service/PROTOCOL.md` 为准，本文件只记录**实现时踩过的坑、易错点、已知限制和 TODO**。
> 更新时间：2026-10-19；对应客户端 commit：F 完成后。

---

## 1. 当前进度与分支

| 项 | 状态 |
|---|---|
| C1 骨架/配置/登录/房间 | 完成 |
| C 聊天（收发/历史/乐观更新/失败重试） | 完成，已对线上双账号实测 |
| D 共享画板（实时增量/快照/撤销重做） | 完成，已对线上双账号实测 |
| F 完善（昵称展示/个人资料/大厅自动刷新/房主管理/历史窗口） | 完成，资料/房间事件已真实联调；历史窗口字段待后端返回 |
| H1 我的房间 + A 建房表单 + B 密码上限 32 | 完成，Mock/冒烟通过；真实 `/rooms/mine` 当前 404，待后端上线联调 |
| H3 房主移出成员 + room_kicked | 完成，右键菜单/行高修复；Mock/冒烟通过；真实 `POST /kick` 已验证，`room_kicked` 事件待后端下发 |
| H4 画板底图 + 图标工具栏 | 完成，画布随底图比例/透明笔画层/图标工具栏；单测+截图冒烟通过 |
| E2 技能 CD 面板 | 完成，Mock 两队友三状态/倒计时/共享开关/模拟数据；真实 E1 接口待联调 |
| E1/E3 技能采集管线 | **未开始**（E3 ROI 规则已记录：队友列表最底部「自己」；不传图像） |

- 本地工作副本：`.tmp/client-work`，当前分支 `feat/skill-panel`。
- 远端集成分支：`feat/client-chat`（lead 用 patch 应用，不要直接改远端）。
- 测试：`python -m unittest discover -s tests -v` → **280 用例**（含 20 个 PySide6 组件测试；无 PySide6 时跳过），离线可跑。
- GUI 冒烟脚本在 `.tmp/client-work-smoke/`（不在仓库内）：`smoke.py`（登录/房间/聊天/设置）、`smoke_canvas.py`（画板保存/恢复）、`smoke_canvas_map.py`（底图比例/坐标/透明层/图标工具栏/截图）、`smoke_skill_panel.py`（技能面板三状态/开关/模拟/移除截图）、`smoke_f.py`（昵称/注册规则/资料/房主管理）、`smoke_username_input.py`（输入过滤/粘贴/光标/IME/注册密码边界）、`smoke_my_rooms.py`（我的房间/退出/关闭/空态）、`smoke_create_room.py`（建房实时校验/失败保留表单/密码 4–32）、`smoke_saved_logins.py`（历史账号/重启带出/删除/失败清密码）、`smoke_kick.py`（右键移出/room_kicked 回大厅）、`smoke_member_menu.py`（多成员/长昵称/行高/右键菜单状态/截图）、`live_*.py`（真实后端联调）。
- 本机沙箱曾把 PySide6 装到 `.tmp/pydeps` 并用 `PYTHONPATH` 跑 GUI；正常开发直接 `pip install -r requirements.txt`。

---

## 2. 协议注意事项（聊天 C）

1. **统一错误包**：`{code,message,data,request_id}`，具体业务码在 **`data.error_code`**（字符串），顶层 `code` 只是 40000/40100 之类类别。客户端 `core.errors.parse_error_body` 已同时读 `data.error_code`。
2. **WS 错误**：`{"type":"error","code","error_code","message"}`；错误**不带 `client_msg_id`**，所以一次错误只能把当前所有 pending 聊天标记失败（通常只有一条）。`RATE_LIMITED` 要恢复输入框内容。
3. **chat_send**：必须已认证 + 已 HTTP join + 已 WS join；服务端**不读 `room_id`**（用会话房间），但客户端仍按约定带上便于日志。限频 **5 条/秒/用户**。
4. **chat_message**：字段固定 `id/room_id/user{id,username}/content/client_msg_id/created_at`；**发送者本人也会收到广播**，必须按 `client_msg_id` 原地认领（发送中→已发送），不能重复插入。
5. **历史**：`GET /rooms/{room_id_or_code}/messages?before=<消息 id>&limit=50`，`items` **新→旧**，游标是**消息 id 字符串**（不是时间戳）；进房拉第一页，上滚用 `next_before`。
6. **重试**：服务端无幂等承诺；同一条内容重试要复用**同一个 `client_msg_id`**，UI 侧靠它避免自己重复渲染（服务端仍可能落两条，属已知限制）。
7. **加入前置**：WS `join_room` 前必须先 HTTP join，否则 `NOT_ROOM_MEMBER`。
8. **离开**：先 WS `leave_room`（触发 `user_left(reason=left)`）再 HTTP leave；HTTP leave 会摘除该用户 WS 房间会话。房主直接 HTTP leave 会失败（需先关房）。
9. **心跳**：服务端每 30s 下发；客户端 25s ping、90s 无消息判失联（`net/ws_client.py` 默认值）。
10. **房间关闭**：HTTP close 会摘除全部成员 WS 会话并广播 `user_left(reason=closed)`；之后 `chat_send`/`canvas_op` 返回 `NOT_ROOM_MEMBER`。

---

## 3. 协议注意事项（画板 D）

1. **坐标**：一律 **0–1 归一化** `{x,y}`；H4/H5 起坐标基准是**画布控件本身**（控件宽高比=底图 1105:1260，控件随宿主等比缩放居中），`x=px/画布宽`、`y=py/画布高`；换算在 `core/canvas_geometry.py` / `ui/canvas_view.py`。
2. **op**：`stroke{points≤512,color:#RRGGBB,width:1–32,tool:pen|eraser}` 或 `clear`；单笔 >512 点客户端自动分段（相邻段共享端点）。
3. **rev**：**每连接、每房间**独立单调递增，重连/重进房从 0 重新计数；服务端丢弃 `rev<=上次` 并回 `CANVAS_OUT_OF_ORDER`。客户端对**别人**的 op 按 `(user_id,rev)` 去重；收到 `rev=0` 视为该用户新连接，`user_joined` 时清掉该用户旧水位。
4. **不回显发送者**：`canvas_op` 广播**不含发送者**；本地绘制必须自己先渲染（`CanvasDocument`），不要等广播。
5. **快照**：`room_joined.canvas_snapshot={strokes,rev}`（DB 快照 ∪ 内存未保存增量）；`strokes` 里可能含 `clear`，按顺序应用即可（client `CanvasDocument.apply_snapshot` 处理）。缺失/为空时 fallback `GET /rooms/{ref}/canvas`（无快照返回 `strokes:[],rev:0,updated_at:null`）。
6. **保存**：只在显式 `canvas_snapshot_save{room_id,rev,strokes}` 或房主关房时落库；**无定时快照**。客户端在离开/退出/关窗/切服务器前保存并等 `canvas_snapshot_saved` ack（3s 超时）。
7. **上限**：快照 ≤5000 笔、序列化 ≤512KB；op 校验失败 `INVALID_CANVAS_OP`；画板限频 **30 条/秒/用户**（客户端本地节流队列）。
8. **重连**：一律以 `room_joined.canvas_snapshot` 为准，不保留重连前的本地增量（客户端会直接覆盖本地画布）。
9. **clear**：全房间生效，任何成员都可发；服务端把状态置空。
10. **undo/redo**：服务端**没有 undo**；客户端只用本地 `CanvasDocument` 历史实现，队友看不到撤销，直到再次 `canvas_snapshot_save` 才落库。

---

## 4. 已知限制 / 坑（按模块）

### 聊天
- 服务端错误无 `client_msg_id`：多 pending 时无法精确知道失败的是哪条，客户端会把全部 pending 标红；尽量串行发送。
- 无幂等：失败重试可能让服务端落重复消息；UI 只按 `client_msg_id` 规避自己重复渲染。
- 历史分页理论上同毫秒消息可能漏行（服务端按 `created_at` 过滤，已知限制）；客户端按 `before` 消息 id 续拉。
- 只渲染首屏 50 条 + 上滚续拉；不做“新消息提示/跳到底部”。
- `ROOM_CLOSED` 时本地可能仍有 pending，已统一标红并 1.2s 后回大厅。

### 画板
- **undo/redo 仅本地**，不影响服务端/队友；远端 op 到达会清空本地 undo/redo 历史（避免撤销误删队友笔画）。
- 橡皮通过“背景色覆盖”渲染（op 里仍保存 tool=eraser），保存/回放一致。
- 离开/关窗保存超时只提示状态栏，仍会离开（可能丢增量）；快照超 5000 笔/512KB 会弹「画布已满」询问是否继续离开。
- 进程崩溃/强杀：未显式保存的增量丢失（服务端无自动快照）。
- 进房时 `canvas_snapshot` 为空也会再发一次 HTTP canvas fallback（冗余请求，无害）。
- 本地 30/s 节流队列在断线时会清空并提示“画板改动仅本地可见”；重连后以服务端快照为准（本地改动会丢）。
- `UI` 画板面板固定宽 400px，小窗口下聊天区会被压缩；画布本身按底图比例缩放，宿主留白。
- 快照保存 ack 只有单条在途；`WsClient.save_canvas_snapshot` 用单 waiter 列表（并发保存请自行串行）。

### F：昵称 / 个人资料 / 大厅自动刷新 / 房主管理 / 历史窗口（新）
- **昵称兼容**：`user` 对象从 `{id,username}` 变为 `{id,nickname}`；`Member`/`ChatMessage` 解析优先 `nickname`，缺失回退 `username` 并置 `legacy_protocol=True`。展示层一律用 `display_name`（昵称），账号只在个人资料页出现。
- **注册账号规则**：6–20 位字母/数字、至少 1 个字母；登录页输入框同样只允许字母/数字（不再兼容 `dsh_test` 等下划线账号，输入 `dsh_test` 会变 `dshtest`）；失败码 `INVALID_USERNAME`。前端 `LoginView` 有实时提示。
- **注册密码**：与改密共用 `NEW_PASSWORD_MIN/MAX`（8–32）；`MIN_REGISTER_PASSWORD_LENGTH = NEW_PASSWORD_MIN` 仅作旧别名，勿单独改。登录密码仍只校验非空（历史 6 位账号可登录）。
- **账号输入框（G）**：`core.validation.sanitize_username_input(text, mode)` 纯函数即时过滤；注册/登录完全一致，仅 ASCII 字母/数字（≤20）。`ui.username_edit.UsernameLineEdit` 负责粘贴/输入/模式切换；过滤后按“光标前保留字符数”回退光标（不跳末尾）；IME preedit 期间跳过清洗、上屏后再过滤。
- **个人资料**：`SettingsDialog` 新增「个人资料」tab；昵称 1–20，改密旧密码 + 新密码 8–32 + 确认。**已按 F 后端契约实现**：
  - 改昵称 `PATCH /api/v1/users/me {"nickname": ...}`（响应 `{"user": {...}}`，客户端取 `user`）；
  - 改密 `POST /api/v1/users/me/password {"old_password","new_password"}`；错误码 `WRONG_OLD_PASSWORD` / `INVALID_NEW_PASSWORD` 均已映射中文文案；成功后 token 继续有效，只更新本地 session（不退出登录）。
  - 旧的 404/405/422 猜测回退已删除；改名与改密是两个独立调用。
- **大厅自动刷新**：QTimer 5s，仅大厅可见且窗口 active 时运行；`core.room_list.diff_rooms` 按 room key 做 added/removed/updated，`RoomListView.update_rooms` 就地改单元格并恢复选中/滚动；失败用 `ReconnectBackoff(base=5,factor=2,max_delay=20)` 退避，成功 reset。手动刷新会 reset 退避。
- **房主管理**：`RoomSettingsDialog`；改名 1–30、私有房密码 4–32、删除需原样输入房间名。HTTP `PATCH/DELETE /api/v1/rooms/{ref}` 已实测；公开房不能设密码（`ROOM_PASSWORD_NOT_ALLOWED`）。WS `room_updated`（字段 `room_id/name/visibility/has_password`，无 `room` 包装）与 `room_deleted` 已实测下发；客户端处理逻辑已接通。
- **H1 我的房间**：`MyRoom`/`parse_my_rooms_page` 解析 `items/has_more/next_before`；大厅 `QTabWidget`（公共/我的房间），`MyRoomsView` 按 room id diff、保留滚动/选中与正在退出的按钮禁用态。`role=owner` 显示「关闭房间」（`QInputDialog` 输入房名确认后走 DELETE），其它显示「退出」（`QMessageBox` 二次确认后走 leave）；成功后立即移除，当前房间被退/关时回大厅。与公共列表共用 5s `_refresh_lobby` 节拍；`room_deleted` 也会移除对应行。**真实 `/api/v1/rooms/mine` 当前 404**，Mock 已完整演示，接口上线后联调。
- **A 建房表单**：`CreateRoomDialog` 实时校验房间名（1–30）与私有密码（4–32），非法时提示并禁用创建；提交失败只写错误区、保留名称/可见性/密码，按钮恢复可再次提交；切回公开时清密码和旧错误。
- **B 密码上限 32**：`NEW_PASSWORD_MAX=32`（注册/改密共用，登录仍只校验非空）；`ROOM_PASSWORD_MAX=32`、房间密码 4–32；提示文案/错误码同步。
- **H2 历史账号**：`state/saved_logins.py` 存 `%APPDATA%\DeltaClient\saved_logins.json`（`DELTA_SAVED_LOGINS_FILE` 可覆盖），结构 `{version, entries:[{username, secret, saved_at, expires_at, last_used_at}]}`；最多 5 条按 `last_used_at` 倒序。密码用 DPAPI `CryptProtectData`（`CRYPTPROTECT_UI_FORBIDDEN`）加密后 base64 存 `secret`；DPAPI 不可用/失败只存账号，**绝不明文回退**。密码有效期 30 天（`now >= expires_at` 视为过期，29 天可用/30 天过期/31 天过期）；登录成功 upsert 到首位，打开登录页带出最近账号+未过期密码，历史列表可选中/单删/清空；改密成功、登录 AUTH 失败清密码保留账号；退出登录不清历史。
- **H3 房主移出成员**：成员行改为**右键菜单**（不再行内放按钮）：QListWidget 标准 item + 固定 40px 行高、右侧省略、tooltip 完整昵称、无横向滚动；右键任意位置弹 `QMenu`「移出房间」——房主对非房主启用，自己/非房主 disabled。触发后 MainWindow 二次确认「确定将《昵称》移出房间？」→ `POST /api/v1/rooms/{ref}/kick {"user_id"}`，成功刷新成员并提示、失败保留列表并提示错误。处理 `room_kicked`：当前房间匹配则提示「你已被房主《by.nickname》移出房间」→ 停 WS、清空状态回大厅；其它房间仅提示。他人被踢继续走 `user_left(reason=kicked)`。Mock 增加 `kick_member` 与 `MockWsClient.simulate_room_kicked()`；真实 `POST /kick` 已验证，`room_kicked` 待后台下发。
  - **成员行扁平根因**：上一版自定义行 widget 无 `minimumHeight`，`QListWidgetItem.setSizeHint(row.sizeHint())` 在布局 polish 前取到接近 0 的高度，叠加 `QListWidget::item` 的 QSS `padding:7px`，行高被压到 ~14px，长昵称/按钮又把行撑宽，文字被压扁不可见。现改用标准 item + `QSize(0,40)`，主题增加 `QListWidget#MemberList::item { padding:9px; min-height:40px; }`。
- **H4 画板底图 + 图标工具栏**：底图 `assets/canvas_map.png`（原图 1105×1260，不重采样；`DELTA_CANVAS_MAP` 可覆盖）。`CanvasHost.resizeEvent` 用 `min(可用宽/图宽, 可用高/图高)` 算画布尺寸并居中，画布控件宽高比=底图比例；控件内部底图铺满、无 letterbox/裁切；宿主剩余空间普通留白。坐标 0–1 = `px/画布宽, py/画布高`。渲染顺序：底图 → 透明笔画层（橡皮 `CompositionMode_Clear`，清空只清层）。工具栏在画板底部，7 个 QPainter 矢量图标（画笔/橡皮/颜色/粗细/撤销/重做/清空），44px 等宽铺满，带 tooltip + 快捷键（P/E/C/W/Ctrl+Z/Ctrl+Shift+Z/Ctrl+Delete），画笔/橡皮 checkable 高亮。打包需把 assets 以 add-data 带上（代码兼容 `_MEIPASS/assets`）。
- **E2 技能 CD 面板**：`core/skills.py` 解析 E1 真实载荷 `skills` 数组（`slot` 0/1/2 归位，读 `pct`/`remaining_ms`/`charges`/`max_charges`/`state`；`state` 仅 ready/charging/unknown，其它归 unknown；缺失槽位才补 unknown）及旧对象格式，`SkillBook` 按 user_id 缓存；`SkillPanel` 每秒按 `server_now = local_now + offset` 刷新倒计时，`remaining_now = remaining_ms - (server_now - captured_at)`；ready 金色高亮/呼吸，unknown「?」，>30 分钟未更新显示「未共享」；`skill_share_removed` 删除。开关默认关闭，「模拟我的技能」循环 ready/charging/unknown，开启后 `skill_share_update`（本地 2 次/秒节流），关闭发 `skill_share_off`。Mock 预置两名队友并可 `simulate_skill_state/removed`。
- **E3 ROI 备注（尚未实现）**：队友列表里「自己」是最底部一项（与编号无关）；干员识别 ROI = 左侧列表最底部一项，底部左侧自己的头像+名字可互为兜底；识别结果按当前对局缓存，换局/重进游戏重置。
- **历史窗口**：`ChatPage.window_days` / `truncated` 从历史接口（键名兼容 `window_days/history_window_days/days` 等）或 `room_joined.history_window_days` 读取，UI 提示「仅显示最近 N 天消息」；当前部署两者均未返回，所以默认不提示，后端补字段后自动生效。

### 通用
- `AsyncBridge` 是单 asyncio 线程 + Qt 30ms 轮询；网络回调一律经 `bridge.post` 回主线程。
- 关闭窗口时用 `QEventLoop` 轮询等保存协程（最多 3s），期间窗口是卡住的，属预期。
- Mock 后端是单客户端内存模型：聊天/画板广播不会真的发给“另一个 Mock 客户端”；画板 snapshot save 有 ack、聊天有回显。
- Mock 不模拟限频/多客户端/持久化。
- PySide6 版本差异：本地验证用 `PySide6-Essentials 6.12`；代码只用 QtWidgets/QtCore/QtGui 基础 API，`requirements.txt` 写 `PySide6>=6.5`。
- 字体：离屏截图需 `QT_QPA_FONTDIR=C:\Windows\Fonts` 才有中文；正常桌面无需设置。
- 测试以 stdlib unittest 为主；`tests/test_create_room_dialog.py` 需要 PySide6（无则跳过），其余 core 测试不依赖 GUI/网络库。

---

## 5. 后续 TODO / 可优化项

1. **E 技能共享**（等拍板）：本地截屏+识别得到 `ready_at`，只上报结构化快照；绝不发送图像。
2. 画板底图（运营预置 `background`）目前未渲染，只存了 `background_id`；D 协议里底图字段已预留。
3. 画板“定期自动保存快照”可加（服务端当前无定时快照），但注意 LWW 覆盖。
4. 画板 op 批量合并：目前一笔一 op；高速绘制可合并相邻点减少 op 数。
5. 聊天：新消息未读提示、自动回到底部、历史加载 loading 态更明显；可做失败消息点击重试（现在是双击）。
6. 分页 UI：房间列表只有首屏 `items`。
7. 设置页可加 WS 连通性测试（现在只测 `/health` 与 rooms）。
8. 服务端若提供幂等去重（client_msg_id 唯一）可去掉 UI 侧重复消息兜底。
9. 增加 GUI 自动化测试（pytest-qt 等）——当前 280 个测试中 20 个为 PySide6 组件测试，其余为纯逻辑；复杂交互仍用冒烟脚本验证。
10. E3 干员识别：ROI 为队友列表最底部「自己」；底部左侧头像+名字兜底；按当前对局缓存，换局/重进游戏重置。

---

## 6. 复验命令（交接/回归）

```powershell
cd .tmp/client-work
python -m unittest discover -s tests -v       # 171 tests, 离线
python main.py --check                        # 依赖与配置
python main.py --mock                         # 离线演示（demo/demo123）
python main.py --server http://114.132.161.169:8000   # 线上（测试账号由 lead 提供）
```

真实联调脚本（不提交，路径 `.tmp/client-work-smoke/`）：
- `live_chat.py`：双账号聊天收发/历史分页/限频/非法消息/成员校验；
- `live_canvas.py`：双账号画板实时/无自回显/clear/save ack/后进房快照/错误码；
- `smoke_canvas.py`、`smoke_canvas_map.py`、`smoke.py`、`smoke_conn_test.py`：离屏 GUI 冒烟。

