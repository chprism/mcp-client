# MCP 客户端详解

## 1. 项目概述

这是一个基于 Model Context Protocol (MCP) 的客户端实现，用于连接和调用 MCP 服务器提供的工具。
该客户端集成了 Anthropic 的 Claude AI 模型，能够处理用户查询，并在需要时调用 MCP 服务器提供的工具来增强 AI 的能力。

### 运行示例
```bash
uv run mcp-client.py D:\02_pythonWorkspace\yahoo-finance\yahoo-finance.py

python mcp-client.py   ../yahoo-finance/yahoo-finance.py


python mcp-client.py  D:/02_pythonWorkspace/tinyurl-mcp-server/tinyurl_mcp_server/server.py -e TINYURL_API_KEY=RFgCTh6ya6LbgO7OmUV4oEtKuZqsELnQ9sdNZE6zRZoqxMyK7C4z9VpZhrar
```

## 2. 底层实现原理

### 2.1 MCP 协议概述

MCP (Model Context Protocol) 是一种标准协议，用于连接 AI 模型与外部工具和数据源。它允许 AI 模型通过标准化的接口访问外部功能，从而扩展 AI 的能力范围。MCP 的核心思想是：

1. **标准化通信**：定义了 AI 模型与外部工具之间的通信格式和协议
2. **工具发现**：允许 AI 动态发现可用的工具及其功能
3. **工具调用**：提供了一种机制，使 AI 能够调用这些工具并获取结果

### 2.2 客户端-服务器架构

该实现采用了客户端-服务器架构：

- **MCP 服务器**：提供特定领域的工具和功能（如 Yahoo Finance 数据获取）
- **MCP 客户端**：连接到服务器，发现可用工具，并在 AI 模型的指导下调用这些工具

### 2.3 通信机制

客户端与服务器之间的通信使用标准输入/输出 (stdio) 进行，这是一种简单但有效的进程间通信方式：

1. 客户端启动服务器脚本作为子进程
2. 通过标准输入向服务器发送请求
3. 从标准输出接收服务器的响应

## 3. 代码结构与逻辑实现

### 3.1 核心类：MCPClient

`MCPClient` 类是整个客户端的核心，负责：

1. 初始化与服务器的连接
2. 处理用户查询
3. 调用 Claude AI 模型
4. 执行工具调用
5. 管理交互式聊天循环

### 3.2 主要方法详解

#### 3.2.1 `__init__` 方法

```python
def __init__(self):
    # 初始化会话和客户端对象
    self.session: Optional[ClientSession] = None
    self.exit_stack = AsyncExitStack()
    self.anthropic = Anthropic()
    self.model = os.getenv("ANTHROPIC_MODEL")
```

- 初始化 MCP 会话对象（初始为 None）
- 创建异步资源管理器 `AsyncExitStack`
- 初始化 Anthropic 客户端
- 从环境变量获取 Claude 模型名称

#### 3.2.2 `connect_to_server` 方法

```python
async def connect_to_server(self, server_script_path: str):
    # 判断服务器脚本类型（Python 或 JavaScript）
    is_python = server_script_path.endswith('.py')
    is_js = server_script_path.endswith('.js')
    
    # 设置启动命令和参数
    command = "python" if is_python else "node"
    server_params = StdioServerParameters(
        command=command,
        args=[server_script_path],
        env=None
    )
    
    # 建立 stdio 连接
    stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
    self.stdio, self.write = stdio_transport
    
    # 初始化会话
    self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
    await self.session.initialize()
    
    # 列出可用工具
    response = await self.session.list_tools()
    tools = response.tools
    print("\nConnected to server with tools:", [tool.name for tool in tools])
```

这个方法负责：
- 根据文件扩展名确定服务器脚本的类型（Python 或 JavaScript）
- 配置服务器启动参数
- 建立基于标准输入/输出的通信通道
- 初始化 MCP 会话
- 获取并显示服务器提供的可用工具列表

#### 3.2.3 `process_query` 方法

这是客户端的核心方法，处理用户查询并在需要时调用工具：

1. 构建初始消息
2. 获取可用工具列表
3. 调用 Claude AI 模型处理查询
4. 解析响应，处理工具调用
5. 将工具调用结果反馈给 AI 模型
6. 整合最终响应

#### 3.2.4 `chat_loop` 方法

提供交互式聊天界面，循环处理用户输入，直到用户输入 'quit'。

#### 3.2.5 `cleanup` 方法

负责清理资源，关闭连接。

### 3.3 主函数流程

1. 解析命令行参数（服务器脚本路径）
2. 创建 MCPClient 实例
3. 连接到指定的 MCP 服务器
4. 启动交互式聊天循环
5. 在结束时清理资源

## 4. 关键参数说明

### 4.1 环境变量

- `ANTHROPIC_MODEL`：指定使用的 Claude 模型版本
- `ANTHROPIC_API_KEY`：Anthropic API 密钥（通过 .env 文件加载）

### 4.2 服务器参数 (StdioServerParameters)

- `command`：启动服务器的命令（python 或 node）
- `args`：命令行参数，包含服务器脚本路径
- `env`：环境变量（此处为 None，使用当前环境）

### 4.3 Claude API 参数

- `model`：使用的 Claude 模型
- `max_tokens`：生成的最大 token 数（设为 1000）
- `messages`：对话历史
- `tools`：可用工具列表

## 5. 工作流程图

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  用户输入   │────>│  Claude AI   │────>│  解析响应     │
└─────────────┘     └──────────────┘     └───────┬───────┘
                           ↑                     │
                           │                     ↓
                    ┌──────┴───────┐     ┌───────────────┐
                    │ 返回工具结果 │<────│  工具调用     │
                    └──────────────┘     └───────┬───────┘
                                                 │
                                                 ↓
                                         ┌───────────────┐
                                         │  MCP 服务器   │
                                         └───────────────┘
```

## 6. 技术依赖

- **Python**: >= 3.12
- **mcp**: >= 1.9.2（MCP 客户端库）
- **anthropic**: >= 0.52.2（Claude AI API 客户端）
- **asyncio**：用于异步操作
- **dotenv**：用于加载环境变量

## 7. 扩展与定制

该客户端可以连接到任何兼容 MCP 协议的服务器，只需提供相应的服务器脚本路径。可以通过以下方式扩展功能：

1. **自定义 MCP 服务器**：开发新的 MCP 服务器，提供特定领域的工具
2. **增强查询处理**：修改 `process_query` 方法，实现更复杂的对话管理
3. **添加用户界面**：替换简单的命令行界面，实现图形化界面

## 8. 注意事项

- 确保已设置正确的环境变量（ANTHROPIC_API_KEY 和 ANTHROPIC_MODEL）
- 服务器脚本必须是有效的 Python (.py) 或 JavaScript (.js) 文件
- 服务器脚本必须实现 MCP 协议
