#!/usr/bin/env python3
"""
Delta Client - 主程序入口
启动图形界面应用程序
"""

import sys
import os

# 添加ui模块路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'ui'))

def main():
    """主函数"""
    try:
        from main_window import main as gui_main
        print("启动Delta Client图形界面...")
        gui_main()
    except ImportError as e:
        print(f"导入错误: {e}")
        print("请确保所有依赖已安装: pip install -r requirements.txt")
    except Exception as e:
        print(f"程序启动错误: {e}")


if __name__ == "__main__":
    main()