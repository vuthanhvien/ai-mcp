const DEFAULT_BASE_URL =
  window.location.protocol === "http:" || window.location.protocol === "https:"
    ? window.location.origin
    : "http://localhost:8000";
const DEFAULT_SYSTEM_PROMPT =
  "You are a Vietnamese data-entry assistant. Extract structured data, ask concise follow-up questions when required fields are missing, and use tools when useful.";

const $ = (id) => document.getElementById(id);

const els = {
  baseUrl: $("baseUrl"),
  apiKey: $("apiKey"),
  systemPrompt: $("systemPrompt"),
  saveSettings: $("saveSettings"),
  testTools: $("testTools"),
  connectionStatus: $("connectionStatus"),
  toolList: $("toolList"),
  messages: $("messages"),
  chatForm: $("chatForm"),
  messageInput: $("messageInput"),
  sendButton: $("sendButton"),
  clearChat: $("clearChat"),
  chatSubtext: $("chatSubtext"),
  messageTemplate: $("messageTemplate"),
  refreshGuide: $("refreshGuide"),
  streamEndpoint: $("streamEndpoint"),
  mcpEndpoint: $("mcpEndpoint"),
  authHeader: $("authHeader"),
  mcpConfig: $("mcpConfig"),
  fetchExample: $("fetchExample"),
};

let history = [];
let pending = false;

function loadSettings() {
  els.baseUrl.value = localStorage.getItem("mcpChat.baseUrl") || DEFAULT_BASE_URL;
  els.apiKey.value = localStorage.getItem("mcpChat.apiKey") || "";
  els.systemPrompt.value =
    localStorage.getItem("mcpChat.systemPrompt") || DEFAULT_SYSTEM_PROMPT;
}

function saveSettings() {
  localStorage.setItem("mcpChat.baseUrl", normalizeBaseUrl(els.baseUrl.value));
  localStorage.setItem("mcpChat.apiKey", els.apiKey.value.trim());
  localStorage.setItem("mcpChat.systemPrompt", els.systemPrompt.value.trim());
  els.baseUrl.value = normalizeBaseUrl(els.baseUrl.value);
  updateConnectGuide();
  setStatus("Đã lưu cấu hình", "ok");
}

function normalizeBaseUrl(url) {
  return (url || DEFAULT_BASE_URL).trim().replace(/\/+$/, "");
}

function getHeaders() {
  const headers = { "Content-Type": "application/json" };
  const apiKey = els.apiKey.value.trim();
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }
  return headers;
}

function setStatus(text, type = "") {
  els.connectionStatus.textContent = text;
  els.connectionStatus.className = `status ${type}`.trim();
}

function setPending(value) {
  pending = value;
  els.sendButton.disabled = value;
  els.testTools.disabled = value;
  els.chatSubtext.textContent = value ? "Đang xử lý..." : "Sẵn sàng nhận yêu cầu";
}

function appendMessage(role, text, toolCalls = []) {
  const node = els.messageTemplate.content.firstElementChild.cloneNode(true);
  node.classList.add(role);

  const bubble = node.querySelector(".bubble");
  bubble.textContent = text;

  if (toolCalls.length) {
    const trace = document.createElement("div");
    trace.className = "trace";
    trace.innerHTML = toolCalls
      .map(
        (call) =>
          `<div><code>${escapeHtml(call.name)}</code> ${escapeHtml(
            JSON.stringify(call.arguments || {}),
          )} -> ${escapeHtml(String(call.output || ""))}</div>`,
      )
      .join("");
    bubble.appendChild(trace);
  }

  els.messages.appendChild(node);
  els.messages.scrollTop = els.messages.scrollHeight;
  return node;
}

function appendStreamingMessage() {
  const node = appendMessage("assistant", "");
  const bubble = node.querySelector(".bubble");
  const text = document.createElement("span");
  const trace = document.createElement("div");
  trace.className = "trace";
  trace.hidden = true;
  bubble.textContent = "";
  bubble.appendChild(text);
  bubble.appendChild(trace);
  return { node, text, trace };
}

function appendTrace(trace, html) {
  trace.hidden = false;
  const line = document.createElement("div");
  line.innerHTML = html;
  trace.appendChild(line);
  els.messages.scrollTop = els.messages.scrollHeight;
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function testTools() {
  saveSettings();
  setPending(true);
  setStatus("Đang kiểm tra /api/tools...");

  try {
    const res = await fetch(`${normalizeBaseUrl(els.baseUrl.value)}/api/tools`, {
      headers: getHeaders(),
    });

    if (!res.ok) {
      throw new Error(await res.text());
    }

    const data = await res.json();
    const tools = data.tools || [];
    els.toolList.innerHTML = "";

    if (!tools.length) {
      els.toolList.innerHTML = '<span class="muted">Không có tool REST</span>';
    } else {
      for (const tool of tools) {
        const badge = document.createElement("span");
        badge.className = "tool";
        badge.textContent = tool.name;
        els.toolList.appendChild(badge);
      }
    }

    setStatus(`Kết nối tốt. Có ${tools.length} REST tools.`, "ok");
  } catch (error) {
    setStatus(`Lỗi kết nối: ${error.message}`, "error");
  } finally {
    setPending(false);
  }
}

async function sendMessage(text) {
  saveSettings();
  setPending(true);
  appendMessage("user", text);
  history.push({ role: "user", content: text });
  const live = appendStreamingMessage();
  let answer = "";
  const toolCalls = [];

  try {
    const res = await fetch(`${normalizeBaseUrl(els.baseUrl.value)}/api/chat/stream`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({
        messages: history,
        system: els.systemPrompt.value.trim() || DEFAULT_SYSTEM_PROMPT,
      }),
    });

    if (!res.ok) {
      throw new Error(await res.text());
    }

    if (!res.body) {
      throw new Error("Streaming is not supported by this browser.");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);

        if (event.type === "status") {
          els.chatSubtext.textContent =
            event.message === "streaming" ? "Đang trả lời..." : "Đang suy nghĩ...";
        }

        if (event.type === "tool_call") {
          appendTrace(
            live.trace,
            `<code>${escapeHtml(event.name)}</code> ${escapeHtml(
              JSON.stringify(event.arguments || {}),
            )}`,
          );
        }

        if (event.type === "tool_result") {
          toolCalls.push({
            name: event.name,
            arguments: event.arguments || {},
            output: event.output || "",
          });
          appendTrace(
            live.trace,
            `<code>${escapeHtml(event.name)}</code> -> ${escapeHtml(
              String(event.output || ""),
            )}`,
          );
        }

        if (event.type === "delta") {
          answer += event.text || "";
          live.text.textContent = answer;
          els.messages.scrollTop = els.messages.scrollHeight;
        }

        if (event.type === "done") {
          answer = event.answer || answer;
          live.text.textContent = answer || "(Không có phản hồi)";
        }

        if (event.type === "error") {
          throw new Error(event.detail || event.error || "Stream error");
        }
      }
    }

    if (!answer.trim()) {
      live.text.textContent = "(Không có phản hồi)";
    }

    history.push({ role: "assistant", content: answer });
    setStatus(`Đã nhận phản hồi streaming (${toolCalls.length} tool calls)`, "ok");
  } catch (error) {
    if (!answer) {
      live.node.remove();
    }
    appendMessage("system", `Lỗi: ${error.message}`);
    setStatus("Gửi tin nhắn thất bại", "error");
  } finally {
    setPending(false);
    els.messageInput.focus();
  }
}

els.saveSettings.addEventListener("click", saveSettings);
els.testTools.addEventListener("click", testTools);

els.clearChat.addEventListener("click", () => {
  history = [];
  els.messages.innerHTML = "";
  appendMessage("system", "Đã xóa lịch sử chat trên trình duyệt.");
});

els.chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (pending) return;

  const text = els.messageInput.value.trim();
  if (!text) return;

  els.messageInput.value = "";
  sendMessage(text);
});

els.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    els.chatForm.requestSubmit();
  }
});

loadSettings();
appendMessage(
  "system",
  "Nhập API base URL và API key rồi bấm Test tools. Sau đó bạn có thể chat để nhập liệu hoặc gọi tool.",
);
