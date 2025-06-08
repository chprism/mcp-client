# MCP 客户端详解

## 1. 项目概述

这是一个基于 Model Context Protocol (MCP) 的客户端实现，用于连接和调用 MCP 服务器提供的工具。
该客户端支持多种 AI 模型：
- Anthropic 的 Claude AI 模型（默认）
- OpenAI 的 GPT 模型

客户端能够处理用户查询，并在需要时调用 MCP 服务器提供的工具来增强 AI 的能力。

### 运行示例
```bash
# 使用默认的 Claude 模型
python mcp-client.py <服务器脚本路径>

# 使用 OpenAI 模型
python mcp-client.py <服务器脚本路径> --model-provider openai

# 设置环境变量示例
python mcp-client.py <服务器脚本路径> -e KEY=VALUE

# 完整示例
python mcp-client.py D:/02_pythonWorkspace/tinyurl-mcp-server/tinyurl_mcp_server/server.py -e TINYURL_API_KEY=your_api_key
```

## 2. 底层实现原理

### 2.1 MCP 协议概述

MCP (Model Context Protocol) 是一种标准协议，用于连接 AI 模型与外部工具和数据源。它允许 AI 模型通过标准化的接口访问外部功能，从而扩展 AI 的能力范围。MCP 的核心思想是：

1. **标准化通信**：定义了 AI 模型与外部工具之间的通信格式和协议
2. **工具发现**：允许 AI 动态发现可用的工具及其功能
3. **工具调用**：提供了一种机制，使 AI 能够调用这些工具并获取结果

### 2.2 客户端-服务器架构

该实现采用了客户端-服务器架构：

- **MCP 服务器**：提供特定领域的工具和功能
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
3. 调用 AI 模型（Claude 或 OpenAI）
4. 执行工具调用
5. 管理交互式聊天循环

### 3.2 主要方法详解

#### 3.2.1 `__init__` 方法

```python
def __init__(self, model_provider: Literal["anthropic", "openai"] = "anthropic"):
    # 初始化会话和客户端对象
    self.session: Optional[ClientSession] = None
    self.exit_stack = AsyncExitStack()
    
    # 根据选择的模型提供商初始化客户端
    self.model_provider = model_provider
    if model_provider == "anthropic":
        self.ai_client = Anthropic()
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")
    else:
        self.ai_client = OpenAI()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
```

#### 3.2.2 `process_query` 方法

根据选择的模型提供商，分别调用不同的处理方法：
- `_process_anthropic_query`: 处理 Claude 模型的查询
- `_process_openai_query`: 处理 OpenAI 模型的查询

## 4. 环境变量配置

### 4.1 必需的环境变量

根据使用的模型，需要设置以下环境变量：

- **使用 Claude 模型时**：
  - `ANTHROPIC_API_KEY`：Anthropic API 密钥
  - `ANTHROPIC_MODEL`：Claude 模型版本（可选，默认为 "claude-3-sonnet-20240229"）

- **使用 OpenAI 模型时**：
  - `OPENAI_API_KEY`：OpenAI API 密钥
  - `OPENAI_MODEL`：GPT 模型版本（可选，默认为 "gpt-4-turbo-preview"）

### 4.2 其他环境变量

- 可以通过命令行参数 `-e` 或 `--env` 设置其他环境变量
- 支持从 `.env` 文件加载环境变量

## 5. 命令行参数

```bash
python mcp-client.py [-h] [--model-provider {anthropic,openai}] [--env ENV] server_script

位置参数:
  server_script          服务器脚本路径

可选参数:
  -h, --help            显示帮助信息
  --model-provider {anthropic,openai}, -m {anthropic,openai}
                        选择模型提供商 (默认: anthropic)
  --env ENV, -e ENV     设置环境变量，格式: KEY=VALUE
```

## 6. 技术依赖

- **Python**: >= 3.12
- **mcp**: >= 1.9.2（MCP 客户端库）
- **anthropic**: >= 0.52.2（Claude AI API 客户端）
- **openai**: >= 1.12.0（OpenAI API 客户端）
- **asyncio**：用于异步操作
- **dotenv**：用于加载环境变量

## 7. 输出格式

客户端使用时间戳和角色标识来格式化输出：

```
[HH:MM:SS User] 用户输入
[HH:MM:SS AI] AI 响应
[HH:MM:SS Tool] 工具调用和结果
```

## 8. 注意事项

- 确保已设置正确的 API 密钥环境变量
- 服务器脚本必须是有效的 Python (.py) 或 JavaScript (.js) 文件
- 服务器脚本必须实现 MCP 协议
- 工具调用结果会被格式化显示，包括参数和返回值
