import asyncio
import websockets
import json
import aiohttp


async def http_client():
    """HTTP客户端连接8000端口"""
    url = "http://114.132.161.169:8000"
    
    async with aiohttp.ClientSession() as session:
        print("HTTP客户端已就绪，输入消息（quit退出）：")
        
        while True:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, input, "HTTP > "
            )
            
            if user_input == "quit":
                break
            
            try:
                async with session.post(url, json={"content": user_input}) as response:
                    result = await response.json()
                    print(f"HTTP服务器响应: {result}")
            except Exception as e:
                print(f"HTTP请求错误: {e}")


async def websocket_client_8765():
    """WebSocket客户端连接8765端口"""
    uri = "ws://114.132.161.169:8765"

    async with websockets.connect(uri) as websocket:
        print("WebSocket 8765端口已连接，输入消息（quit退出）：")

        while True:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, input, "WS8765 > "
            )

            if user_input == "quit":
                break

            await websocket.send(json.dumps({
                "type": "broadcast",
                "content": user_input
            }))

            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                print(f"WebSocket 8765服务器: {json.loads(response)}")
            except asyncio.TimeoutError:
                print("WebSocket 8765: 接收超时")


async def interactive_client():
    """交互式测试客户端"""
    uri = "ws://114.132.161.169:8000"

    async with websockets.connect(uri) as websocket:
        print("WebSocket 8000端口已连接，输入消息（quit退出）：")

        while True:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, input, "WS8000 > "
            )

            if user_input == "quit":
                break

            await websocket.send(json.dumps({
                "type": "broadcast",
                "content": user_input
            }))

            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                print(f"WebSocket 8000服务器: {json.loads(response)}")
            except asyncio.TimeoutError:
                print("WebSocket 8000: 接收超时")


async def main():
    """主函数，同时运行三个客户端"""
    print("选择连接方式：")
    print("1. HTTP客户端（8000端口）")
    print("2. WebSocket客户端（8765端口）")
    print("3. WebSocket客户端（8000端口）")
    
    choice = await asyncio.get_event_loop().run_in_executor(
        None, input, "请输入选择（1/2/3）: "
    )
    
    if choice == "1":
        await http_client()
    elif choice == "2":
        await websocket_client_8765()
    elif choice == "3":
        await interactive_client()
    else:
        print("无效选择")


if __name__ == "__main__":
    asyncio.run(main())