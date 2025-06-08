# 导入必要的库
import asyncio  # 用于异步编程
import os  # 用于访问环境变量
from typing import Optional  # 类型提示
from contextlib import AsyncExitStack  # 异步资源管理

# 导入MCP相关库
from mcp import ClientSession, StdioServerParameters  # MCP客户端会话和服务器参数
from mcp.client.stdio import stdio_client  # 基于标准输入输出的客户端

# 导入Anthropic API客户端
from anthropic import Anthropic  # Claude AI API
from dotenv import load_dotenv  # 环境变量加载

# 加载.env文件中的环境变量（如API密钥等）
load_dotenv()

class MCPClient:
    """MCP客户端类
    
    负责连接MCP服务器、处理用户查询、调用AI模型和执行工具调用
    """
    def __init__(self):
        """初始化MCP客户端
        
        设置会话对象、资源管理器和AI模型客户端
        """
        # 初始化MCP会话对象（初始为None）
        self.session: Optional[ClientSession] = None
        # 创建异步资源管理器，用于管理异步上下文资源
        self.exit_stack = AsyncExitStack()
        # 初始化Anthropic API客户端
        self.anthropic = Anthropic()
        # 从环境变量获取Claude模型名称
        self.model = os.getenv("ANTHROPIC_MODEL")

    async def connect_to_server(self, server_script_path: str):
        """连接到MCP服务器
        
        Args:
            server_script_path: 服务器脚本路径（.py或.js文件）
        """
        # 判断服务器脚本类型（Python或JavaScript）
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("服务器脚本必须是.py或.js文件")
            
        # 根据脚本类型选择执行命令
        command = "python" if is_python else "node"
        # 配置服务器启动参数
        server_params = StdioServerParameters(
            command=command,  # 执行命令（python或node）
            args=[server_script_path],  # 命令行参数
            env=None  # 环境变量（使用当前环境）
        )
        
        # 建立基于标准输入/输出的通信通道
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport  # 解包读写通道
        # 初始化MCP会话
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        
        # 初始化会话
        await self.session.initialize()
        
        # 获取并显示服务器提供的可用工具列表
        response = await self.session.list_tools()
        tools = response.tools
        print("\n已连接到服务器，可用工具:", [tool.name for tool in tools])

    async def process_query(self, query: str) -> str:
        """处理用户查询，使用Claude AI和可用工具
        
        Args:
            query: 用户输入的查询文本
            
        Returns:
            str: 处理后的响应文本
        """
        # 构建初始消息列表
        messages = [
            {
                "role": "user",  # 用户角色
                "content": query  # 用户查询内容
            }
        ]

        # 获取可用工具列表
        response = await self.session.list_tools()
        available_tools = [{ 
            "name": tool.name,  # 工具名称
            "description": tool.description,  # 工具描述
            "input_schema": tool.inputSchema  # 工具输入模式
        } for tool in response.tools]

        # 初始调用Claude AI模型
        response = self.anthropic.messages.create(
            model=self.model,  # 使用环境变量中指定的模型
            max_tokens=1000,  # 生成的最大token数
            messages=messages,  # 消息历史
            tools=available_tools  # 可用工具列表
        )

        # 处理响应和工具调用
        tool_results = []  # 存储工具调用结果
        final_text = []  # 存储最终响应文本

        # 遍历响应内容
        for content in response.content:
            if content.type == 'text':  # 如果是文本内容
                final_text.append(content.text)  # 添加到最终响应
            elif content.type == 'tool_use':  # 如果是工具调用
                tool_name = content.name  # 获取工具名称
                tool_args = content.input  # 获取工具参数
                
                # 执行工具调用
                result = await self.session.call_tool(tool_name, tool_args)
                tool_results.append({"call": tool_name, "result": result})  # 记录调用结果
                final_text.append(f"[调用工具 {tool_name}，参数 {tool_args}]")  # 添加调用信息到响应

                # 将工具调用结果继续对话
                # 如果AI响应中包含文本，添加到消息历史
                if hasattr(content, 'text') and content.text:
                    messages.append({
                      "role": "assistant",  # AI助手角色
                      "content": content.text  # AI响应内容
                    })
                # 将工具调用结果作为用户输入添加到消息历史
                messages.append({
                    "role": "user", 
                    "content": result.content  # 工具调用结果
                })

                # 获取Claude对工具调用结果的下一个响应
                response = self.anthropic.messages.create(
                    model=self.model,
                    max_tokens=1000,
                    messages=messages,
                )

                # 添加新响应到最终文本
                final_text.append(response.content[0].text)

        # 合并所有响应文本并返回
        return "\n".join(final_text)

    async def chat_loop(self):
        """运行交互式聊天循环
        
        提供命令行界面，处理用户输入并显示响应
        """
        print("\nMCP 客户端已启动!")
        print("输入您的查询，或输入'quit'退出。")
        
        # 主聊天循环
        while True:
            try:
                # 获取用户输入并去除前后空格
                query = input("\n查询: ").strip()
                
                # 检查是否退出
                if query.lower() == 'quit':
                    break
                
                # 处理查询并获取响应
                response = await self.process_query(query)
                # 显示响应
                print("\n" + response)
                    
            except Exception as e:
                # 错误处理
                print(f"\n错误: {str(e)}")
    
    async def cleanup(self):
        """清理资源
        
        关闭所有打开的连接和资源
        """
        # 关闭异步资源管理器中的所有资源
        await self.exit_stack.aclose()

async def main():
    """主函数
    
    解析命令行参数，创建客户端实例，连接服务器并启动聊天循环
    """
    # 检查命令行参数
    if len(sys.argv) < 2:
        print("用法: python mcp-client.py <服务器脚本路径>")
        sys.exit(1)
        
    # 创建MCP客户端实例
    client = MCPClient()
    try:
        # 连接到指定的MCP服务器
        await client.connect_to_server(sys.argv[1])
        # 启动交互式聊天循环
        await client.chat_loop()
    finally:
        # 确保资源被正确清理
        await client.cleanup()

if __name__ == "__main__":
    # 程序入口点
    import sys  # 导入sys模块用于访问命令行参数
    # 运行异步主函数
    asyncio.run(main())