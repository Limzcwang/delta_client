import tkinter as tk
from tkinter import ttk, messagebox
import threading
import asyncio
import sys
import os

# 添加服务模块路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'services'))

from client_service import http_client, websocket_client_8765, interactive_client


class ClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Delta Client - 连接管理器")
        self.root.geometry("400x300")
        
        # 创建主框架
        main_frame = ttk.Frame(root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 标题
        title_label = ttk.Label(main_frame, text="选择连接方式", font=("Arial", 16))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # 连接选项
        self.connection_var = tk.StringVar(value="1")
        
        options = [
            ("HTTP客户端（8000端口）", "1"),
            ("WebSocket客户端（8765端口）", "2"),
            ("WebSocket客户端（8000端口）", "3")
        ]
        
        for i, (text, value) in enumerate(options):
            ttk.Radiobutton(main_frame, text=text, variable=self.connection_var, 
                           value=value).grid(row=i+1, column=0, sticky=tk.W, pady=5)
        
        # 连接按钮
        connect_button = ttk.Button(main_frame, text="连接", command=self.start_connection)
        connect_button.grid(row=4, column=0, pady=20)
        
        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="日志输出")
        log_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        
        self.log_text = tk.Text(log_frame, height=8, width=50)
        self.log_text.grid(row=0, column=0, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        # 配置网格权重
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(5, weight=1)
        
    def log_message(self, message):
        """在日志区域添加消息"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        
    def start_connection(self):
        """启动选定的连接"""
        choice = self.connection_var.get()
        
        # 在新线程中运行异步代码
        thread = threading.Thread(target=self.run_async_client, args=(choice,))
        thread.daemon = True
        thread.start()
        
    def run_async_client(self, choice):
        """在新线程中运行异步客户端"""
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            if choice == "1":
                self.log_message("启动HTTP客户端连接8000端口...")
                loop.run_until_complete(http_client())
            elif choice == "2":
                self.log_message("启动WebSocket客户端连接8765端口...")
                loop.run_until_complete(websocket_client_8765())
            elif choice == "3":
                self.log_message("启动WebSocket客户端连接8000端口...")
                loop.run_until_complete(interactive_client())
            else:
                self.log_message("无效的选择")
        except Exception as e:
            self.log_message(f"连接错误: {e}")
        finally:
            loop.close()
            self.log_message("连接已关闭")


def main():
    """启动GUI应用程序"""
    root = tk.Tk()
    app = ClientApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()