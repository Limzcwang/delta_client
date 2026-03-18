# Delta Client

一个支持多种连接方式的客户端应用程序，提供图形界面和命令行两种使用方式。

## 项目结构

```
delta_client/
├── services/           # 服务层 - 连接逻辑实现
│   └── client_service.py  # 三种连接方式的实现
├── ui/                 # 用户界面层
│   └── main_window.py     # 图形界面主窗口
├── main.py             # 主程序入口（启动GUI）
├── requirements.txt    # 项目依赖
└── README.md          # 项目说明
```

## 功能特性

- **HTTP客户端**：连接8000端口，支持HTTP POST请求
- **WebSocket客户端**：连接8765端口，实时双向通信
- **WebSocket客户端**：连接8000端口，保留原有功能
- **图形界面**：使用tkinter实现的用户友好界面
- **日志输出**：实时显示连接状态和服务器响应

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 图形界面模式（推荐）
```bash
python main.py
```

### 直接使用服务层（命令行模式）
```bash
cd services
python client_service.py
```

## 连接方式选择

启动程序后，可以选择以下连接方式：

1. **HTTP客户端（8000端口）** - 使用HTTP协议进行通信
2. **WebSocket客户端（8765端口）** - 新增的WebSocket连接
3. **WebSocket客户端（8000端口）** - 原有的WebSocket连接

## 开发说明

- `services/client_service.py` 包含所有连接逻辑，不直接参与执行
- `ui/main_window.py` 是图形界面实现
- `main.py` 是程序主入口，启动GUI应用

## 扩展建议

如需更现代化的界面，可以考虑：
- 安装 `customtkinter` 获得更好的视觉效果
- 使用 `tkinterweb` 添加网页组件支持
- 添加配置文件和设置界面