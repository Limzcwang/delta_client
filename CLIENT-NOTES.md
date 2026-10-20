# CLIENT-NOTES —— 客户端交接/踩坑记录

版本：**0.1.4** · 更新日期：**2026-10-20** · 基线：`feat/login-dropdown`（含事件 HUD + 1.4 UI/稳定性修复）

> 面向后续接手客户端的人。协议以 `delta_service/PROTOCOL.md` 为准；本文件记录架构、线程模型、HUD 识别链路、崩溃修复、构建测试与已知限制。
> 当前 Release：`release/DeltaClient-Setup-0.1.4.exe`、`DeltaClient-0.1.4-portable.zip`。

---

## 1. 架构与模块地图

```
main.py                    # --mock/--server/--check/--version；QApplication 入口
config.py                  # 配置加载/保存；APP_VERSION=0.1.4；默认服务器/快捷键
core/                      # 纯逻辑（尽量无 Qt/网络，单测直接覆盖）
  protocol.py              # API 路径、WS 消息、响应包兼容
  errors.py                # HTTP/WS 错误 -> ApiError + 中文提示
  backoff.py               # WS 重连指数退避
  connection.py            # /health + rooms 连通性自检
  chat.py                  # 聊天时间线/乐观更新/去重/分页
  canvas.py                # 画板 op/快照/撤销重做/限频
  canvas_geometry.py       # 底图比例/0–1 坐标换算
  skills.py                # SkillState/倒计时/缓存/共享状态
  skill_auto.py            # 自动上报变化判定（state/charges/ready_at）
  skill_payload.py         # 上报 payload 清洗/serialize/校验
  operators.py             # 17 干员配置/slot/charge_cd_ms
  operator_match.py        # 头像多尺度模板匹配 + 左下角自动扫描
  hud_profile.py           # HUD ROI（skill_bar/text_row/avatar）/缩放/JSON
  hud_ocr.py               # RapidOCR 适配（惰性导入，含文字行 3x 放大）
  hud_recognition.py       # NN秒/N%/N分M秒/充能数解析
  hud_brightness.py        # 亮度/充能事件去抖、ready_at 估算
  hud_band.py              # 灰带实验代码（默认关闭）
  clock.py                 # 服务器时钟偏移
  operator_config.py       # 配置中心缓存/ETag
  hud_pipeline.py          # 单帧 -> 三槽 -> 诊断/SkillState
  hud_debug.py             # HUD 调试导出（ROI/frame/result.json）
  room_list.py             # 大厅 diff/room_key
  rooms.py                 # 房间号/名称/密码校验
  models.py                # Room/Member/ChatMessage 容错解析
  validation.py            # 登录/注册/昵称校验
net/
  api_client.py            # aiohttp HTTP 客户端（/api/v1）
  ws_client.py             # websockets（auth/心跳/重连/消息分发）
  mock_backend.py          # Mock HTTP + Mock WS
state/
  session.py               # JWT + 用户信息（可选落盘）
  saved_logins.py          # 历史账号/DPAPI 密码（30 天，最多 5）
  paths.py                 # %APPDATA%\DeltaClient 路径
  crash_logging.py         # faulthandler/excepthook/last_step/stall watchdog
capture/
  window.py                # 游戏窗口查找（进程/标题/尺寸兜底）
  sources.py               # WGC/mss 采集工厂
ui/
  main_window.py           # QStackedWidget + 网络/房间/热键/overlay 编排
  login_view.py            # 登录/注册 + 历史账号下拉入口
  login_history.py         # 0.1.4 非模态历史账号 popup（行高 38）
  username_edit.py         # 账号输入过滤（IME/粘贴/光标）
  room_list_view.py        # 大厅（公共/我的房间）
  my_rooms_view.py         # 我的房间列表
  room_view.py             # 房间内页（成员/聊天/画板）
  canvas_view.py           # 画板控件（底图/透明层/工具栏）
  skill_panel.py           # 技能 CD 面板
  auto_share.py            # 自动识别 2s 循环/变化去抖/暂停
  skill_overlay.py         # 悬浮窗 + OverlayController
  global_hotkeys.py        # Win32 RegisterHotKey + 原生消息过滤
  calibration_dialog.py    # HUD 标定
  hud_async.py             # HUD 异步识别 QThreadPool 服务
  dialogs.py               # 创建/加入房间、连接设置、历史账号对话框（保留）
  async_bridge.py          # asyncio 线程 <-> Qt 桥
  theme.py                 # 深色 QSS（含历史账号下拉样式）
assets/
  canvas_map.png           # 1105×1260 底图
  operators.json           # 17 干员（total_cd_ms/max_charges/charge_cd_ms）
  operators/               # 头像模板（17/17）
  operators/skills/        # 技能图标 fixture/实验模板（不参与主链路）
tests/                     # stdlib unittest；fixtures/hud、hud_text、hud_charge
```

---

## 2. 线程 / 事件模型

- **Qt 主线程**：所有 QWidget、定时器、信号槽、overlay 原生调用、全局热键分发后的 UI 操作。
- **AsyncBridge**：单独 asyncio 线程；网络协程在桥内跑，回调经 `bridge.post` 回主线程（Qt 30ms 轮询）。
- **HUD 识别**：`HudRecognitionService` 使用 `QThreadPool`，**单 worker**；OCR 引擎懒加载单例；10s 超时 token 失效，迟到结果丢弃。
- **自动识别循环**：`AutoShareController` 主线程 QTimer 2s 采样；窗口最小化/无交集暂停；图像只在内存。
- **悬浮窗 follow**：主线程 `QTimer` 500ms；仅位置/尺寸/attach 变化时调用 Win32；模态/抓帧期间 `pause`（可嵌套计数），恢复延迟 100ms。
- **全局热键**：`QAbstractNativeEventFilter` 捕获 `WM_HOTKEY`，`GlobalHotkeyManager.triggered` 信号回主线程；只在登录后注册。
- **测试**：GUI 测试统一 `QT_QPA_PLATFORM=offscreen`，必要时 `QT_QPA_FONTDIR=C:\Windows\Fonts`。

---

## 3. HUD 识别链路

```
capture(source) -> 帧(2560×1440 客户区)
  -> HudProfile.scaled()：skill_bar / text_row / avatar_roi
  -> 左槽文字行 OCR（3x 灰度）
  -> 右上角充能数 OCR
  -> p90 亮度（非充能技能）
  -> SkillTransitionTracker：2 帧去抖 + 状态跳变
  -> SlotRecognition(state/remaining_ms/ready_at/charges/max_charges)
  -> to_skill_state() / serialize_skill_state()
  -> WS skill_share_update / skill_share_off
  -> 队友端 ready_at - server_now 本地倒计时
```

### 3.1 优先级

1. 文字 `NN秒` / `N分M秒` / `N%`（含 0 秒→ready）；文字时间会重同步 `ready_at`。
2. 充能数 OCR：
   - 数字减少（2→1、1→0）→ cast 事件；有剩余充能 `ready_at=t0+charge_cd_ms`；0 充能优先文字秒数，否则 `total_cd_ms`；
   - 数字增加 → 该次充能恢复；`charges==max` 需下一帧仍保持满才 ready（M1 修复）。
3. 亮度 p90：高亮→变暗连续 2 帧确认 → cast；`ready_at=t0+total_cd_ms`。
4. 无信号：上次已知值 / `unknown`。

### 3.2 配置与误差

- `charge_cd_ms` 优先取干员配置；缺省 `total_cd_ms / max_charges`（红狼手炮 70s/2=35s，烟雾弹 45s/2=22.5s）。
- 误差 **1–2s**：t0 取截图识别时刻而非释放瞬间，OCR 有 1–2 帧去抖。
- 上报只在 state、charges/max_charges、`ready_at` 重同步（>1s）、首次/进出房间时触发；同 state 的 remaining 自然减少不上报（M3 修复）。

### 3.3 干员识别

- 默认头像 ROI `(40,1284,78,80)`；自动扫描左下角区域，多尺度 0.5–1.8，阈值 0.65；top3 写日志。
- 红狼实测 `honglang=0.823 @ (40,1284,78,80)`，top2 0.56。
- 未命中保留手动选择；识别结果按对局缓存，换局/重进重置。

### 3.4 灰带实验结论（默认关闭）

- 用户提供的充能序列中，灰带方向/比例不稳定，两次抓取都未覆盖完整 35s 周期；
- 改用「事件驱动 + 本地跑 CD」后不再依赖灰带；`hud_band.py` / `use_band` 代码保留仅作实验，默认 `False`，不影响主链路。
- 技能图标模板库也不再是主链路依赖；`assets/operators/skills/*` 仅测试/实验。

---

## 4. 崩溃可观测性与 qwindows 修复

### 4.1 可观测性

- `faulthandler` 写 `%APPDATA%\DeltaClient\logs\crash.log`；
- `sys.excepthook` / `threading.excepthook` / Qt message handler 统一记录版本、线程、`last_step`；
- 主线程 stall watchdog；异常退出后下次启动提示并打开日志目录；
- 正常/崩溃日志 2MB × 3 轮转，token/password 脱敏；
- `set_current_step()` 标记 HUD/标定/overlay 等阶段，便于定位时序。

### 4.2 已修复的 qwindows 原生崩溃

背景：WER 报 `qwindows.dll` 访问违例，发生在打开/关闭标定对话框时；当时 overlay follow 每 500ms 反复 `SetWindowPos/raise_`，同时 `grab_frame_hidden` 对顶层窗口 hide/show 重建 HWND。

修复要点：

1. **模态暂停**：设置/标定/弹窗 `exec()` 前 `overlay_controller.pause()`，finally `resume()`；嵌套 pause 计数，抓帧 pause 不会提前恢复。
2. **follow 只在状态变化操作窗口**：仅窗口 rect/overlay size 变化、首次 attach、force 时调用 `SetWindowPos/raise_`；同几何仅更新内容/移动位置。
3. **hide/show 排除 overlay**：抓帧隐藏候选窗口时 `exclude=[overlay]`；overlay 绝不被 hide/show。
4. **失效保护**：native 调用前检查 `shiboken6.isValid` + `isVisible`；`OverlayController.stop()` 不碰已删除对象。
5. **延迟恢复**：抓帧 finally 后 `QTimer.singleShot(100ms, resume)`，避开 HWND 重建窗口。
6. **attach 日志限频**：`_last_log_reason` 仅在状态变化写日志，不再每秒十几次 `overlay_attach`。

复现自查：登录 → 开悬浮窗 → 设置 → HUD 标定 → 关闭 → 重复 3 次；不应崩溃，`crash.log` 无新记录。

---

## 5. 悬浮窗规则

- **登录后**才注册全局热键、才允许显示；登出/切换账号立即注销热键、`stop()` 控制器、`hide()` overlay。
- 登录页永不显示，即使 `overlay_enabled=true`；`overlay_enabled` 只表示「用户希望开启」，实际显示 = 已登录 + 检测到游戏窗口。
- 未登录热键静默忽略（不提示/不显示/不记错误日志）；已登录无游戏窗口不显示。
- 无窗口/最小化：hide + 状态「等待游戏窗口」；恢复窗口自动 attach。
- topmost / 不抢焦点 / `WS_EX_TOOLWINDOW`；默认 30% 透明 + 鼠标穿透；编辑模式 100% 不透明并接受输入。
- 注册失败（热键被占用）只在设置页显示；登录页设置页热键状态显示「登录后注册/未注册」。
- `closeEvent` 顺序：停 HUD、`hotkeys.stop()`、`overlay_controller.stop()`、停 bridge。

---

## 6. 配置中心（17 干员）

- `GET /api/v1/config/operators` + `If-None-Match`：
  - `304` → 用缓存；
  - `200` → 校验（非空、干员 id/skill 合法）→ 写 `%APPDATA%\DeltaClient\operators.json` → 热更新面板/识别/上报；
  - 空配置/非法/损坏 → **拒绝覆盖**，回退内置 `assets/operators.json`；
  - 网络失败静默。
- 设置页「干员」显示当前版本/来源/更新时间，可手动检查；手动选择 `operator_id` 持久化到配置。
- 头像路径 `assets/operators/<id>.png`；技能槽 `0/1/2 = 大招/战术/投掷物`。

---

## 7. 构建与打包

### 7.1 源码/依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-e3.txt   # HUD 采集/OCR
python main.py --check
python main.py --mock
```

构建 venv：Python 3.11.5（PySide6 6.12 / numpy / opencv / RapidOCR / Windows capture）。离线 pydeps 仅含 GUI 依赖，HUD/OCR 测试会 skip。

### 7.2 一键构建

```powershell
.\scripts\build_win.ps1
```

流程：读 `config.APP_VERSION` → 安装 build/e3 依赖 → 全量单测 → 生成 Windows version resource → PyInstaller one-folder（`--noupx`，无控制台）→ 校验 FileVersion → 便携 ZIP → Inno Setup → `SHA256SUMS.txt`。

产物命名：

- `release/DeltaClient-Setup-0.1.4.exe`
- `release/DeltaClient-0.1.4-portable.zip`
- `release/SHA256SUMS.txt`

### 7.3 测试约定

```powershell
python -m unittest discover -s tests -v
```

- 当前 **489 用例全部通过**；构建 venv 含真实 fixture **494** 用例。
- 无 PySide6/OCR 依赖时自动 skip（约 6 个）；真实 HUD fixture 在 `tests/fixtures/hud*`。
- GUI 测试使用 `QT_QPA_PLATFORM=offscreen`；离屏中文需 `QT_QPA_FONTDIR=C:\Windows\Fonts`。
- 新增纯逻辑优先放 `core/`，避免 GUI 依赖；UI 行为用 QTest/offscreen。

---

## 8. 已知限制 / TODO

- **WGC 在部分机器不可用**：当前默认 mss 回退；WGC 仅可选，需继续实机验证。
- **CD 误差 1–2s**：事件 t0/OCR 去抖导致；后续可结合更密集采样或服务端结算优化。
- **其他干员头像模板待补**：目前 fixture 以红狼/蜂医为主，17 干员头像模板已配置但真实对局样本不足。
- **灰带/技能图标模板**：实验代码默认关闭；有完整充能周期数据后再考虑校准。
- **零停机发布**：当前安装包升级需重启客户端；服务端热更新/灰度发布链路待做。
- **undo/redo 仅本地**：队友不可见，直到下一次画板快照保存。
- **房间列表分页 UI**：仅首屏 items；后续按需加载。
- **自动快照**：画板无定时快照，崩溃/强杀会丢未保存增量。
- **测试覆盖**：复杂真实窗口/游戏交互仍依赖 `.tmp/client-work-smoke/` 冒烟脚本；未接入 CI 的 GUI 自动化。
- **历史窗口字段**：后端未返回 `window_days` 时 UI 不提示，字段上线后自动生效。

---

## 9. 复验命令

```powershell
cd .tmp/client-work
python -m unittest discover -s tests -v
python main.py --check
python main.py --mock
python main.py --server https://deltachat.icu:8443
```

真实联调脚本（不提交）在 `.tmp/client-work-smoke/`：`live_chat.py`、`live_canvas.py`、`smoke_hud.py`、`smoke_saved_logins.py` 等。
