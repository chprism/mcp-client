# 导入必要的库
import asyncio  # 用于异步编程
import os  # 用于访问环境变量
import sys  # 用于命令行参数
import json  # 用于解析JSON字符串
from typing import Optional, Literal  # 类型提示
from contextlib import AsyncExitStack  # 异步资源管理
from datetime import datetime  # 用于时间戳
import argparse

# 导入MCP相关库
from mcp import ClientSession, StdioServerParameters  # MCP客户端会话和服务器参数
from mcp.client.stdio import stdio_client  # 基于标准输入输出的客户端

# 导入AI模型API客户端
from anthropic import Anthropic  # Claude AI API
from openai import OpenAI  # OpenAI API
from dotenv import load_dotenv  # 环境变量加载

# 加载.env文件中的环境变量（如API密钥等）
load_dotenv()

def format_message(role: str, content: str, is_tool: bool = False) -> str:
    """格式化消息输出
    
    Args:
        role: 消息角色
        content: 消息内容
        is_tool: 是否为工具调用
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    if is_tool:
        prefix = f"[{timestamp} Tool]"
    elif role == "assistant":
        prefix = f"[{timestamp} AI]"
    else:
        prefix = f"[{timestamp} User]"
    
    return f"{prefix} {content}\n"

class MCPClient:
    """MCP客户端类
    
    负责连接MCP服务器、处理用户查询、调用AI模型和执行工具调用
    """
    def __init__(self, model_provider: Literal["anthropic", "openai"] = "anthropic"):
        """初始化MCP客户端
        
        Args:
            model_provider: 选择使用的模型提供商，可选 "anthropic" 或 "openai"
        
        设置会话对象、资源管理器和AI模型客户端
        """
        # 初始化MCP会话对象（初始为None）
        self.session: Optional[ClientSession] = None
        # 创建异步资源管理器，用于管理异步上下文资源
        self.exit_stack = AsyncExitStack()
        
        # 设置模型提供商
        self.model_provider = model_provider
        
        if model_provider == "anthropic":
            # 初始化Anthropic API客户端
            self.ai_client = Anthropic()
            # 从环境变量获取Claude模型名称
            self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")
        else:
            # 初始化OpenAI API客户端
            self.ai_client = OpenAI()
            # 从环境变量获取OpenAI模型名称
            self.model = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")

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
        """处理用户查询，使用AI模型和可用工具
        
        Args:
            query: 用户输入的查询文本
            
        Returns:
            str: 处理后的响应文本
        """
        # 获取可用工具列表
        response = await self.session.list_tools()
        
        if self.model_provider == "anthropic":
            available_tools = [{ 
                "name": tool.name,  # 工具名称
                "description": tool.description,  # 工具描述
                "parameters": tool.inputSchema  # 工具输入模式
            } for tool in response.tools]
        else:
            # OpenAI需要特定的工具格式
            available_tools = [{
                "type": "function",  # OpenAI要求的type字段
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                }
            } for tool in response.tools]

        if self.model_provider == "anthropic":
            return await self._process_anthropic_query(query, available_tools)
        else:
            return await self._process_openai_query(query, available_tools)

    async def _process_anthropic_query(self, query: str, available_tools: list) -> str:
        """使用Anthropic模型处理查询"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        response = self.ai_client.messages.create(
            model=self.model,
            max_tokens=1000,
            messages=messages,
            tools=available_tools
        )

        tool_results = []
        final_text = []

        for content in response.content:
            if content.type == 'text':
                final_text.append(content.text)
            elif content.type == 'tool_use':
                tool_name = content.name
                tool_args = content.input
                
                result = await self.session.call_tool(tool_name, tool_args)
                tool_results.append({"call": tool_name, "result": result})
                final_text.append(f"[调用工具 {tool_name}，参数 {tool_args}]")

                if hasattr(content, 'text') and content.text:
                    messages.append({
                        "role": "assistant",
                        "content": content.text
                    })
                messages.append({
                    "role": "user",
                    "content": result.content
                })

                response = self.ai_client.messages.create(
                    model=self.model,
                    max_tokens=1000,
                    messages=messages,
                )

                final_text.append(response.content[0].text)

        return "\n".join(final_text)

    async def _process_openai_query(self, query: str, available_tools: list) -> str:
        """使用OpenAI模型处理查询"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        response = self.ai_client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=available_tools,
            tool_choice="auto"
        )

        tool_results = []
        final_text = []

        message = response.choices[0].message
        if message.content:
            final_text.append(format_message("assistant", message.content))

        while message.tool_calls:
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    error_msg = f"解析工具参数时出错: {e}\n原始参数: {tool_call.function.arguments}"
                    final_text.append(format_message("system", error_msg))
                    continue
                
                # 格式化工具调用信息
                tool_call_msg = f"调用工具: {tool_name}"
                if tool_args:
                    formatted_args = json.dumps(tool_args, ensure_ascii=False, indent=2)
                    tool_call_msg += f"\n参数:\n{formatted_args}"
                final_text.append(format_message("system", tool_call_msg, True))
                
                result = await self.session.call_tool(tool_name, tool_args)
                tool_results.append({"call": tool_name, "result": result})
                
                # 格式化工具返回结果
                result_msg = f"工具返回结果:\n{result.content}"
                final_text.append(format_message("system", result_msg, True))

                messages.append({
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": message.tool_calls
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result.content
                })

            response = self.ai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=available_tools,
                tool_choice="auto"
            )
            
            message = response.choices[0].message
            if message.content:
                final_text.append(format_message("assistant", message.content))

        return "".join(final_text)

    async def chat_loop(self):
        """运行交互式聊天循环
        
        提供命令行界面，处理用户输入并显示响应
        """
        print("\nMCP 客户端已启动!")
        print("输入您的查询，或输入'quit'退出。\n")
        
        # 主聊天循环
        while True:
            try:
                # 获取用户输入并去除前后空格
                query = input("查询: ").strip()
                
                # 检查是否退出
                if query.lower() == 'quit':
                    break
                
                # 处理查询并获取响应
                response = await self.process_query(query)
                # 显示响应
                print(response)
                    
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
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='MCP客户端')
    parser.add_argument('server_script', help='服务器脚本路径')
    parser.add_argument('--model-provider', '-m', 
                      choices=['anthropic', 'openai'],
                      default='anthropic',
                      help='选择模型提供商 (默认: anthropic)')
    parser.add_argument('--env', '-e', 
                      action='append',
                      help='设置环境变量，格式: KEY=VALUE')
    
    args = parser.parse_args()
    
    # 处理环境变量
    if args.env:
        for env_var in args.env:
            key, value = env_var.split('=', 1)
            os.environ[key] = value
    
    # 创建MCP客户端实例
    client = MCPClient(model_provider=args.model_provider)
    try:
        # 连接到指定的MCP服务器
        await client.connect_to_server(args.server_script)
        # 启动交互式聊天循环
        await client.chat_loop()
    finally:
        # 清理资源
        await client.cleanup()

if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())