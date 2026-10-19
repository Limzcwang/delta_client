# Delta Client —— 三角洲行动队友房间（Windows 桌面端 / PySide6）

桌面客户端：**文字聊天、公共/私有房间、房间内画板协同（D 占位）、本地截屏识别技能 CD 后共享给队友（E 占位）**。
本项目只做桌面端，不做 Web；截屏与识别全部在客户端本地完成，服务端不接收图像。

> 当前进度：**C1（骨架 + JWT 登录 + 房间界面）+ C（聊天：收发 / 历史 / 乐观更新）**。画板（D）与截屏/技能（E）仅为占位，未实现。

---

## 1. 已完成能力（C1 + C 聊天）

| 模块 | 内容 |
|---|---|
| 配置 | 服务器地址可配置（`DELTA_SERVER` / `~/.delta_client.json` / `--server`），默认 `http://127.0.0.1:8000`，无硬编码 IP |
| HTTP 客户端 | `net/api_client.py`：统一 Base URL、`X-Request-Id` / `X-Protocol-Version`、`Authorization: Bearer`、超时、错误映射 |
| WS 客户端 | `net/ws_client.py`：`/ws` 首消息 `auth`、心跳（25s ping / 90s 失联）、指数退避重连（1s→30s）、消息分发、未知类型忽略 |
| 会话 | `state/session.py`：token + 用户信息（内存；可选落盘，**不落盘密码**） |
| 登录/注册 | `POST /api/v1/auth/login`、`POST /api/v1/auth/register`（404 时回退旧接口；注册带 token 自动登录） |
| 房间 | 公共房间列表、刷新、创建（公开/私有+密码）、按 5 位房间号加入（私有需密码）、离开 |
| 房间内页 | 成员列表（WS `room_joined` + HTTP 房间详情兜底）、聊天（WS 实时 + 历史分页 + 乐观更新）、画板占位 |
| 聊天（C） | 发送 `chat_send`（带 `room_id` / `client_msg_id`）、`chat_message` 广播认领（发送中→已发送、不重复插入）、失败标红双击重试（复用 `client_msg_id`）、进房拉最近 50 条、上滚 `next_before` 续拉 |
| 连通性测试 | 设置页「测试连接」：探测 `/health` + `/api/v1/rooms?page=1`，分别报告可达/鉴权失效/超时/网络错误 |
| 协议对齐 | PROTOCOL C 定稿 + PR#9：`data.error_code`、§7.2/§7.3 实名错误码、WS `room_id_or_code` 与 join 前置条件、聊天字段 `id/user/content/client_msg_id/created_at` |
| Mock | `--mock` / `DELTA_MOCK=1`：内置内存后端（含聊天历史），后端接口未就绪也能完整演示 |
| 测试 | 150 个纯逻辑 stdlib unittest，离线可跑 |

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
│   ├── rooms.py             # 房间号/房间名/可见性/密码校验
│   ├── models.py            # Room / Member / ChatMessage 与容错解析
│   └── validation.py        # 登录/注册输入校验、用户信息清洗
├── net/
│   ├── api_client.py        # aiohttp HTTP 客户端（/api/v1 契约）
│   ├── ws_client.py         # websockets 客户端（auth/心跳/重连）
│   └── mock_backend.py      # 可切换 Mock HTTP + Mock WS
├── state/
│   └── session.py           # JWT 会话（可选落盘，不含密码）
├── ui/                      # PySide6 界面
│   ├── main_window.py       # QStackedWidget + 网络编排
│   ├── login_view.py        # 登录/注册
│   ├── room_list_view.py    # 房间大厅
│   ├── room_view.py         # 房间内页（成员/聊天/画板占位）
│   ├── dialogs.py           # 创建房间 / 加入房间 / 连接设置
│   ├── async_bridge.py      # asyncio 线程 <-> Qt 主线程桥
│   └── theme.py             # 深色 + 橙色 QSS 主题
├── tests/                   # stdlib unittest（离线）
├── requirements.txt
└── README.md
```

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

当前结果：**150 个用例全部通过**（约 0.5s）。

---

## 6. 后端接口依赖（C1 / B2b 联调 + PR#9 对齐）

契约以 `delta_service/PROTOCOL.md` 为准（含待合并的 PR #9 聊天契约改动）：B2b（JWT + 房间模型 + WS 认证）已上线，C1 已用客户端真实代码对 `http://114.132.161.169:8000` 完成联调（2026-10-19）；PR #9 尚未合并/部署，客户端已提前按它的 §1.4 / §6.3 / §7.2 / §7.3 对齐。

### 6.1 已按目标契约调用

| 用途 | 方法/路径 | 说明 |
|---|---|---|
| 登录签发 JWT | `POST /api/v1/auth/login` | 读 `data.access_token`（兼容 `token` / `accessToken`）；`user` 取 `data.user` |
| 注册 | `POST /api/v1/auth/register` | 响应同登录（含 token，客户端注册后自动登录）；404 时回退旧 `/api/users/create` |
| 公共房间列表 | `GET /api/v1/rooms` | 读 `data.items + has_more + next_before`；字段 `id/code/name/member_count/has_password/owner_id/created_at/background_id` |
| 房间详情（成员兜底） | `GET /api/v1/rooms/{room_id_or_code}` | 读 `data.{room, members:[{id,username,online}]}`；进房先渲染一次，WS `room_joined` 丢失/重连失败时按 5s 节流刷新 |
| 创建房间 | `POST /api/v1/rooms` | `{name, visibility:"public"|"private", password?}`；响应 `data.room` |
| 加入房间 | `POST /api/v1/rooms/{room_id_or_code}/join` | body `{password?}`；路径接受 5 位 room_code 或内部 id，客户端输入自动转大写 |
| 离开房间 | WS `leave_room` + `POST /api/v1/rooms/{room_id_or_code}/leave` | 客户端离开/退出/关窗先发 WS `leave_room` 再 HTTP leave；服务端广播 `user_left(reason=left)` |
| 实时连接 | `WS /ws` | 首消息 `{"type":"auth","token","protocol_version":1,"client":{...}}` |
| 加入实时频道 | WS `join_room` | `{"room_id_or_code": ...}`（同时带旧字段 `room_code` 兼容）；**前置条件：先 HTTP 加入房间**，否则 `NOT_ROOM_MEMBER`；`password` 服务端忽略；成功回 `room_joined{room,members}` |
| 聊天收发（C） | WS `chat_send` | `{client_msg_id,content,content_type,room_id}`；服务端向房间内所有连接（含发送者）广播 `chat_message`，客户端按 `client_msg_id` 认领「发送中→已发送」，不重复插入 |
| 聊天历史（C） | `GET /api/v1/rooms/{room_id_or_code}/messages` | `?before=<消息 id>&limit=50`；`data.{items,has_more,next_before}`，`items` 新→旧；进房拉最近一页，上滚用 `next_before` 续拉 |
| 心跳 | WS `ping` / 服务端 `heartbeat` | PR#9：服务端每 30s 下发；客户端 25s ping，90s 无消息判定失联 |

错误体统一读取 `data.error_code`（PR#9 §1.4/§7.3），并已映射 §7.2 全部 WS 错误码（`NOT_AUTHENTICATED`/`AUTH_INVALID`/`AUTH_EXPIRED`/`NOT_ROOM_MEMBER`/`ROOM_CLOSED`/`INVALID_MESSAGE`/`CANVAS_SEQ_GAP` 等）。

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
- 聊天（C）：客户端按 C 定稿实现（乐观更新、广播认领、历史分页、失败重试），mock + 单测已打通；真实双账号联调待 C 部署完成后执行（本机检查部署 OpenAPI 时仍为 B2b）。
- 房间对象比 PROTOCOL 多 `visibility/updated_at/closed_at/background` 等字段，客户端忽略未知字段。

### 6.4 后续里程碑 / 待部署

1. C 聊天代码已合并（bebb15e）但部署尚需确认：部署前 `/api/v1/rooms/{ref}/messages` 返回 404、`chat_send` 仍为 B2b 行为；客户端实现已就绪，部署后按双账号清单复验。
2. 列表分页 UI：C1 只渲染首屏 `items`，后续视需要加分页/滚动加载。
3. 画板（D）`canvas_*` 与技能（E）`skill_*` 本轮仅占位。

---

## 7. 安全约定

- 服务器地址可配置，仓库内**无硬编码 IP**；
- 密码只在登录请求体内发送，**不落盘、不写日志、不进配置文件**；
- JWT 默认只存内存；开启 `save_token` 时才落盘到 `~/.delta_client_session.json`，并用 `core.validation.sanitize_user` 清洗用户信息（去掉 password/token/secret 类字段）；
- 错误提示只展示服务端 `message` 或客户端兜底文案，5xx 不展示内部细节；
- 截屏/OCR/画板（D/E）本轮未实现，客户端不采集、不上传屏幕内容。

---

## 8. 已知限制 / TODO

- 画板（D）与截屏/技能识别（E）未实现，房间内画板卡片仅为占位；
- 房间列表暂无分页/自动定时刷新（提供手动刷新）；只渲染 `items` 首屏；
- 成员列表以 WS `room_joined` 为准，HTTP 房间详情做兜底（进房一次 + 重连失败时 5s 节流）；
- 聊天：进房拉最近 50 条，上滚按 `next_before` 续拉（服务端 `items` 新→旧）；发送失败/超时标红，双击重试复用同一 `client_msg_id`；`RATE_LIMITED` 会保留输入内容；
- 断线重连后会自动重新 `join_room` 并依赖 `room_joined` 恢复状态（画板/技能快照本轮不消费）；
- 离开房间/退出登录/关闭窗口会先发 WS `leave_room`，确保队友收到 `user_left`；
- 设置页「测试连接」使用当前登录 token 探测 `/health` 与 `/api/v1/rooms?page=1`，未登录时会显示鉴权失效；
- Mock 后端只用于演示，不模拟限频、多客户端并发与持久化（但包含聊天历史，可离线演示收发/乐观更新）；
- 若后端返回的登录响应没有 token，界面会提示并进入“无 JWT 兼容模式”（聊天仅本地回显）。

---

## 9. 开发约定

- 纯逻辑（config/core/state）不得 import PySide6/aiohttp/websockets，保证离线单测；
- aiohttp / websockets 采用函数内延迟导入，缺失依赖时给出明确安装提示；
- 新增 UI 页面时沿用 `ui/` + 信号/槽，网络请求统一经 `AsyncBridge` 提交，不在 UI 线程直接 `asyncio.run`。
