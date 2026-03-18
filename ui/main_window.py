import tkinter as tk
from tkinter import ttk, messagebox
import threading
import asyncio
import aiohttp
import json


class LoginApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Delta Client - 用户登录")
        self.root.geometry("400x300")
        
        # 创建主框架
        main_frame = ttk.Frame(root, padding="30")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 标题
        title_label = ttk.Label(main_frame, text="用户登录/注册", font=("Arial", 16))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 30))
        
        # 用户名输入
        ttk.Label(main_frame, text="用户名:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.username_entry = ttk.Entry(main_frame, width=20)
        self.username_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        # 密码输入
        ttk.Label(main_frame, text="密码:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.password_entry = ttk.Entry(main_frame, width=20, show="*")
        self.password_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=20)
        
        # 登录按钮
        login_button = ttk.Button(button_frame, text="登录", command=self.login)
        login_button.grid(row=0, column=0, padx=(0, 10))
        
        # 注册按钮
        register_button = ttk.Button(button_frame, text="注册", command=self.register)
        register_button.grid(row=0, column=1, padx=(10, 0))
        
        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="操作日志")
        log_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        
        self.log_text = tk.Text(log_frame, height=8, width=50)
        self.log_text.grid(row=0, column=0, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        # 配置网格权重
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(4, weight=1)
        
    def log_message(self, message):
        """在日志区域添加消息"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        
    def login(self):
        """登录操作"""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        
        if not username or not password:
            messagebox.showwarning("输入错误", "请输入用户名和密码")
            return
        
        # 在新线程中运行登录
        thread = threading.Thread(target=self.run_login, args=(username, password))
        thread.daemon = True
        thread.start()
        
    def register(self):
        """注册操作"""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        
        if not username or not password:
            messagebox.showwarning("输入错误", "请输入用户名和密码")
            return
        
        # 在新线程中运行注册
        thread = threading.Thread(target=self.run_register, args=(username, password))
        thread.daemon = True
        thread.start()
        
    def run_login(self, username, password):
        """在新线程中运行登录请求"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            self.log_message(f"正在登录用户: {username}")
            result = loop.run_until_complete(self.http_request("/api/user/login", {
                "username": username,
                "password": password
            }))
            self.log_message(f"登录结果: {result}")
        except Exception as e:
            self.log_message(f"登录错误: {e}")
        finally:
            loop.close()
            
    def run_register(self, username, password):
        """在新线程中运行注册请求"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            self.log_message(f"正在注册用户: {username}")
            result = loop.run_until_complete(self.http_request("/api/user/register", {
                "username": username,
                "password": password
            }))
            self.log_message(f"注册结果: {result}")
        except Exception as e:
            self.log_message(f"注册错误: {e}")
        finally:
            loop.close()
            
    async def http_request(self, endpoint, data):
        """发送HTTP请求到8000端口"""
        url = f"http://114.132.161.169:8000{endpoint}"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                return await response.json()


def main():
    """启动GUI应用程序"""
    root = tk.Tk()
    app = LoginApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()