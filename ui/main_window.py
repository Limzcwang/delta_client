import sys
import threading
import asyncio
import aiohttp
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QMouseEvent


class LoginApp(QMainWindow):
    """Delta Client 登录主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Delta Client - 用户登录")
        self.setFixedSize(800, 500)
        
        # 设置无边框窗口
        self.setWindowFlags(Qt.FramelessWindowHint)
        
        # 鼠标拖动相关变量
        self._drag_pos = None
        
        self.setup_ui()
        self.center_window()
        
    def setup_ui(self):
        """设置用户界面 - 左右分栏布局"""
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主水平布局 - 左右分栏
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ========== 左侧：品牌展示区 ==========
        left_panel = self._create_left_panel()
        
        # ========== 右侧：表单区域 ==========
        right_panel = self._create_right_panel()
        
        # 添加到主布局
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
        
    def _create_left_panel(self):
        """创建左侧品牌面板"""
        left_panel = QWidget()
        left_panel.setFixedWidth(380)
        left_panel.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #667eea, stop:1 #764ba2);
                border-top-left-radius: 8px;
                border-bottom-left-radius: 8px;
            }
        """)
        
        left_layout = QVBoxLayout(left_panel)
        left_layout.setAlignment(Qt.AlignCenter)
        left_layout.setSpacing(30)
        
        # Logo 容器
        logo_container = QWidget()
        logo_container.setFixedSize(140, 140)
        logo_container.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.15);
                border-radius: 70px;
                border: 3px solid rgba(255, 255, 255, 0.4);
            }
        """)
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setAlignment(Qt.AlignCenter)
        
        logo_label = QLabel("◆")
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 64px;
                font-weight: bold;
                background: transparent;
            }
        """)
        logo_layout.addWidget(logo_label)
        
        # 应用名称
        app_name = QLabel("Delta")
        app_name.setAlignment(Qt.AlignCenter)
        app_name.setFont(QFont("微软雅黑", 24, QFont.Bold))
        app_name.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 36px;
                font-weight: bold;
                background: transparent;
                letter-spacing: 3px;
            }
        """)
        
        # 副标题
        app_slogan = QLabel("Secure Connection Client")
        app_slogan.setAlignment(Qt.AlignCenter)
        app_slogan.setFont(QFont("微软雅黑", 10))
        app_slogan.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.7);
                font-size: 14px;
                background: transparent;
                letter-spacing: 1px;
            }
        """)
        
        left_layout.addWidget(logo_container, alignment=Qt.AlignCenter)
        left_layout.addWidget(app_name)
        left_layout.addWidget(app_slogan)
        
        # 支持拖动
        left_panel.mousePressEvent = self._on_drag_start
        left_panel.mouseMoveEvent = self._on_drag_move
        left_panel.mouseReleaseEvent = self._on_drag_end
        
        return left_panel
        
    def _create_right_panel(self):
        """创建右侧表单面板"""
        right_panel = QWidget()
        right_panel.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
            }
        """)
        
        layout = QVBoxLayout(right_panel)
        layout.setContentsMargins(50, 20, 50, 50)
        layout.setSpacing(16)
        
        # 关闭按钮
        layout.addLayout(self._create_close_button_layout())
        
        # 欢迎文字
        welcome_label = QLabel("欢迎回来")
        welcome_label.setFont(QFont("微软雅黑", 22, QFont.Bold))
        welcome_label.setStyleSheet("color: #2c3e50; background: transparent;")
        layout.addWidget(welcome_label)
        
        # 副标题
        sub_label = QLabel("请登录您的账户以继续")
        sub_label.setFont(QFont("微软雅黑", 10))
        sub_label.setStyleSheet("color: #7f8c8d; background: transparent;")
        layout.addWidget(sub_label)
        
        layout.addSpacing(20)
        
        # 用户名输入框
        self.username_entry = self._create_input_field("用户名")
        layout.addWidget(self.username_entry)
        
        # 密码输入框
        self.password_entry = self._create_input_field("密码", is_password=True)
        layout.addWidget(self.password_entry)
        
        # 错误提示区域（现代化设计）
        self.error_container = QWidget()
        self.error_container.hide()
        self.error_layout = QHBoxLayout(self.error_container)
        self.error_layout.setContentsMargins(12, 10, 12, 10)
        self.error_layout.setSpacing(8)
        self.error_container.setStyleSheet("""
            QWidget {
                background-color: #fef2f2;
                border: 1px solid #fecaca;
                border-radius: 8px;
            }
        """)
        
        self.error_icon = QLabel("⚠")
        self.error_icon.setStyleSheet("color: #dc2626; font-size: 14px; background: transparent;")
        self.error_icon.setFixedWidth(18)
        
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #dc2626; font-size: 13px; background: transparent;")
        self.error_label.setFont(QFont("微软雅黑", 10))
        
        self.error_layout.addWidget(self.error_icon)
        self.error_layout.addWidget(self.error_label, stretch=1)
        layout.addWidget(self.error_container)
        
        # 成功提示区域
        self.success_container = QWidget()
        self.success_container.hide()
        success_layout = QHBoxLayout(self.success_container)
        success_layout.setContentsMargins(12, 10, 12, 10)
        success_layout.setSpacing(8)
        self.success_container.setStyleSheet("""
            QWidget {
                background-color: #f0fdf4;
                border: 1px solid #bbf7d0;
                border-radius: 8px;
            }
        """)
        
        self.success_icon = QLabel("✓")
        self.success_icon.setStyleSheet("color: #16a34a; font-size: 14px; font-weight: bold; background: transparent;")
        self.success_icon.setFixedWidth(18)
        
        self.success_label = QLabel()
        self.success_label.setWordWrap(True)
        self.success_label.setStyleSheet("color: #16a34a; font-size: 13px; background: transparent;")
        self.success_label.setFont(QFont("微软雅黑", 10))
        
        success_layout.addWidget(self.success_icon)
        success_layout.addWidget(self.success_label, stretch=1)
        layout.addWidget(self.success_container)
        
        # 按钮区域
        layout.addSpacing(10)
        layout.addWidget(self._create_login_button())
        layout.addWidget(self._create_register_button())
        
        layout.addStretch()
        
        return right_panel
        
    def _create_close_button_layout(self):
        """创建关闭按钮布局"""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        
        close_button = QPushButton("×")
        close_button.setFixedSize(24, 24)
        close_button.setCursor(Qt.PointingHandCursor)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #95a5a6;
                border: 1.5px solid #bdc3c7;
                border-radius: 12px;
                font-size: 14px;
                font-weight: bold;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background-color: #e74c3c;
                color: white;
                border-color: #e74c3c;
            }
            QPushButton:pressed {
                background-color: #c0392b;
                border-color: #c0392b;
            }
        """)
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)
        
        return layout
        
    def _create_input_field(self, placeholder, is_password=False):
        """创建输入框"""
        entry = QLineEdit()
        entry.setFont(QFont("微软雅黑", 11))
        entry.setPlaceholderText(placeholder)
        entry.setFixedHeight(48)
        if is_password:
            entry.setEchoMode(QLineEdit.Password)
        
        # 存储默认样式，用于恢复
        entry.default_style = """
            QLineEdit {
                padding: 0 16px;
                border: 2px solid #e0e6ed;
                border-radius: 10px;
                background-color: #f8fafc;
                color: #2c3e50;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #667eea;
                background-color: #ffffff;
            }
            QLineEdit::placeholder {
                color: #a0aec0;
            }
        """
        entry.error_style = """
            QLineEdit {
                padding: 0 16px;
                border: 2px solid #dc2626;
                border-radius: 10px;
                background-color: #fef2f2;
                color: #2c3e50;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #dc2626;
                background-color: #ffffff;
            }
            QLineEdit::placeholder {
                color: #a0aec0;
            }
        """
        entry.setStyleSheet(entry.default_style)
        
        # 输入时清除错误状态
        entry.textChanged.connect(lambda: self._clear_error_state(entry))
        
        return entry
        
    def _create_login_button(self):
        """创建登录按钮"""
        self.login_button = QPushButton("登 录")
        self.login_button.setFont(QFont("微软雅黑", 12, QFont.Bold))
        self.login_button.setFixedHeight(50)
        self.login_button.setCursor(Qt.PointingHandCursor)
        self.login_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: bold;
                letter-spacing: 2px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #5a6fd6, stop:1 #6a4190);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #4e5fc4, stop:1 #5e3580);
            }
            QPushButton:disabled {
                background: #cbd5e0;
                color: #7f8c8d;
            }
        """)
        self.login_button.clicked.connect(self.login)
        return self.login_button
        
    def _create_register_button(self):
        """创建注册按钮"""
        self.register_button = QPushButton("创 建 账 户")
        self.register_button.setFont(QFont("微软雅黑", 11))
        self.register_button.setFixedHeight(48)
        self.register_button.setCursor(Qt.PointingHandCursor)
        self.register_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #667eea;
                border: 2px solid #667eea;
                border-radius: 10px;
                font-size: 13px;
                font-weight: bold;
                letter-spacing: 2px;
            }
            QPushButton:hover {
                background-color: rgba(102, 126, 234, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(102, 126, 234, 0.2);
            }
            QPushButton:disabled {
                background-color: transparent;
                color: #a0aec0;
                border-color: #cbd5e0;
            }
        """)
        self.register_button.clicked.connect(self.register)
        return self.register_button
        
    def center_window(self):
        """将窗口居中显示"""
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)
        
    # ========== 鼠标拖动窗口功能 ==========
    def _on_drag_start(self, event):
        """开始拖动"""
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            
    def _on_drag_move(self, event):
        """拖动中"""
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            
    def _on_drag_end(self, event):
        """结束拖动"""
        self._drag_pos = None
        event.accept()
        
    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下事件"""
        if event.button() == Qt.LeftButton and event.position().y() <= 60:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)
        
    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动事件"""
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)
        
    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放事件"""
        self._drag_pos = None
        super().mouseReleaseEvent(event)
        
    # ========== 错误处理 ==========
    def _show_error(self, message):
        """显示错误信息（现代化样式）"""
        # 隐藏成功提示
        self.success_container.hide()
        
        # 显示错误提示
        self.error_label.setText(message)
        self.error_container.show()
        
        # 高亮输入框
        self.username_entry.setStyleSheet(self.username_entry.error_style)
        self.password_entry.setStyleSheet(self.password_entry.error_style)
        
        # 重新启用按钮（错误时允许重试）
        self._set_buttons_enabled(True)
        
    def _show_success(self, message):
        """显示成功信息"""
        # 隐藏错误提示
        self.error_container.hide()
        self.username_entry.setStyleSheet(self.username_entry.default_style)
        self.password_entry.setStyleSheet(self.password_entry.default_style)
        
        # 显示成功提示
        self.success_label.setText(message)
        self.success_container.show()
        
    def _clear_error_state(self, entry):
        """清除错误状态"""
        entry.setStyleSheet(entry.default_style)
        # 如果错误提示显示中，也清除它
        if self.error_container.isVisible():
            self.error_container.hide()
            
    def _set_buttons_enabled(self, enabled):
        """设置按钮启用状态"""
        self.login_button.setEnabled(enabled)
        self.register_button.setEnabled(enabled)
        
    # ========== 业务逻辑 ==========
    def login(self):
        """登录操作"""
        username = self.username_entry.text().strip()
        password = self.password_entry.text().strip()
        
        # 禁用按钮
        self._set_buttons_enabled(False)
        
        # 验证输入
        if not username or not password:
            self._show_error("请输入用户名和密码")
            return
            
        # 在新线程中运行登录
        thread = threading.Thread(target=self._run_login, args=(username, password))
        thread.daemon = True
        thread.start()
        
    def register(self):
        """注册操作"""
        username = self.username_entry.text().strip()
        password = self.password_entry.text().strip()
        
        # 禁用按钮
        self._set_buttons_enabled(False)
        
        # 验证输入
        if not username or not password:
            self._show_error("请输入用户名和密码")
            return
            
        # 在新线程中运行注册
        thread = threading.Thread(target=self._run_register, args=(username, password))
        thread.daemon = True
        thread.start()
        
    def _run_login(self, username, password):
        """后台执行登录"""
        def on_success(result):
            self._show_success(f"登录成功！欢迎回来，{username}")
            self._set_buttons_enabled(True)
            
        def on_error(error_msg):
            self._show_error(f"登录失败：{error_msg}")
            
        self._run_async_task("/api/users/login", {"username": username, "password": password}, 
                            on_success, on_error)
        
    def _run_register(self, username, password):
        """后台执行注册"""
        def on_success(result):
            self._show_success(f"注册成功！请使用新账户登录")
            self._set_buttons_enabled(True)
            # 清空密码方便登录
            self.password_entry.clear()
            
        def on_error(error_msg):
            self._show_error(f"注册失败：{error_msg}")
            
        self._run_async_task("/api/users/create", {"username": username, "password": password}, 
                            on_success, on_error)
        
    def _run_async_task(self, endpoint, data, on_success, on_error):
        """运行异步任务并处理回调"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(self._http_request(endpoint, data))
            # 在UI线程中回调
            QTimer.singleShot(0, lambda: on_success(result))
        except Exception as e:
            error_msg = str(e)
            # 简化错误信息
            if "Cannot connect" in error_msg or "Connection refused" in error_msg:
                error_msg = "无法连接到服务器，请检查网络"
            elif "Timeout" in error_msg:
                error_msg = "连接超时，请稍后重试"
            elif "401" in error_msg or "Unauthorized" in error_msg:
                error_msg = "用户名或密码错误"
            elif "409" in error_msg or "Conflict" in error_msg:
                error_msg = "用户名已存在"
            QTimer.singleShot(0, lambda: on_error(error_msg))
        finally:
            loop.close()
            
    async def _http_request(self, endpoint, data):
        """发送HTTP请求"""
        url = f"http://114.132.161.169:8000{endpoint}"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    text = await response.text()
                    raise Exception(f"HTTP {response.status}: {text}")


def main():
    """启动GUI应用程序"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = LoginApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
