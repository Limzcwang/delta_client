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

当前结果：**107 个用例全部通过**（约 0.5s）。

---

## 6. 后端接口依赖（C1 使用 / 需后端配合）

契约以 `delta_service/PROTOCOL.md` 为准（里程碑 A 契约基线，B 阶段实现）。

### 6.1 已按目标契约调用

| 用途 | 方法/路径 | 说明 |
|---|---|---|
| 登录签发 JWT | `POST /api/v1/auth/login` | 读 `data.access_token`（兼容 `token` / `accessToken`）；`user` 取 `data.user` |
| 注册 | `POST /api/users/create` | PROTOCOL 暂未定义 v1 注册接口，沿用 A 现状；**需后端确认是否提供 `/api/v1/auth/register`** |
| 公共房间列表 | `GET /api/v1/rooms` | 读 `data.items`；字段 `code/name/member_count/has_password/owner_id/created_at/background_id` |
| 创建房间 | `POST /api/v1/rooms` | `{name, visibility:"public"|"private", password?}`；响应 `data.room` |
| 加入房间 | `POST /api/v1/rooms/{code}/join` | body `{password?}`；**请后端确认路径参数同时接受 room_code（客户端只有 code，PROTOCOL §4 允许）** |
| 离开房间 | `POST /api/v1/rooms/{code}/leave` | 尽力而为，失败不阻塞 UI |
| 实时连接 | `WS /ws` | 首消息 `{"type":"auth","token","protocol_version":1,"client":{...}}` |
| 加入实时频道 | WS `join_room` | `{room_code,password?}`；服务端应回 `room_joined`（含 `room`、`members`） |
| 聊天 | WS `chat_send` | `{client_msg_id,content,content_type:"text"}`；服务端 `chat_message` 需回传 `client_msg_id` 供去重 |
| 心跳 | WS `ping` / 服务端 `heartbeat` | 客户端 20s ping，45s 无消息判定失联 |

### 6.2 当前兼容分支（B 阶段上线后删除）

- `POST /api/v1/auth/login` 返回 404 时回退 `POST /api/users/login`（A 现状，无 token → 提示“已登录但无 JWT，聊天仅本地回显”）；
- `GET /api/v1/rooms` 返回 404 时回退 `GET /api/room/public/list`；
- 错误体同时兼容 `{code,message,data}`、`{detail:{error_code,message}}`、`{detail:"..."}`、Pydantic 422 列表。

### 6.3 需要后端确认 / 补齐的接口

1. **v1 注册接口**：`POST /api/v1/auth/register`（否则客户端长期依赖旧 `/api/users/create`）。
2. **join 路径参数语义**：`/api/v1/rooms/{id}/join` 是否接受 5 位 room_code；若只接受内部 `room_id`，需要新增按 code 查询接口或允许 code。
3. **`GET /api/v1/rooms` 分页**：客户端当前一次性读取 `data.items`；若强制分页，需要 `has_more/next_before` 的 UI 分页交互（C1 暂未做）。
4. **WS `join_room` 密码**：HTTP 加入成功后，WS 加入是否还需要重复传密码（客户端目前会带）。
5. **`chat_message` 回显**：服务端需把发送者自己的消息也广播回来并带 `client_msg_id`，否则客户端本地回显与服务器回显会重复（已做去重，但需服务端配合）。
6. **错误码**：私有房间密码错误/缺失在 HTTP 层建议返回 `ROOM_PASSWORD_REQUIRED` / `ROOM_PASSWORD_INVALID`（字符串码或明确文案），客户端会据此弹密码框。

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
- 房间列表暂无分页/自动定时刷新（提供手动刷新）；
- 断线重连后会自动重新 `join_room` 并依赖 `room_joined` 快照恢复状态（画板/技能快照本轮不消费）；
- Mock 后端只用于演示，不模拟限频、多客户端并发与持久化；
- 若后端返回的登录响应没有 token，界面会提示并进入“无 JWT 兼容模式”（聊天本地回显）。

---

## 9. 开发约定

- 纯逻辑（config/core/state）不得 import PySide6/aiohttp/websockets，保证离线单测；
- aiohttp / websockets 采用函数内延迟导入，缺失依赖时给出明确安装提示；
- 新增 UI 页面时沿用 `ui/` + 信号/槽，网络请求统一经 `AsyncBridge` 提交，不在 UI 线程直接 `asyncio.run`。
