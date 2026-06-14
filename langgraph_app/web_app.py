# langgraph_app/web_app.py

# ===== 最先设置项目路径，确保所有模块都使用当前项目 =====
import sys
import os
# 统一设置项目根目录，适配服务器实际路径
PROJECT_ROOT = "/mnt/data4/WHH/MyEmoHH"
if PROJECT_ROOT not in sys.path:
  sys.path.insert(0, PROJECT_ROOT)
print(f"✅ 项目根目录已设置: {PROJECT_ROOT}")
# ==========================================================

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from langgraph_app.graphs.conversation_graph import run_conversation
from langgraph_app.state import state_to_dict

app = FastAPI(title="情绪小站 · 温柔陪伴")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    html = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>情绪小站 · 温柔陪伴</title>
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      height: 100%;
      width: 100%;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
      background: linear-gradient(135deg, #F7F4FF, #E8F3FF);
      color: #333;
    }
    .container {
      height: 100%;
      width: 100%;
      display: flex;
      align-items: stretch;
      justify-content: center;
      padding: 16px;
    }
    .chat-wrapper {
      width: 100%;
      max-width: 1100px;
      background: #FFFFFF;
      border-radius: 24px;
      box-shadow: 0 18px 45px rgba(0, 0, 0, 0.08);
      display: flex;
      flex-direction: column;
      padding: 20px 24px 18px 24px;
    }
    .header {
      margin-bottom: 10px;
    }
    .title {
      font-size: 22px;
      font-weight: 600;
      color: #4B3FA6;
      margin-bottom: 4px;
    }
    .subtitle {
      font-size: 13px;
      color: #777;
    }
    .role-bar {
      margin-top: 10px;
      padding: 8px 12px;
      border-radius: 12px;
      background: #F7F4FF;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .role-name {
      font-size: 13px;
      font-weight: 500;
      color: #4B3FA6;
    }
    .role-desc {
      font-size: 12px;
      color: #666;
    }
    /* 模型选择器样式 */
    .model-selector {
      margin-top: 10px;
      padding: 10px 12px;
      border-radius: 12px;
      background: #F0F7FF;
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .model-selector label {
      font-size: 13px;
      font-weight: 500;
      color: #2563EB;
    }
    .model-selector select {
      padding: 6px 12px;
      border-radius: 8px;
      border: 1px solid #93C5FD;
      background: #FFF;
      font-size: 13px;
      color: #1E40AF;
      cursor: pointer;
      outline: none;
    }
    .model-selector select:focus {
      border-color: #3B82F6;
      box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
    }
    .model-info {
      font-size: 11px;
      color: #6B7280;
      margin-left: auto;
    }
    .model-type-tag {
      display: inline-block;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 500;
      margin-left: 4px;
    }
    .model-type-tag.api {
      background: #DBEAFE;
      color: #1D4ED8;
    }
    .model-type-tag.local {
      background: #D1FAE5;
      color: #047857;
    }
    .chat-area {
      flex: 1;
      margin-top: 10px;
      padding: 12px;
      border-radius: 18px;
      background: #FAFBFF;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .msg {
      max-width: 80%;
      padding: 8px 12px;
      border-radius: 16px;
      font-size: 14px;
      line-height: 1.5;
      word-break: break-word;
    }
    .msg.user {
      align-self: flex-end;
      background: #D6EBFF;
      border-bottom-right-radius: 4px;
    }
    .msg.assistant {
      align-self: flex-start;
      background: #EEE7FF;
      border-bottom-left-radius: 4px;
    }
    .input-bar {
      margin-top: 10px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .input-bar textarea {
      flex: 1;
      border-radius: 12px;
      border: 1px solid #DDD;
      padding: 8px 10px;
      resize: none;
      min-height: 42px;
      max-height: 80px;
      font-size: 14px;
      outline: none;
    }
    .input-bar textarea:focus {
      border-color: #7A6AF5;
      box-shadow: 0 0 0 1px rgba(122, 106, 245, 0.2);
    }
    .send-btn {
      border: none;
      border-radius: 999px;
      padding: 10px 18px;
      background: #7A6AF5;
      color: #FFF;
      font-size: 14px;
      cursor: pointer;
      transition: background 0.15s ease;
      white-space: nowrap;
    }
    .send-btn:disabled {
      background: #CCC;
      cursor: not-allowed;
    }
    .send-btn:hover:not(:disabled) {
      background: #6353E6;
    }
    .hint {
      margin-top: 6px;
      font-size: 12px;
      color: #999;
    }
    /* 打字指示器动画 */
    .typing-indicator {
      color: #888;
      font-style: italic;
    }
    .typing-indicator::after {
      content: '';
      animation: dots 1.5s infinite;
    }
    @keyframes dots {
      0%, 20% { content: ''; }
      40% { content: '.'; }
      60% { content: '..'; }
      80%, 100% { content: '...'; }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="chat-wrapper">
      <div class="header">
        <div class="title">情绪小站 · 温柔陪伴</div>
        <div class="subtitle">这里是一个可以放下防备的小空间，你可以慢慢说，不需要着急。</div>
        <div class="role-bar">
          <div id="roleName" class="role-name">
            当前陪伴者MBTI属性：待匹配
          </div>
          <div id="roleDesc" class="role-desc">
            打招呼时我会以普通小助手的身份回应你；当你聊到自己的情绪、压力或烦恼时，我会为你匹配一位更适合的陪伴者。
          </div>
        </div>
        
        <!-- 模型选择器 -->
        <div class="model-selector">
          <label for="modelSelect">🤖 选择模型：</label>
          <select id="modelSelect">
            <optgroup label="📡 API 模型">
              <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
              <option value="gpt-4o">GPT-4o</option>
              <option value="deepseek-r1">DeepSeek-R1</option>
            </optgroup>
            <optgroup label="💻 本地模型">
              <option value="qwen2-1.5b" selected>Qwen2-1.5B (轻量)</option>
              <option value="qwen2-7b">Qwen2-7B (高质量)</option>
              <option value="deepseek-r1-7b">DeepSeek-R1-7B (推理)</option>
            </optgroup>
          </select>
          <span id="modelInfo" class="model-info">
            当前：<span id="modelType" class="model-type-tag local">本地</span> Qwen2-1.5B-Instruct
          </span>
        </div>
      </div>

      <div id="chatArea" class="chat-area">
        <div class="msg assistant">
          嗨～很高兴在这里见到你。<br />
          这里没有标准答案，也没有对错，你可以随时跟我聊聊最近的心情或小事。
        </div>
      </div>

      <div class="input-bar">
        <textarea id="userInput" placeholder="想说点什么？这里是一个可以放心倾诉的小空间。"></textarea>
        <button id="sendBtn" class="send-btn">发送</button>
      </div>
      <div class="hint">
        温馨提示：简单的“你好”“在吗”等打招呼会以普通小助手身份回复；当你开始聊到自己的情绪、压力或困扰时，我会为你匹配一位专属陪伴者，并在上方显示。
      </div>
    </div>
  </div>

  <script>
    const chatArea = document.getElementById("chatArea");
    const userInput = document.getElementById("userInput");
    const sendBtn = document.getElementById("sendBtn");
    const roleNameEl = document.getElementById("roleName");
    const roleDescEl = document.getElementById("roleDesc");
    const modelSelect = document.getElementById("modelSelect");
    const modelType = document.getElementById("modelType");
    const modelInfo = document.getElementById("modelInfo");

    // 模型信息映射
    const modelDescriptions = {
      "gpt-3.5-turbo": { type: "api", name: "GPT-3.5 Turbo" },
      "gpt-4o": { type: "api", name: "GPT-4o" },
      "deepseek-r1": { type: "api", name: "DeepSeek-R1" },
      "qwen2-1.5b": { type: "local", name: "Qwen2-1.5B-Instruct" },
      "qwen2-7b": { type: "local", name: "Qwen2-7B-Instruct" },
      "deepseek-r1-7b": { type: "local", name: "DeepSeek-R1-Distill-7B" }
    };

    // 更新模型信息显示
    function updateModelInfo() {
      if (!modelSelect || !modelInfo) return;
      const selectedModel = modelSelect.value;
      const info = modelDescriptions[selectedModel];
      if (info && modelType) {
        modelType.textContent = info.type === "api" ? "API" : "本地";
        modelType.className = "model-type-tag " + info.type;
        modelInfo.innerHTML = `当前：<span class="model-type-tag ${info.type}">${info.type === "api" ? "API" : "本地"}</span> ${info.name}`;
      }
    }

    // 监听模型选择变化
    if (modelSelect) {
      modelSelect.addEventListener("change", updateModelInfo);
      // 页面加载时初始化模型信息显示
      updateModelInfo();
    }

    // 流式打字效果配置
    const TYPING_SPEED = 30;  // 每个字符的延迟(毫秒)
    let isTyping = false;  // 是否正在打字

    // ===== 多轮对话上下文管理 =====
    let conversationHistory = [];  // 对话历史 [{role: 'user'/'assistant', content: '...'}]
    let savedFusionWeights = null;  // 保存的角色融合权重（首次匹配后保持）
    let savedMbtiFusionVector = null;  // 保存的MBTI融合向量（首次匹配后保持）
    let hasMatchedRole = false;  // 是否已匹配角色

    function appendMessage(text, sender) {
      const msg = document.createElement("div");
      msg.className = "msg " + sender;
      // 将换行符替换为 <br />
      const safeText = (text || "").split(String.fromCharCode(10)).join("<br />");
      msg.innerHTML = safeText;
      chatArea.appendChild(msg);
      chatArea.scrollTop = chatArea.scrollHeight;
      return msg;
    }

    // 创建空消息元素（用于流式输出）
    function createEmptyMessage(sender) {
      const msg = document.createElement("div");
      msg.className = "msg " + sender;
      chatArea.appendChild(msg);
      return msg;
    }

    // 流式打字效果（优化版：长文本自动加速）
    async function typeMessage(element, text, speed = TYPING_SPEED) {
      isTyping = true;
      element.innerHTML = "";
      
      // 如果文本太长，减少延迟或直接显示
      const maxTypingLength = 200;  // 超过200字符加速
      if (text.length > maxTypingLength) {
        speed = Math.max(5, speed / 2);  // 加速一倍
      }
      if (text.length > 500) {
        // 超长文本直接显示
        const safeText = text.split(String.fromCharCode(10)).join("<br />");
        element.innerHTML = safeText;
        chatArea.scrollTop = chatArea.scrollHeight;
        isTyping = false;
        return;
      }
      
      // 处理换行符
      const chars = text.split("");
      let currentText = "";
      
      for (let i = 0; i < chars.length; i++) {
        if (!isTyping) break;  // 允许中断
        
        currentText += chars[i];
        // 将换行符转换为 <br />
        const safeText = currentText.split(String.fromCharCode(10)).join("<br />");
        element.innerHTML = safeText;
        chatArea.scrollTop = chatArea.scrollHeight;
        
        // 根据字符类型调整延迟
        let delay = speed;
        if (chars[i] === "，" || chars[i] === "," || chars[i] === "。" || chars[i] === ".") {
          delay = speed * 2;  // 标点符号停顿
        } else if (chars[i] === String.fromCharCode(10)) {
          delay = speed * 1.5;  // 换行稍微停顿
        }
        
        await new Promise(resolve => setTimeout(resolve, delay));
      }
      
      isTyping = false;
    }
    
    // 点击聊天区域可跳过打字效果
    chatArea.addEventListener("click", function() {
      if (isTyping) {
        isTyping = false;  // 中断打字，直接显示完整内容
      }
    });

    function updateRoleBar(current_role, role_description, is_emotional, is_greeting, fusion_weights, mbti_fusion_vector) {
      if (is_greeting || !current_role) {
        roleNameEl.textContent = "当前陪伴者MBTI属性：待匹配";
        roleDescEl.textContent =
          "打招呼时我会以普通小助手的身份回应你；当你聊到自己的情绪、压力或烦恼时，我会为你匹配一位更适合的陪伴者。";
        return;
      }
      
      // 显示MBTI属性（从融合MBTI向量解析，包含数值）
      let mbtiText = "未知";
      if (mbti_fusion_vector && Array.isArray(mbti_fusion_vector) && mbti_fusion_vector.length >= 4) {
        const [ei, sn, tf, jp] = mbti_fusion_vector;
        // 根据数值判断MBTI类型（>50偏向后者）
        const E_I = ei > 50 ? "E" : "I";
        const S_N = sn > 50 ? "N" : "S";
        const T_F = tf > 50 ? "F" : "T";
        const J_P = jp > 50 ? "P" : "J";
        const mbtiType = `${E_I}${S_N}${T_F}${J_P}`;
        const mbtiValues = `I/E:${ei.toFixed(1)}, S/N:${sn.toFixed(1)}, F/T:${tf.toFixed(1)}, J/P:${jp.toFixed(1)}`;
        mbtiText = `${mbtiType}（${mbtiValues}）`;
      }
      roleNameEl.textContent = "当前陪伴者MBTI属性：" + mbtiText;

      // 构造融合权重展示文本（只取前3个权重最高的角色）
      let fusionText = "";
      if (fusion_weights && typeof fusion_weights === "object") {
        const entries = Object.entries(fusion_weights);
        if (entries.length > 0) {
          entries.sort((a, b) => b[1] - a[1]);
          const top = entries.slice(0, 4)  // 显示全部4个融合角色
            .map(([name, w]) => `${name}(${(w * 100).toFixed(0)}%)`)
            .join("、");
          fusionText = `融合角色：${top}`;
        }
      }

      roleDescEl.textContent =
        (role_description ||
          (is_emotional
            ? "一位会耐心倾听你情绪的陪伴者。"
            : "一位会以轻松、不打扰的方式陪你聊天的伙伴。")) +
        (fusionText ? `（${fusionText}）` : "");
    }

    async function sendMessage() {
      const text = userInput.value.trim();
      if (!text) return;

      appendMessage(text, "user");
      userInput.value = "";
      userInput.focus();
      sendBtn.disabled = true;

      // 将用户消息加入对话历史
      conversationHistory.push({ role: "user", content: text });

      // 创建空的助手消息，显示加载状态
      const assistantMsg = createEmptyMessage("assistant");
      assistantMsg.innerHTML = '<span class="typing-indicator">正在思考中...</span>';

      try {
        // 获取选中的模型，如果选择器不存在则使用默认值
        const selectedModel = modelSelect ? modelSelect.value : "qwen2-1.5b";
        
        // 构建请求体，包含对话历史和融合状态
        const requestBody = {
          text: text,
          model: selectedModel,
          conversation_history: conversationHistory.slice(0, -1),  // 不包含刚添加的当前消息
        };
        // 如果已有融合权重，传递给后端保持一致
        if (savedFusionWeights) {
          requestBody.character_fusion_weights = savedFusionWeights;
        }
        if (savedMbtiFusionVector) {
          requestBody.mbti_fusion_vector = savedMbtiFusionVector;
        }

        const resp = await fetch("/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestBody)
        });
        
        if (!resp.ok) {
          throw new Error(`HTTP error! status: ${resp.status}`);
        }
        
        const data = await resp.json();

        // 更新角色信息（包含MBTI属性）
        // 多轮对话时优先使用保存的融合状态，确保UI一致性
        const displayWeights = hasMatchedRole ? savedFusionWeights : data.character_fusion_weights;
        const displayMbti = hasMatchedRole ? savedMbtiFusionVector : data.mbti_fusion_vector;
        updateRoleBar(
          data.current_role,
          data.role_description,
          data.is_emotional,
          data.is_greeting,
          displayWeights,
          displayMbti
        );

        // 流式打字效果显示回复
        const responseText = data.assistant_response || "（系统暂时没有回复）";
        await typeMessage(assistantMsg, responseText);

        // 将助手回复加入对话历史
        conversationHistory.push({ role: "assistant", content: responseText });

        // 保存融合权重和MBTI向量（仅在首次匹配时保存，后续保持不变）
        if (!hasMatchedRole && data.is_emotional && !data.is_greeting) {
          if (data.character_fusion_weights) {
            savedFusionWeights = data.character_fusion_weights;
          }
          if (data.mbti_fusion_vector) {
            savedMbtiFusionVector = data.mbti_fusion_vector;
          }
          if (savedFusionWeights || savedMbtiFusionVector) {
            hasMatchedRole = true;
            console.log("✅ 首次匹配角色，保存融合状态:", {
              weights: savedFusionWeights,
              mbti: savedMbtiFusionVector
            });
          }
        }
        
      } catch (e) {
        assistantMsg.innerHTML = "";
        await typeMessage(assistantMsg, "抱歉，服务器好像有点累了，请稍后再试一下。");
        console.error(e);
      } finally {
        sendBtn.disabled = false;
      }
    }

    // 绑定发送按钮事件
    if (sendBtn) {
      sendBtn.addEventListener("click", sendMessage);
    }
    
    // 绑定回车键发送
    if (userInput) {
      userInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          sendMessage();
        }
      });
    }
    
    // 调试信息
    console.log("页面加载完成，发送按钮:", sendBtn ? "已找到" : "未找到");
    console.log("模型选择器:", modelSelect ? "已找到" : "未找到");
  </script>
</body>
</html>
    """
    return HTMLResponse(content=html)


@app.post("/chat", response_class=JSONResponse)
async def chat(payload: dict) -> JSONResponse:
    text = payload.get("text", "") or ""
    model = payload.get("model", "qwen2-1.5b") or "qwen2-1.5b"
    conversation_history = payload.get("conversation_history", []) or []
    # 多轮对话MCTS融合保持：从请求中获取融合权重和MBTI向量
    character_fusion_weights = payload.get("character_fusion_weights", None)
    mbti_fusion_vector = payload.get("mbti_fusion_vector", None)
    
    # 验证模型名称
    valid_models = [
        'gpt-3.5-turbo', 'gpt-4o', 'deepseek-r1',  # API
        'qwen2-1.5b', 'qwen2-7b', 'deepseek-r1-7b'  # 本地
    ]
    if model not in valid_models:
        model = 'qwen2-1.5b'
    
    # 计算当前轮次
    current_round = len(conversation_history) // 2 + 1
    fusion_info = f", 保持MCTS融合" if character_fusion_weights else ", 首轮MCTS探索"
    print(f"📨 收到请求 - 模型: {model}, 轮次: 第{current_round}轮{fusion_info}, 文本: {text[:50]}...")
    
    try:
        state = run_conversation(
            text, 
            model=model, 
            conversation_history=conversation_history,
            character_fusion_weights=character_fusion_weights,
            mbti_fusion_vector=mbti_fusion_vector
        )
        data = state_to_dict(state)
        data["model_used"] = model  # 返回使用的模型信息
        return JSONResponse(content=data)
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ 处理请求时出错: {error_msg}")
        traceback.print_exc()
        # 返回友好的错误响应
        return JSONResponse(content={
            "assistant_response": f"处理请求时遇到问题：{error_msg}\n请检查服务器日志获取详细信息。",
            "current_role": None,
            "role_description": None,
            "is_emotional": False,
            "is_greeting": False,
            "error": error_msg
        })


if __name__ == "__main__":
    import uvicorn
    print("🚀 启动情绪小站 Web 服务...")
    print("📍 访问地址: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)