# EmoFusionRAG
这是一个中文角色融合情感对话项目，结合角色设定、情感分析、BM25 检索和多模型接入，支持命令行与 Web 交互，旨在让对话系统既能按照角色风格回应，又能感知情绪、利用检索提升回答质量。
# EmoFusionRAG 简易说明

一个中文角色融合情感对话项目。项目结合角色匹配、情感分析、BM25 检索和多模型接入，支持 Web 页面和命令行交互。

## 主要入口

- Web 服务：
  ```bash
  python langgraph_app/web_app.py
  ```
  启动后访问：`http://localhost:8000`

- 命令行聊天：
  ```bash
  python langgraph_app/cli.py
  ```


## 依赖

常用依赖：

```bash
pip install fastapi uvicorn numpy jieba
```

如果使用本地模型，还需要安装 `torch`。

## 说明

- 项目主要做角色融合情感对话。 
- 支持 API 模型和本地模型。
- 请先检查 `langgraph_app/web_app.py` 中的模型路径和 API 配置。
