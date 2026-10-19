# Delta Client —— 三角洲行动队友房间（Windows 桌面端 / PySide6）

桌面客户端：**文字聊天、公共/私有房间、房间内共享画板、本地截屏识别技能 CD 后共享给队友（E 占位）**。
本项目只做桌面端，不做 Web；截屏与识别全部在客户端本地完成，服务端不接收图像。

> 当前进度：**C1 + C（聊天）+ D（共享画板）+ F（完善：昵称/个人资料/大厅自动刷新/房主管理/历史窗口）**。E（技能共享）仍为占位。

---

## 1. 已完成能力（C1 + C + D + F）

| 模块 | 内容 |
|---|---|
| 配置 | 服务器地址可配置（`DELTA_SERVER` / `~/.delta_client.json` / `--server`），默认 `http://127.0.0.1:8000`，无硬编码 IP |
| HTTP 客户端 | `net/api_client.py`：统一 Base URL、`X-Request-Id` / `X-Protocol-Version`、`Authorization: Bearer`、超时、错误映射 |
| WS 客户端 | `net/ws_client.py`：`/ws` 首消息 `auth`、心跳（25s ping / 90s 失联）、指数退避重连（1s→30s）、消息分发、未知类型忽略 |
| 会话 | `state/session.py`：token + 用户信息（内存；可选落盘，**不落盘密码**） |
| 历史账号（H2） | `state/saved_logins.py`：`%APPDATA%\DeltaClient\saved_logins.json`；最多 5 个账号、最近使用在前；密码用 Windows DPAPI 加密 base64 保存（30 天有效），DPAPI 不可用只存账号；登录成功保存、打开登录页自动带出最近账号/未过期密码，历史列表支持单删/清空；改密成功或登录密码错误清除该账号密码，退出登录不清历史 |
| 登录/注册 | `POST /api/v1/auth/login`、`POST /api/v1/auth/register`；注册账号 6–20 位字母/数字且至少含 1 个字母，注册密码 8–32 位（与后端一致；登录密码仍只校验非空以兼容历史短密码）；账号输入框即时过滤（注册/登录均仅字母数字，≤20；`dsh_test` 会被过滤为 `dshtest`），粘贴保留合法部分、IME 上屏后清洗；注册带 token 自动登录 |
| 昵称展示（F） | 成员列表/聊天/房主标识/加入离开提示统一显示 **nickname**（缺失时回退 username 并标记旧协议）；账号只在个人资料页对自己可见 |
| 个人资料（F） | 设置页新增「个人资料」：修改昵称（1–20，立即刷新所有展示，含历史聊天中自己的名字）、修改密码（旧密码 + 新密码 8–32 + 确认；成功后保持登录） |
| 房间 | 公共房间列表、刷新、创建（公开/私有+密码）、按 5 位房间号加入（私有需密码）、离开 |
| 我的房间（H1） | 大厅「我的房间」tab：房间名/房号/类型/人数 + 行内「退出」；`role=owner` 显示「关闭房间」（输入房名确认）；空状态提示；与公共列表共用 5s 刷新节拍，按 room id diff 更新，进行中的退出不被打断 |
| 建房表单（A） | 创建房间名/私有密码实时校验并禁用提交；密码 4–32 位提示；提交失败保留表单，仅在错误区提示 |
| 大厅自动刷新（F） | 大厅可见且有焦点时每 5s 拉列表；按 room id diff 就地更新（保留选中/滚动）；失败退避 5→10→20s，恢复后重置；进房停止 |
| 房主管理（F） | 房主房间内「房间设置」：改房间名（1–30）、改私有房密码（4–32）、删除房间（输入房间名二次确认）；处理 `room_updated`/`room_deleted` 实时事件 |
| 历史窗口（F） | 兼容历史接口 `window_days` / `truncated` 字段，提示「仅显示最近 N 天消息」 |
| 房间内页 | 成员列表（标准行 + 固定 40px 行高/右侧省略，右键菜单；WS `room_joined` + HTTP 房间详情兜底）、聊天、共享画板 |
| 房主移出（H3） | 成员行右键菜单「移出房间」：仅房主对非房主成员可用，自己/非房主 disabled；二次确认后 `POST /rooms/{ref}/kick`；成功刷新成员并提示，失败按错误码提示；处理 `room_kicked` 定向事件（自己被踢则提示并回大厅），他人被踢走 `user_left(reason=kicked)` |
| 聊天（C） | 发送 `chat_send`（带 `room_id` / `client_msg_id`）、`chat_message` 广播认领（发送中→已发送、不重复插入）、失败标红双击重试（复用 `client_msg_id`）、进房拉最近 50 条、上滚 `next_before` 续拉 |
| 画板（D/H4） | 内置三角洲地图底图（1105×1260）；画布控件锁定底图宽高比、随可用空间等比缩放并居中（宿主剩余空间留白），控件内底图铺满；坐标 0–1 = 画布像素/画布宽高（图外不绘制）；透明笔画层（橡皮 composition Clear，清空只清笔画）；画笔/橡皮/颜色/粗细/撤销/重做/清空图标工具栏（QPainter 矢量图标、快捷键、当前工具高亮）；`canvas_op` 增量（≤512 点自动分段、30 条/秒本地节流）、`room_joined.canvas_snapshot` 初始化（缺失/空时 HTTP fallback）、`(user_id,rev)` 丢弃旧包、离开/关窗前 `canvas_snapshot_save` 等 ack、快照上限 5000 笔/512KB |
| 技能面板（E2） | 房间侧栏「技能」tab：按队友一行，头像首字母/昵称/干员名 + 大招（百分比环）/技能（n/max+CD）/投掷物（n/max+CD）；ready 高亮、charging 每秒倒计时、unknown「?」、30 分钟未更新「未共享」；缓存 `skill_share_state`/`room_joined.skill_states`，`skill_share_removed` 删除；本地时钟偏移用 `auth_ok.server_time` 估算；默认关闭共享，「模拟我的技能」循环状态，开启后 `skill_share_update`（2 次/秒限频），关闭发 `skill_share_off` |
| 干员配置（E3a） | 读取 `assets/operators.json`（16 干员，slot 0/1/2 = 大招/战术技能/投掷物），面板显示干员名+技能名（hover）；设置页「干员」下拉手动选择并持久化 `operator_id`；`total_cd_ms` 缺失/0 的槽显示「CD未知」、不画环/不倒计时、上报 `state=unknown`；头像 `assets/operators/<id>.png` 存在则加载、缺失用首字母；上报带 `operator_id/operator_name` |
| 连通性测试 | 设置页「测试连接」：探测 `/health` + `/api/v1/rooms?page=1`，分别报告可达/鉴权失效/超时/网络错误 |
| 协议对齐 | PROTOCOL C/D 定稿：`data.error_code`、§7.2/§7.3 实名错误码、WS `room_id_or_code`、聊天字段、画板 `rev`/快照语义 |
| Mock | `--mock` / `DELTA_MOCK=1`：内置内存后端（昵称/聊天历史/画板快照/房主管理/我的房间），可完整离线演示 |
| 测试 | 295 个 stdlib unittest（含 27 个 PySide6 组件测试；无 PySide6 时跳过），离线可跑 |

---

## 2. 目录结构

```
delta_client/
├── main.py                  # 入口（--mock / --server / --check / --print-config）
├── config.py                # 配置加载与保存（env > 文件 > 默认，CLI 最高）
├── core/                    # 纯逻辑（仅标准库，单测直接覆盖）
│   ├── protocol.py          # PROTOCOL 常量、路径、WS 消息、响应包兼容
│   ├── errors.py            # HTTP/WS 错误 -> 统一 ApiError + 中文提示
│   ├── backoff.py           # WS 重连指数退避
│   ├── connection.py        # 连通性测试结果模型（/health + /api/v1/rooms）
│   ├── chat.py              # 聊天时间线：乐观更新/广播认领/去重/失败重试/历史分页
│   ├── canvas.py            # 画板逻辑：归一化/op 校验分段/快照上限/撤销重做/限频
│   ├── canvas_geometry.py   # 画板随底图比例/画布坐标换算（纯逻辑）
│   ├── skills.py            # E2 技能状态/倒计时/缓存/上报限频（纯逻辑）
│   ├── operators.py         # E3a 干员配置/槽位技能/CD/头像路径（纯逻辑）
│   ├── room_list.py         # 大厅列表 diff/room_key（自动刷新就地更新）
│   ├── rooms.py             # 房间号/房间名/可见性/密码校验
│   ├── models.py            # Room / Member / ChatMessage 与容错解析
│   └── validation.py        # 登录/注册输入校验、用户信息清洗
├── net/
│   ├── api_client.py        # aiohttp HTTP 客户端（/api/v1 契约）
│   ├── ws_client.py         # websockets 客户端（auth/心跳/重连）
│   └── mock_backend.py      # 可切换 Mock HTTP + Mock WS
├── state/
│   ├── session.py           # JWT 会话（可选落盘，不含密码）
│   └── saved_logins.py      # H2 历史账号/DPAPI 加密密码（30 天）
├── ui/                      # PySide6 界面
│   ├── main_window.py       # QStackedWidget + 网络编排
│   ├── login_view.py        # 登录/注册
│   ├── username_edit.py     # 账号输入框即时过滤（IME/粘贴/光标）
│   ├── room_list_view.py    # 房间大厅（公共 + 我的房间 tab）
│   ├── my_rooms_view.py     # 我的房间列表（diff/退出/关闭）
│   ├── room_view.py         # 房间内页（成员/聊天/画板）
│   ├── canvas_view.py       # 画板控件（底图/透明层/图标工具栏）
│   ├── canvas_icons.py      # 画板矢量图标（QPainter）
│   ├── skill_panel.py       # E2/E3a 技能 CD 面板（三槽/倒计时/干员配置/模拟共享）
│   ├── dialogs.py           # 创建房间 / 加入房间 / 连接设置 / 干员选择
│   ├── async_bridge.py      # asyncio 线程 <-> Qt 主线程桥
│   └── theme.py             # 深色 + 橙色 QSS 主题
├── assets/
│   ├── canvas_map.png       # 内置三角洲地图底图（1105×1260，原图，不重采样）
│   ├── operators.json       # E3a 16 干员配置（槽位/技能名/total_cd_ms/max_charges）
│   ├── operators.README.md  # 配置说明/未知 CD/版本口径
│   └── operators/           # 干员头像模板（当前缺失，UI 用首字母占位）
├── tests/                   # stdlib unittest（离线）
├── requirements.txt
└── README.md
```

> 打包：`assets/canvas_map.png`、`assets/operators.json` 及 `assets/operators/` 头像需随包分发
> （PyInstaller `--add-data "assets;assets"` 或分别 add-data），代码同时兼容 `sys._MEIPASS/assets/`；
> `DELTA_CANVAS_MAP` / `DELTA_OPERATORS_JSON` 可覆盖资源路径（调试用）。

---

## 3. 安装

需要 **Python 3.10+**（本项目在 Python 3.11 上开发）。

```powershell
cd delta_client
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

`requirements.txt`：`PySide6>=6.5`、`aiohttp>=3.8`、`websockets>=10`。

检查依赖是否就绪：

```powershell
python main.py --check
```

---

## 4. 启动

### 4.1 Mock 模式（后端未就绪也能演示，推荐先跑这个）

```powershell
python main.py --mock
```

演示账号（仅内存、仅 Mock 模式）：

| 账号 | 密码 | 说明 |
|---|---|---|
| `demo` | `demo123` | 登录后可见演示公共房间 |
| `player` | `player123` | 同上 |

Mock 数据：公共房间 `AB12C`、`K7M2P`；私有房间 `Q4W8E`，密码 `1234`。
Mock 模式可正常走完「登录 → 房间列表 → 创建/加入 → 房间内聊天回显 → 离开/退出」全流程。

### 4.2 连接真实后端

```powershell
# 方式一：命令行
python main.py --server http://127.0.0.1:8000

# 方式二：环境变量（当前终端有效）
$env:DELTA_SERVER = "http://127.0.0.1:8000"
python main.py

# 方式三：界面右上角「连接设置」，保存到 ~/.delta_client.json
python main.py
```

服务器地址优先级：**CLI `--server` > 环境变量 `DELTA_SERVER` > 配置文件 > 默认 `http://127.0.0.1:8000`**。

WebSocket 地址：

- 默认由 HTTP 地址推导：`http(s)://host[/path]` → `ws(s)://host[/path]/ws`（PROTOCOL B 阶段目标）；
- A 现状后端 WS 在 **8765** 端口，需要显式指定：`$env:DELTA_WS = "ws://127.0.0.1:8765"`，或在「连接设置」里填写。
- 地址支持反代路径前缀，例如 `https://example.com/delta` → `wss://example.com/delta/ws`。

### 4.3 配置文件 `~/.delta_client.json`

```json
{
  "server_url": "http://127.0.0.1:8000",
  "ws_url": null,
  "mock": false,
  "save_token": false,
  "request_timeout": 15.0
}
```

- `mock`：是否默认使用内置 Mock 后端（也可用 `DELTA_MOCK=1/0`）；
- `save_token`：是否把 JWT 落盘到 `~/.delta_client_session.json`（默认关闭；**任何时候都不保存密码**）；
- 相应环境变量：`DELTA_SERVER` / `DELTA_WS` / `DELTA_MOCK` / `DELTA_SAVE_TOKEN` / `DELTA_CLIENT_CONFIG`（自定义配置文件路径）/ `DELTA_SESSION_FILE`（自定义会话文件路径）。

---

## 5. 测试

纯逻辑测试只用标准库，**不需要 PySide6、不联网、不需要后端**：

```powershell
python -m unittest discover -s tests -v
```

覆盖：配置加载与优先级、URL 规范化、协议路径/WS 消息、HTTP 错误映射、WS 重连退避、房间号校验（5 位 `[A-Z0-9]`）、房间/成员/消息解析、登录注册校验、token 存取与“不落盘密码”、Mock 后端完整流程。

当前结果：**295 个用例全部通过**（约 1.0s）。

---

## 6. 后端接口依赖（B2b / C / D 已联调）

契约以 `delta_service/PROTOCOL.md` 为准；B2b（JWT + 房间）、C（聊天）、D（画板，master `3787ed9`）均已上线，客户端真实代码已对 `http://114.132.161.169:8000` 完成联调（2026-10-19）。

### 6.1 已按目标契约调用

| 用途 | 方法/路径 | 说明 |
|---|---|---|
| 登录签发 JWT | `POST /api/v1/auth/login` | 读 `data.access_token`（兼容 `token` / `accessToken`）；`user` 取 `data.user` |
| 注册 | `POST /api/v1/auth/register` | 响应同登录（含 token，客户端注册后自动登录）；404 时回退旧 `/api/users/create` |
| 公共房间列表 | `GET /api/v1/rooms` | 读 `data.items + has_more + next_before`；字段 `id/code/name/member_count/has_password/owner_id/created_at/background_id` |
| 我的房间（H1） | `GET /api/v1/rooms/mine?page=1&page_size=20` | 读 `data.items/has_more/next_before`（按加入时间倒序）；字段 `id/code/name/visibility/member_count/joined_at/role` |
| 房间详情（成员兜底） | `GET /api/v1/rooms/{room_id_or_code}` | 读 `data.{room, members:[{id,username,online}]}`；进房先渲染一次，WS `room_joined` 丢失/重连失败时按 5s 节流刷新 |
| 创建房间 | `POST /api/v1/rooms` | `{name, visibility:"public"|"private", password?}`；响应 `data.room` |
| 加入房间 | `POST /api/v1/rooms/{room_id_or_code}/join` | body `{password?}`；路径接受 5 位 room_code 或内部 id，客户端输入自动转大写 |
| 离开房间 | WS `leave_room` + `POST /api/v1/rooms/{room_id_or_code}/leave` | 客户端离开/退出/关窗先发 WS `leave_room` 再 HTTP leave；服务端广播 `user_left(reason=left)` |
| 实时连接 | `WS /ws` | 首消息 `{"type":"auth","token","protocol_version":1,"client":{...}}` |
| 加入实时频道 | WS `join_room` | `{"room_id_or_code": ...}`（同时带旧字段 `room_code` 兼容）；**前置条件：先 HTTP 加入房间**，否则 `NOT_ROOM_MEMBER`；`password` 服务端忽略；成功回 `room_joined{room,members}` |
| 聊天收发（C） | WS `chat_send` | `{client_msg_id,content,content_type,room_id}`；服务端向房间内所有连接（含发送者）广播 `chat_message`，客户端按 `client_msg_id` 认领「发送中→已发送」，不重复插入 |
| 聊天历史（C） | `GET /api/v1/rooms/{room_id_or_code}/messages` | `?before=<消息 id>&limit=50`；`data.{items,has_more,next_before}`，`items` 新→旧；进房拉最近一页，上滚用 `next_before` 续拉 |
| 画板快照（D） | `GET /api/v1/rooms/{room_id_or_code}/canvas` | `data.{strokes,rev,updated_at}`；`room_joined.canvas_snapshot` 缺失/为空时 fallback |
| 画板增量（D） | WS `canvas_op` | `{room_id,rev,op}`；op 为 `stroke{points≤512,color,width,tool}` 或 `clear`；坐标 0–1；服务端只广播给其他人 |
| 画板快照保存（D） | WS `canvas_snapshot_save` | `{room_id,rev,strokes}`（≤5000 笔 / ≤512KB）；等 `canvas_snapshot_saved` ack 后断开；离开/关窗前必须发 |
| 修改房间（F） | `PATCH /api/v1/rooms/{room_id_or_code}` | 房主：`{name?}` / `{password?}`（公开房不允许设密码，服务端 `ROOM_PASSWORD_NOT_ALLOWED`）；响应 `data.room` |
| 删除房间（F） | `DELETE /api/v1/rooms/{room_id_or_code}` | 房主：关闭房间并摘除成员会话；响应 `{closed:true}` |
| 房间事件（F） | WS `room_updated` / `room_deleted` | 实时更新房名/密码状态；删除后提示并退回大厅 |
| 移出成员（H3） | `POST /api/v1/rooms/{room_id_or_code}/kick` | body `{"user_id": <成员id>}`；房主专用，错误码 `NOT_ROOM_OWNER`/`MEMBER_NOT_FOUND`/`CANNOT_KICK_OWNER`；成功响应含最新 `members` |
| 被踢事件（H3） | WS `room_kicked` | `{room_id, room_code, by:{id,nickname}, reason:"kicked"}`；当前房间被踢时提示、清空房间状态并回大厅 |
| 技能状态（E2） | WS `skill_share_state` / `room_joined.skill_states` | 单条/列表 `{user_id,nickname,operator_id,operator_name,captured_at,updated_at,skills:[{slot,state,remaining_ms,charges,max_charges,pct}]}`；客户端按 slot 0/1/2 归位、按 user_id 缓存；空/缺失槽位仅该槽 unknown |
| 技能移除（E2） | WS `skill_share_removed` | `{user_id}`；从面板移除该队友 |
| 技能上报（E2/E3a） | WS `skill_share_update` / `skill_share_off` | `{room_id,captured_at,skills:[{slot,state,remaining_ms,charges,max_charges,pct}],operator_id,operator_name}` / `{room_id}`；默认关闭，开启后 2 次/秒本地节流，关闭时发 off；未知 CD 槽 `state=unknown` |
| 修改昵称（F） | `PATCH /api/v1/users/me` | body `{"nickname": "新昵称"}`；响应 `{"user": {...}}`；成功后本地立即更新展示、保持登录 |
| 修改密码（F） | `POST /api/v1/users/me/password` | body `{"old_password","new_password"}`；旧密码错 `WRONG_OLD_PASSWORD`、新密码不合规 `INVALID_NEW_PASSWORD`（8–32，前端先校验）；成功后 token 继续有效 |
| 心跳 | WS `ping` / 服务端 `heartbeat` | 服务端每 30s 下发；客户端 25s ping，90s 无消息判定失联 |

错误体统一读取 `data.error_code`（§1.4/§7.3），并已映射 §7.2 全部 WS 错误码（`NOT_AUTHENTICATED`/`AUTH_INVALID`/`AUTH_EXPIRED`/`NOT_ROOM_MEMBER`/`ROOM_CLOSED`/`INVALID_MESSAGE`/`INVALID_CANVAS_OP`/`CANVAS_OUT_OF_ORDER`/`RATE_LIMITED` 等）。

### 6.2 当前兼容分支（保留以兼容旧后端）

- `POST /api/v1/auth/login` 返回 404 时回退 `POST /api/users/login`（A 现状，无 token → 提示“已登录但无 JWT，聊天仅本地回显”）；
- `POST /api/v1/auth/register` 返回 404 时回退 `POST /api/users/create`；
- `GET /api/v1/rooms` 返回 404 时回退 `GET /api/room/public/list`；
- 错误体同时兼容 `{code,message,data}`、`{detail:{error_code,message}}`、`{detail:"..."}`、Pydantic 422 列表与 `data.error_code`。

### 6.3 真实联调结论（客户端实测）

- 登录：返回 `access_token`；JWT `sub`=user_id、有效期 7 天；`GET /api/v1/users/me` 正常。
- 401 形态：`40100 未认证`、`40102 登录凭证无效`；客户端按 401 清会话回登录页。
- 房间：列表分页字段齐全；创建公开/私有正确（`has_password`）；join 接受小写/大写 room_code；私有密码错误返回 HTTP 400 + `data.error_code = ROOM_PASSWORD_REQUIRED / ROOM_PASSWORD_INVALID`，客户端准确识别并弹密码框。
- 房间详情：`GET /api/v1/rooms/{code|id}` 正常返回 `room + members`（含 `online`），已作为成员兜底接入 UI。
- WS：`auth` → `auth_ok`；双账号 `room_joined` 成员互见、`user_joined` 正常；未认证发 `join_room` 返回 `NOT_AUTHENTICATED`（PR#9 §7.2 已统一为该码）。
- 断线重连：同账号新连接顶号后，客户端自动重连 → 重新 auth → 重新 `join_room` 成功。
- 离开：WS `leave_room`（填 code 或内部 id 均可）会广播 `user_left(reason=left)`；B2b 当前直接断连不广播，PR#9 起断连会清理并广播 `reason=disconnected`（客户端已按 `left/disconnected/kicked/replaced` 展示原因）。
- 连通性自检：真实后端 `/health` 与 `/api/v1/rooms?page=1` 均通过，设置页「测试连接」可区分可达/鉴权失效/超时/网络错误。
- 聊天（C，部署后实测）：双账号 `dsh_test`/`dsh_test2` 收发（A 发 A/B 都收到、B 发 A 收到）；`chat_message` 字段 `id/room_id/user/content/client_msg_id/created_at` 正确，`client_msg_id` 原样回传；历史分页 4 页 7 条无重复、顺序新→旧；5 条/秒限频第 6 条返回 `RATE_LIMITED`；2001 字返回 `INVALID_MESSAGE`；HTTP leave 后 WS 发送返回 `NOT_ROOM_MEMBER`。
- 画板（D，部署后实测）：A 画 B 实时收到 `canvas_op`（含 `user_id/rev/op`），A 无自回显；B 画 A 收到；`clear` 生效；`canvas_snapshot_save` 收到 `canvas_snapshot_saved{rev,updated_at}`，HTTP canvas 与后进房 `room_joined.canvas_snapshot` 均能恢复已保存笔画；非法 op→`INVALID_CANVAS_OP`、rev 回退→`CANVAS_OUT_OF_ORDER`、超 30 条/秒→`RATE_LIMITED`、HTTP leave 后→`NOT_ROOM_MEMBER`。
- 房间管理（F，当前 master 实测）：`PATCH /rooms/{ref}` 改名成功；私有房改密码后旧密码失效、新密码可加入；`DELETE /rooms/{ref}` 成功且删除后房间不可访问（返回 409 + `ROOM_NOT_FOUND`）；公开房设置密码返回 `ROOM_PASSWORD_NOT_ALLOWED`（UI 只对私有房展示密码修改）。
- 个人资料/房间事件（F，部署后实测）：`PATCH /users/me` 改昵称成功（响应 `{"user": {...}}`）；`POST /users/me/password` 成功且原 token 继续有效，旧密码错→`WRONG_OLD_PASSWORD`、短新密码→`INVALID_NEW_PASSWORD`；WS `room_updated`（字段 `room_id/name/visibility/has_password`）和 `room_deleted` 均已下发并被客户端处理；`room_joined`/历史接口当前暂未返回 `history_window_days`/`window_days`，客户端按缺省不提示，后端补字段后自动生效。
- 房间对象比 PROTOCOL 多 `visibility/updated_at/closed_at/background` 等字段，客户端忽略未知字段。
- 我的房间（H1）：Mock 已覆盖预置/退出/创建/删除；真实 `GET /api/v1/rooms/mine` 当前返回 404（路径被当作 room ref），接口上线后联调。底层 `POST /leave` 与房间成员减少走既有接口。
- 注册/改密密码规则：前端统一 8–32（与后端 F/B 一致），注册页 6–7 位提交前即被拦截并提示「密码至少 8 位」；登录密码只校验非空，历史短密码账号不受影响。

### 6.4 后续里程碑

1. C 聊天、D 画板均已部署并通过真实双账号联调。
2. F 客户端已完成；昵称/改密/`room_updated`/`room_deleted` 已真实联调通过，历史窗口字段待后端补返回。
3. 列表分页 UI：只渲染首屏 `items`，后续视需要加分页/滚动加载。
4. 技能共享（E）`skill_report`/`skill_state` 仍为占位，等 E 协议/通知后实现。

---

## 7. 安全约定

- 服务器地址可配置，仓库内**无硬编码 IP**；
- 密码只在登录请求体内发送，**不落盘、不写日志、不进配置文件**（H2 历史账号密码例外：仅 DPAPI 加密密文落盘，绝不明文）；
- H2 历史账号：密码用 Windows DPAPI（`CRYPTPROTECT_UI_FORBIDDEN`）加密后 base64 存入 `%APPDATA%\DeltaClient\saved_logins.json`；DPAPI 失败/非 Windows 时降级为**只存账号、不存密码**，无明文回退；
- JWT 默认只存内存；开启 `save_token` 时才落盘到 `~/.delta_client_session.json`，并用 `core.validation.sanitize_user` 清洗用户信息（去掉 password/token/secret 类字段）；
- 错误提示只展示服务端 `message` 或客户端兜底文案，5xx 不展示内部细节；
- 画板只收发矢量操作/快照（坐标+颜色+粗细），**不上传截图或图像**；截屏/OCR（E）未实现。

---

## 8. 已知限制 / TODO

- 技能共享（E）未实现，房间内技能卡片仅为占位；截屏/识别尚未接入；
- F 个人资料/房间事件接口已真实联调通过；历史窗口字段后端暂未返回，客户端已兼容，后端返回 `window_days`/`truncated` 后自动提示；
- 修改密码走 `POST /users/me/password`（8–32 位且新旧不同，前端先校验，后端错误 `WRONG_OLD_PASSWORD`/`INVALID_NEW_PASSWORD` 直接展示）；修改昵称走 `PATCH /users/me`，成功后立即更新本地展示（含聊天历史中自己的名字），不退出登录；
- 房主改房名 1–30、私有房密码 4–32；删除房间必须原样输入房间名确认；非房主看不到入口（服务端仍会校验）；
- 我的房间（H1）接口未上线前 Mock 可完整演示；真实接口 `/api/v1/rooms/mine` 当前 404，上线后按 PROTOCOL 联调；退出/关闭后立即本地移除，失败保留行并提示；
- 房主移出（H3）：成员操作改为右键菜单（行内不再放按钮，行高固定 40px，长昵称右侧省略 + tooltip）；真实 `POST /rooms/{ref}/kick` 已用 QA 双账号验证（成员被移除、返回最新 members）；`room_kicked` 定向事件当前未下发，待后端补；客户端已实现提示+回大厅，Mock 可演示；
- 大厅自动刷新仅在大厅可见且窗口有焦点时运行；失败按 5→10→20s 退避；手动刷新会重置退避；
- 历史窗口提示依赖后端返回 `window_days`/`truncated`（字段名兼容多种写法）；未返回时按普通历史展示；
- 画板 undo/redo 为**纯本地**（服务端无 undo，队友不会看到撤销，保存快照后才持久化）；`clear` 为全房间生效；
- H4 底图为客户端内置资源 `assets/canvas_map.png`（1105×1260，约 2MB），打包需 add-data；画布控件锁定底图宽高比，随宿主可用空间等比缩放居中（宿主外部留白，控件内部底图铺满、不裁切/不留边）；坐标 0–1 以画布控件为基准，不做旧视口坐标迁移（线上无真实数据）；
- E3a 干员配置来自 `assets/operators.json`（16 人）；当前 `assets/operators/*.png` 头像模板尚未提供，UI 用首字母占位，文件存在时自动加载；`total_cd_ms` 为 null/0 的 5 个槽位显示「CD未知」，不画环/不倒计时、上报 `state=unknown`；E3b 截图识别尚未开始（显示模式/OCR 依赖待确认）。
- 画板快照只在离开房间/关闭应用/切服务器时显式保存（服务端无定时快照），进程崩溃可能丢失未保存增量；快照上限 5000 笔 / 512KB，超限会提示「画布已满」；
- 房间列表暂无分页；只渲染 `items` 首屏；
- 成员列表以 WS `room_joined` 为准，HTTP 房间详情做兜底（进房一次 + 重连失败时 5s 节流）；
- 聊天：进房拉最近 50 条，上滚按 `next_before` 续拉（服务端 `items` 新→旧）；发送失败/超时标红，双击重试复用同一 `client_msg_id`；`RATE_LIMITED` 会保留输入内容；
- 断线重连后自动重新 `join_room`，画板以 `room_joined.canvas_snapshot` 为准（不保留旧增量）；
- 离开房间/退出登录/关闭窗口会先保存画板快照、再发 WS `leave_room` 与 HTTP leave；
- 设置页「测试连接」使用当前登录 token 探测 `/health` 与 `/api/v1/rooms?page=1`，未登录时会显示鉴权失效；
- Mock 后端只用于演示，不模拟限频/多客户端/持久化（但包含昵称、聊天历史、画板快照、房主管理、我的房间、踢人/room_kicked，可离线演示）；
- 若后端返回的登录响应没有 token，界面会提示并进入“无 JWT 兼容模式”（聊天仅本地回显）。

---

## 9. 开发约定

- 纯逻辑（config/core/state）不得 import PySide6/aiohttp/websockets，保证离线单测；
- aiohttp / websockets 采用函数内延迟导入，缺失依赖时给出明确安装提示；
- 新增 UI 页面时沿用 `ui/` + 信号/槽，网络请求统一经 `AsyncBridge` 提交，不在 UI 线程直接 `asyncio.run`；
- **聊天/画板协议细节、已知限制与 TODO 见 [`CLIENT-NOTES.md`](CLIENT-NOTES.md)**（交接必读）。





