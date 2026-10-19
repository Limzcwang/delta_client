# Delta Client —— 三角洲行动队友房间（Windows 桌面端 / PySide6）

桌面客户端：**文字聊天、公共/私有房间、房间内画板协同（C2 占位）、本地截屏识别技能 CD 后共享给队友（C3 占位）**。
本项目只做桌面端，不做 Web；截屏与识别全部在客户端本地完成，服务端不接收图像。

> 当前进度：**C1（工程骨架 + JWT 登录 + 房间界面）**。画板与截屏仅为占位，未实现。

---

## 1. 本轮 C1 已完成

| 模块 | 内容 |
|---|---|
| 配置 | 服务器地址可配置（`DELTA_SERVER` / `~/.delta_client.json` / `--server`），默认 `http://127.0.0.1:8000`，无硬编码 IP |
| HTTP 客户端 | `net/api_client.py`：统一 Base URL、`X-Request-Id` / `X-Protocol-Version`、`Authorization: Bearer`、超时、错误映射 |
| WS 客户端 | `net/ws_client.py`：`/ws` 首消息 `auth`、心跳、指数退避重连（1s→30s）、消息分发、未知类型忽略 |
| 会话 | `state/session.py`：token + 用户信息（内存；可选落盘，**不落盘密码**） |
| 登录/注册 | `/api/v1/auth/login`（404 时回退 A 现状 `/api/users/login`，无 token 给出明确提示）+ `/api/users/create` |
| 房间 | 公共房间列表、刷新、创建（公开/私有+密码）、按 5 位房间号加入（私有需密码）、离开 |
| 房间内页 | 成员列表（WS 驱动）、聊天（WS 实时 + 本地回显）、画板占位 |
| Mock | `--mock` / `DELTA_MOCK=1`：内置内存后端，后端 B 阶段接口未就绪也能完整演示 |
| 测试 | 107 个纯逻辑 stdlib unittest，离线可跑 |

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

当前结果：**109 个用例全部通过**（约 0.5s）。

---

## 6. 后端接口依赖（C1 使用 / B2b 已联调）

契约以 `delta_service/PROTOCOL.md` 为准；B2b（JWT 认证 + 房间模型 + WS 认证）已上线，C1 已用客户端真实代码对 `http://114.132.161.169:8000` 完成联调（2026-10-19）。

### 6.1 已按目标契约调用

| 用途 | 方法/路径 | 说明 |
|---|---|---|
| 登录签发 JWT | `POST /api/v1/auth/login` | 读 `data.access_token`（兼容 `token` / `accessToken`）；`user` 取 `data.user` |
| 注册 | `POST /api/v1/auth/register` | B2b 已上线，响应同登录（含 token，客户端注册后自动登录）；404 时回退旧 `/api/users/create` |
| 公共房间列表 | `GET /api/v1/rooms` | 读 `data.items + has_more + next_before`；字段 `id/code/name/member_count/has_password/owner_id/created_at/background_id` |
| 创建房间 | `POST /api/v1/rooms` | `{name, visibility:"public"|"private", password?}`；响应 `data.room` |
| 加入房间 | `POST /api/v1/rooms/{code}/join` | body `{password?}`；B2b 实测路径参数接受 5 位 room_code（同时支持内部 id），客户端输入自动转大写 |
| 离开房间 | WS `leave_room` + `POST /api/v1/rooms/{code}/leave` | B2b 实测 `user_left` 只在 WS leave_room 时广播，客户端离开房间/退出登录/关窗会先发 WS leave_room；HTTP leave 用于清理成员（房主需先关闭房间） |
| 实时连接 | `WS /ws` | 首消息 `{"type":"auth","token","protocol_version":1,"client":{...}}` |
| 加入实时频道 | WS `join_room` | `{room_code,password?}`；**B2b 要求先 HTTP 加入房间**，否则 `NOT_ROOM_MEMBER`；服务端回 `room_joined`（含 `room`、`members`） |
| 聊天（C 阶段） | WS `chat_send` | B2b 返回 `UNSUPPORTED_MESSAGE_TYPE`，C 上线后测收发；客户端已实现 `client_msg_id` 去重 |
| 心跳 | WS `ping` / 服务端 `heartbeat` | 客户端 20s ping，45s 无消息判定失联 |

### 6.2 当前兼容分支（保留以兼容旧后端）

- `POST /api/v1/auth/login` 返回 404 时回退 `POST /api/users/login`（A 现状，无 token → 提示“已登录但无 JWT，聊天仅本地回显”）；
- `POST /api/v1/auth/register` 返回 404 时回退 `POST /api/users/create`；
- `GET /api/v1/rooms` 返回 404 时回退 `GET /api/room/public/list`；
- 错误体同时兼容 `{code,message,data}`、`{detail:{error_code,message}}`、`{detail:"..."}`、Pydantic 422 列表；B2b 的 `data.error_code` 也一并读取。

### 6.3 B2b 真实联调结论（客户端实测）

- 登录：返回 `access_token`；JWT `sub`=user_id、有效期 7 天；`GET /api/v1/users/me` 正常。
- 401 形态：`{"code":40100,"message":"未认证","data":null}`、`{"code":40102,"message":"登录凭证无效"}`；客户端按 401 清会话回登录页。
- 房间：列表分页字段齐全；创建公开/私有正确（`has_password`）；join 接受小写/大写 room_code；私有密码错误返回 HTTP 400 + `data.error_code = ROOM_PASSWORD_REQUIRED / ROOM_PASSWORD_INVALID`，客户端能准确识别并弹密码框。
- WS：`auth` → `auth_ok`（`user`、`heartbeat_interval_ms=30000`）；双账号 `room_joined` 成员互见、`user_joined` 正常；`room_joined` 暂未带 `canvas_snapshot`（D 阶段）。
- 断线重连：同账号新连接顶号后，客户端自动重连 → 重新 auth → 重新 `join_room` 成功。
- 离开：WS `leave_room`（room_id 填 code 或内部 id 均可）会广播 `user_left`；**直接断开 WS 或仅 HTTP leave 不会广播**。客户端已改为离开前先发 WS `leave_room`。
- WS 未认证错误码实测为 `NOT_AUTHENTICATED`（PROTOCOL §7.2 写 `AUTH_REQUIRED`）；`chat_send` 返回 `UNSUPPORTED_MESSAGE_TYPE`。客户端已做错误码别名兼容。
- 房间对象比 PROTOCOL 多 `visibility/updated_at/closed_at/background` 等字段，客户端忽略未知字段。

### 6.4 仍建议后端补齐 / 后续里程碑

1. `user_left` 的触发语义：WS 断连是否应广播离开，建议写进 PROTOCOL（当前实现只在显式 `leave_room` 时广播）。
2. WS 未认证错误码建议与 PROTOCOL 统一（`AUTH_REQUIRED` ↔ `NOT_AUTHENTICATED` 二选一）。
3. `chat_send/chat_message`（C）、`canvas_*`（D）、`skill_*`（E）按里程碑继续。
4. 列表分页 UI：C1 只渲染首屏 `items`，C2 视需要加分页/滚动加载。

---

## 7. 安全约定

- 服务器地址可配置，仓库内**无硬编码 IP**；
- 密码只在登录请求体内发送，**不落盘、不写日志、不进配置文件**；
- JWT 默认只存内存；开启 `save_token` 时才落盘到 `~/.delta_client_session.json`，并用 `core.validation.sanitize_user` 清洗用户信息（去掉 password/token/secret 类字段）；
- 错误提示只展示服务端 `message` 或客户端兜底文案，5xx 不展示内部细节；
- 截屏/OCR/画板（C2/C3）本轮未实现，客户端不采集、不上传屏幕内容。

---

## 8. 已知限制 / TODO

- C1 不实现画板（C2）与截屏/技能识别（C3），房间内画板卡片仅为占位；
- 房间列表暂无分页/自动定时刷新（提供手动刷新）；C1 只渲染 `items` 首屏；
- 成员列表依赖 WS `room_joined`；B2b 期间可用 `GET /api/v1/rooms/{code}` 做 HTTP 成员兜底，计划随 C2 一起做；
- 断线重连后会自动重新 `join_room` 并依赖 `room_joined` 快照恢复状态（画板/技能快照本轮不消费）；
- 离开房间/退出登录/关闭窗口会先发 WS `leave_room`，确保队友收到 `user_left`；
- Mock 后端只用于演示，不模拟限频、多客户端并发与持久化；
- 若后端返回的登录响应没有 token，界面会提示并进入“无 JWT 兼容模式”（聊天本地回显）。

---

## 9. 开发约定

- 纯逻辑（config/core/state）不得 import PySide6/aiohttp/websockets，保证离线单测；
- aiohttp / websockets 采用函数内延迟导入，缺失依赖时给出明确安装提示；
- 新增 UI 页面时沿用 `ui/` + 信号/槽，网络请求统一经 `AsyncBridge` 提交，不在 UI 线程直接 `asyncio.run`。
