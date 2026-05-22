const sourceText = document.querySelector("#sourceText");
const resultText = document.querySelector("#resultText");
const optimizeButton = document.querySelector("#optimizeButton");
const copyButton = document.querySelector("#copyButton");
const clearButton = document.querySelector("#clearButton");
const extraButton = document.querySelector("#extraButton");
const statusLine = document.querySelector("#statusLine");
const quotaLine = document.querySelector("#quotaLine");
const charCount = document.querySelector("#charCount");
const downloadLink = document.querySelector("#downloadLink");
const githubLink = document.querySelector("#githubLink");
const extraPanel = document.querySelector("#extraPanel");
const machineLine = document.querySelector("#machineLine");
const complimentGrid = document.querySelector("#complimentGrid");

const TOKEN_KEY = "knowsayin.cloudToken";
const DEVICE_KEY = "knowsayin.deviceCode";
const LONG_TEXT_THRESHOLD = 800;

const state = {
  config: {},
  token: localStorage.getItem(TOKEN_KEY) || "",
  deviceCode: localStorage.getItem(DEVICE_KEY) || "",
  linkedMachineCode: "",
  selectedCompliment: "",
  remaining: null,
  quotaLimit: null,
  maxChars: 3000,
};

function normalizeDeviceCode(value) {
  return Array.from(value || "")
    .filter((char) => /[a-z0-9]/i.test(char))
    .join("")
    .toUpperCase()
    .slice(0, 16);
}

function textLength(value) {
  return Array.from(value || "").length;
}

function setStatus(message, kind = "") {
  statusLine.textContent = message || "";
  statusLine.dataset.kind = kind;
}

function requestJson(path, payload, token = "") {
  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return fetch(path, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  }).then(async (response) => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.message || "请求失败。");
      error.data = data;
      error.status = response.status;
      throw error;
    }
    return data;
  });
}

function readMachineFromUrl() {
  const params = new URL(window.location.href).searchParams;
  return normalizeDeviceCode(params.get("machine") || params.get("device") || params.get("code") || "");
}

function updateCharCount() {
  const current = textLength(sourceText.value);
  charCount.textContent = `${current} / ${state.maxChars}`;
  charCount.dataset.kind = current >= state.maxChars ? "error" : "";
}

function setQuota(remaining, quotaLimit) {
  state.remaining = Number.isFinite(remaining) ? remaining : null;
  state.quotaLimit = Number.isFinite(quotaLimit) ? quotaLimit : null;
  if (state.remaining === null || state.quotaLimit === null) {
    quotaLine.textContent = "额度 -";
  } else {
    quotaLine.textContent = `额度 ${state.remaining}/${state.quotaLimit}`;
  }
  optimizeButton.textContent = quotaEmpty() ? "Get extra" : "Optimize";
}

function quotaEmpty() {
  return state.remaining !== null && state.remaining <= 0 && Boolean(getExtraDeviceCode());
}

function getExtraDeviceCode() {
  return state.linkedMachineCode || state.deviceCode || "";
}

function saveSession(data) {
  state.token = String(data.token || state.token || "").trim();
  state.deviceCode = normalizeDeviceCode(data.deviceCode || state.deviceCode || "");
  if (state.token) {
    localStorage.setItem(TOKEN_KEY, state.token);
  }
  if (state.deviceCode) {
    localStorage.setItem(DEVICE_KEY, state.deviceCode);
  }
}

async function loadConfig() {
  try {
    const response = await fetch("/api/config", { headers: { Accept: "application/json" } });
    const data = await response.json();
    state.config = data || {};
    if (data.downloadUrl) {
      downloadLink.href = data.downloadUrl;
    }
    if (data.githubUrl) {
      githubLink.href = data.githubUrl;
    }
    renderCompliments(data.compliments || []);
  } catch {
    githubLink.href = "https://github.com/aginchan-spec/knowsayin";
    renderCompliments([]);
  }
}

async function ensureSession() {
  if (state.token) {
    return;
  }
  const data = await requestJson("/api/session", {});
  saveSession(data);
  if (Number.isFinite(data.maxChars)) {
    state.maxChars = data.maxChars;
    sourceText.maxLength = state.maxChars;
  }
  setQuota(Number(data.remaining), Number(data.quotaLimit || data.dailyLimit));
}

async function refreshUsage() {
  try {
    await ensureSession();
    const data = await requestJson("/api/usage", {}, state.token);
    saveSession(data);
    if (Number.isFinite(data.maxChars)) {
      state.maxChars = data.maxChars;
      sourceText.maxLength = state.maxChars;
    }
    setQuota(Number(data.remaining), Number(data.quotaLimit || data.dailyLimit));
    updateCharCount();
    updateExtraPanel();
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      localStorage.removeItem(TOKEN_KEY);
      state.token = "";
      await ensureSession();
      return refreshUsage();
    }
    setQuota(null, null);
    updateExtraPanel();
  }
}

function renderCompliments(options) {
  const fallback = [
    { id: "taste", label: "你很有品味" },
    { id: "kind", label: "你很好人" },
    { id: "lucky", label: "好人一生平安" },
    { id: "handsome", label: "这个工具做得有点帅" },
    { id: "tokens", label: "谢谢你帮我省 token" },
    { id: "button", label: "这个按钮值得被点击" },
    { id: "thoughtful", label: "你想得真周到" },
    { id: "prompt", label: "愿你的 prompt 永远清楚" },
    { id: "useful", label: "KnowSayin 有点东西" },
    { id: "coffee", label: "请收下一杯精神咖啡" },
  ];
  const compliments = options.length ? options : fallback;
  complimentGrid.replaceChildren();
  compliments.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "compliment-option";
    button.textContent = option.label;
    button.dataset.id = option.id;
    button.setAttribute("role", "option");
    button.addEventListener("click", () => selectCompliment(option.id));
    complimentGrid.appendChild(button);
  });
}

function selectCompliment(id) {
  state.selectedCompliment = id;
  document.querySelectorAll(".compliment-option").forEach((button) => {
    const selected = button.dataset.id === id;
    button.dataset.selected = selected ? "true" : "";
    button.setAttribute("aria-selected", selected ? "true" : "false");
  });
  setStatus("");
}

function updateExtraPanel(force = false) {
  const deviceCode = getExtraDeviceCode();
  const shouldShow = force || Boolean(state.linkedMachineCode) || quotaEmpty();
  extraPanel.hidden = !shouldShow;
  if (!shouldShow) {
    return;
  }
  machineLine.textContent = deviceCode ? `Machine ${deviceCode}` : "Machine code will load automatically.";
}

async function optimize() {
  if (quotaEmpty()) {
    updateExtraPanel(true);
    extraPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    setStatus("选一句好话，马上补满额度。");
    return;
  }

  const text = sourceText.value.trim();
  if (!text) {
    setStatus("请输入要优化的文字。", "error");
    sourceText.focus();
    return;
  }

  optimizeButton.disabled = true;
  copyButton.disabled = true;
  document.body.dataset.busy = "true";
  setStatus(textLength(text) >= LONG_TEXT_THRESHOLD ? "正在整理长文本..." : "正在优化...");

  try {
    await ensureSession();
    const data = await requestJson(
      "/api/clean",
      {
        text,
        mode: "medium",
      },
      state.token,
    );
    resultText.value = data.result || "";
    copyButton.disabled = !resultText.value;
    if (Number.isFinite(data.maxChars)) {
      state.maxChars = data.maxChars;
      sourceText.maxLength = state.maxChars;
    }
    setQuota(Number(data.remaining), Number(data.quotaLimit || data.dailyLimit));
    updateCharCount();
    updateExtraPanel();
    setStatus("已优化。");
    resultText.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (error.data && error.data.error === "QUOTA_EMPTY") {
      setQuota(0, state.quotaLimit || 20);
      updateExtraPanel(true);
    }
    setStatus(error.message || "优化失败。", "error");
  } finally {
    optimizeButton.disabled = false;
    delete document.body.dataset.busy;
  }
}

async function getExtra() {
  const deviceCode = getExtraDeviceCode();
  if (!deviceCode) {
    setStatus("请从 KnowSayin App 打开这个页面，机器码会自动带过来。", "error");
    return;
  }
  if (!state.selectedCompliment) {
    setStatus("先选一句好话。", "error");
    return;
  }

  extraButton.disabled = true;
  setStatus("正在补额度...");
  try {
    const data = await requestJson("/api/extra", {
      deviceCode,
      compliment: state.selectedCompliment,
    });
    if (normalizeDeviceCode(deviceCode) === state.deviceCode) {
      setQuota(Number(data.remaining), Number(data.quotaLimit || data.dailyLimit));
      await refreshUsage();
    }
    setStatus("额度已补满，回到 KnowSayin 继续用。", "success");
    optimizeButton.textContent = quotaEmpty() ? "Get extra" : "Optimize";
  } catch (error) {
    setStatus(error.message || "补额度失败，请稍后再试。", "error");
  } finally {
    extraButton.disabled = false;
  }
}

async function copyResult() {
  const text = resultText.value.trim();
  if (!text) {
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    setStatus("已复制。", "success");
  } catch {
    resultText.focus();
    resultText.select();
    setStatus("已选中结果，可手动复制。");
  }
}

function clearText() {
  sourceText.value = "";
  resultText.value = "";
  copyButton.disabled = true;
  updateCharCount();
  setStatus("已清除。");
  sourceText.focus();
}

optimizeButton.addEventListener("click", optimize);
copyButton.addEventListener("click", copyResult);
clearButton.addEventListener("click", clearText);
extraButton.addEventListener("click", getExtra);
sourceText.addEventListener("input", () => {
  updateCharCount();
  setStatus("");
});

state.linkedMachineCode = readMachineFromUrl();
if (state.linkedMachineCode) {
  updateExtraPanel(true);
  setStatus("机器码已带过来，选一句好话即可补额度。", "success");
}

updateCharCount();
loadConfig().then(refreshUsage);
