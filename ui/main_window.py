import sys
import threading
import asyncio
import aiohttp
import json
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                               QMessageBox, QFrame)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, Property
from PySide6.QtGui import QFont, QPalette, QColor, QMouseEvent


class TipWidget(QWidget):
    """自定义提示组件"""
    
    def __init__(self, parent=None, title="", message=""):
        super().__init__(parent)
        self.title = title
        self.message = message
        self.is_expanded = False
        self.hover_timer = QTimer()
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.start_close_timer)
        
        self.setup_ui()
        self.setup_animations()
        
    def setup_ui(self):
        """设置UI界面"""
        self.setFixedWidth(300)
        self.setMinimumHeight(80)
        self.setMaximumHeight(200)
        
        # 设置样式
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3498db, stop:1 #2980b9);
                border: 1px solid #21618c;
                border-radius: 8px;
            }
        """)
        
        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # 标题栏（包含关闭按钮）
        title_layout = QHBoxLayout()
        
        # 标题
        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("""
            QLabel {
                color: white;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        
        # 关闭按钮
        self.close_button = QPushButton("×")
        self.close_button.setFixedSize(20, 20)
        self.close_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: white;
                border: 1px solid white;
                border-radius: 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.2);
            }
        """)
        self.close_button.clicked.connect(self.close_tip)
        
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.close_button)
        
        # 消息内容
        self.message_label = QLabel()
        self.message_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 12px;
                background: transparent;
            }
        """)
        self.message_label.setWordWrap(True)
        
        # 更多按钮
        self.more_button = QLabel()
        self.more_button.setStyleSheet("""
            QLabel {
                color: #aed6f1;
                font-size: 11px;
                text-decoration: underline;
                background: transparent;
            }
        """)
        self.more_button.setText("<a href='more' style='color: #aed6f1; text-decoration: underline;'>more</a>")
        self.more_button.setOpenExternalLinks(False)
        self.more_button.linkActivated.connect(self.toggle_expand)
        self.more_button.hide()
        
        layout.addLayout(title_layout)
        layout.addWidget(self.message_label)
        layout.addWidget(self.more_button)
        
        # 设置初始消息
        self.set_message(self.message)
        
    def setup_animations(self):
        """设置动画效果"""
        # 渐入动画
        self.fade_in = QPropertyAnimation(self, b"windowOpacity")
        self.fade_in.setDuration(500)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.setEasingCurve(QEasingCurve.OutCubic)
        
        # 渐出动画
        self.fade_out = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out.setDuration(500)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.setEasingCurve(QEasingCurve.InCubic)
        self.fade_out.finished.connect(self.hide)
        
        # 高度动画
        self.height_anim = QPropertyAnimation(self, b"minimumHeight")
        self.height_anim.setDuration(300)
        self.height_anim.setEasingCurve(QEasingCurve.OutCubic)
        
    def set_message(self, message):
        """设置消息内容"""
        self.full_message = message
        
        # 检查是否需要显示more按钮
        self.message_label.setText(message)
        self.message_label.adjustSize()
        
        # 如果文本高度超过限制，则截断并显示more按钮
        if self.message_label.height() > 60:  # 3行文本的高度
            # 计算截断位置
            lines = message.split('\n')
            truncated_message = ''
            current_height = 0
            font_metrics = self.message_label.fontMetrics()
            line_height = font_metrics.height()
            
            for line in lines:
                if current_height + line_height <= 60:
                    truncated_message += line + '\n'
                    current_height += line_height
                else:
                    break
            
            truncated_message = truncated_message.strip() + "..."
            self.message_label.setText(truncated_message)
            self.more_button.show()
        else:
            self.more_button.hide()
    
    def toggle_expand(self):
        """切换展开/收起状态"""
        self.is_expanded = not self.is_expanded
        
        if self.is_expanded:
            # 展开显示完整内容
            self.message_label.setText(self.full_message)
            self.more_button.setText("<a href='more' style='color: #aed6f1; text-decoration: underline;'>less</a>")
            self.setMinimumHeight(200)
        else:
            # 收起显示截断内容
            self.set_message(self.full_message)
            self.more_button.setText("<a href='more' style='color: #aed6f1; text-decoration: underline;'>more</a>")
            self.setMinimumHeight(80)
    
    def show_tip(self):
        """显示提示"""
        self.show()
        self.fade_in.start()
        self.start_close_timer()
    
    def start_close_timer(self):
        """启动关闭计时器"""
        self.close_timer = QTimer()
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self.close_tip)
        self.close_timer.start(3000)  # 3秒后关闭
    
    def close_tip(self):
        """关闭提示"""
        if hasattr(self, 'close_timer'):
            self.close_timer.stop()
        self.fade_out.start()
    
    def enterEvent(self, event):
        """鼠标进入事件"""
        if hasattr(self, 'close_timer'):
            self.close_timer.stop()
        self.hover_timer.start(100)  # 鼠标离开后100ms重新启动计时器
    
    def leaveEvent(self, event):
        """鼠标离开事件"""
        self.hover_timer.stop()
        self.start_close_timer()


class LoginApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Delta Client - 用户登录")
        self.setFixedSize(400, 300)
        self.tips = []  # 存储当前显示的提示
        self.setup_ui()
        self.center_window()
        
    def setup_ui(self):
        """设置用户界面"""
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(20)
        
        # 标题
        title_label = QLabel("用户登录")
        title_font = QFont("微软雅黑", 18, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 20px;")
        main_layout.addWidget(title_label)
        
        # 用户名输入区域
        username_layout = QHBoxLayout()
        username_label = QLabel("用户名:")
        username_label.setFont(QFont("微软雅黑", 10))
        username_label.setFixedWidth(80)
        
        self.username_entry = QLineEdit()
        self.username_entry.setFont(QFont("微软雅黑", 10))
        self.username_entry.setPlaceholderText("请输入用户名")
        self.username_entry.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                background-color: #ecf0f1;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
            }
        """)
        
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_entry)
        main_layout.addLayout(username_layout)
        
        # 密码输入区域
        password_layout = QHBoxLayout()
        password_label = QLabel("密码:")
        password_label.setFont(QFont("微软雅黑", 10))
        password_label.setFixedWidth(80)
        
        self.password_entry = QLineEdit()
        self.password_entry.setFont(QFont("微软雅黑", 10))
        self.password_entry.setPlaceholderText("请输入密码")
        self.password_entry.setEchoMode(QLineEdit.Password)
        self.password_entry.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                background-color: #ecf0f1;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
            }
        """)
        
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_entry)
        main_layout.addLayout(password_layout)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        
        # 登录按钮
        self.login_button = QPushButton("登录")
        self.login_button.setFont(QFont("微软雅黑", 10, QFont.Bold))
        self.login_button.setFixedHeight(40)
        self.login_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)
        self.login_button.clicked.connect(self.login)
        
        # 注册按钮
        self.register_button = QPushButton("注册")
        self.register_button.setFont(QFont("微软雅黑", 10))
        self.register_button.setFixedHeight(40)
        self.register_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:pressed {
                background-color: #1e8449;
            }
        """)
        self.register_button.clicked.connect(self.register)
        
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.register_button)
        main_layout.addLayout(button_layout)
        
        # 添加弹性空间
        main_layout.addStretch()
        
    def center_window(self):
        """将窗口居中显示"""
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)
        
    def login(self):
        """登录操作"""
        username = self.username_entry.text().strip()
        password = self.password_entry.text().strip()
        
        if not username or not password:
            QMessageBox.warning(self, "输入错误", "请输入用户名和密码")
            return
        
        # 禁用按钮防止重复点击
        self.set_buttons_enabled(False)
        
        # 在新线程中运行登录
        thread = threading.Thread(target=self.run_login, args=(username, password))
        thread.daemon = True
        thread.start()
        
    def register(self):
        """注册操作"""
        username = self.username_entry.text().strip()
        password = self.password_entry.text().strip()
        
        if not username or not password:
            QMessageBox.warning(self, "输入错误", "请输入用户名和密码")
            return
        
        # 禁用按钮防止重复点击
        self.set_buttons_enabled(False)
        
        # 在新线程中运行注册
        thread = threading.Thread(target=self.run_register, args=(username, password))
        thread.daemon = True
        thread.start()
        
    def set_buttons_enabled(self, enabled):
        """设置按钮启用状态"""
        self.login_button.setEnabled(enabled)
        self.register_button.setEnabled(enabled)
        
    def run_login(self, username, password):
        """在新线程中运行登录请求"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 在UI线程中显示消息
            self.show_message_in_ui("登录中", f"正在登录用户: {username}")
            result = loop.run_until_complete(self.http_request("/api/users/login", {
                "username": username,
                "password": password
            }))
            self.show_message_in_ui("登录成功", f"登录结果: {result}")
        except Exception as e:
            self.show_message_in_ui("登录错误", f"登录过程中发生错误: {e}")
        finally:
            loop.close()
            # 重新启用按钮
            self.set_buttons_enabled_in_ui(True)
            
    def run_register(self, username, password):
        """在新线程中运行注册请求"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            self.show_message_in_ui("注册中", f"正在注册用户: {username}")
            result = loop.run_until_complete(self.http_request("/api/users/create", {
                "username": username,
                "password": password
            }))
            self.show_message_in_ui("注册成功", f"注册结果: {result}")
        except Exception as e:
            self.show_message_in_ui("注册错误", f"注册过程中发生错误: {e}")
        finally:
            loop.close()
            self.set_buttons_enabled_in_ui(True)
            
    def show_message_in_ui(self, title, message):
        """在UI线程中显示消息"""
        def show():
            # 创建新的提示窗口
            tip = TipWidget(self, title, message)
            
            # 设置位置（右上角）
            tip_width = tip.width()
            tip_height = tip.height()
            x = self.width() - tip_width - 20  # 距离右边20像素
            y = 20  # 距离顶部20像素
            
            # 调整位置避免重叠
            for existing_tip in self.tips:
                y = max(y, existing_tip.y() + existing_tip.height() + 10)
            
            tip.move(x, y)
            
            # 添加到提示列表
            self.tips.append(tip)
            
            # 显示提示
            tip.show_tip()
            
            # 设置关闭回调
            def on_tip_closed():
                if tip in self.tips:
                    self.tips.remove(tip)
                tip.deleteLater()
            
            tip.fade_out.finished.connect(on_tip_closed)
        
        # 使用QTimer确保在UI线程中执行
        QTimer.singleShot(0, show)
        
    def set_buttons_enabled_in_ui(self, enabled):
        """在UI线程中设置按钮状态"""
        def set_enabled():
            self.set_buttons_enabled(enabled)
        
        QTimer.singleShot(0, set_enabled)
            
    async def http_request(self, endpoint, data):
        """发送HTTP请求到8000端口"""
        url = f"http://114.132.161.169:8000{endpoint}"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                return await response.json()


def main():
    """启动GUI应用程序"""
    app = QApplication(sys.argv)
    
    # 设置应用程序样式
    app.setStyle("Fusion")
    
    window = LoginApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()