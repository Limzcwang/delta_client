"""Delta Client 核心纯逻辑。

本包只依赖 Python 标准库，不导入 PySide6 / aiohttp / websockets，
因此可以在无 GUI、无网络的环境下用 ``python -m unittest`` 直接测试。
"""
