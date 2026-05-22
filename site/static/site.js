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
const LANG = detectLanguage();

const COPY = {
  en: {
    headline: "Refine a rough prompt",
    getExtraEyebrow: "Get extra",
    extraTitle: "Send the author a nice note to refill for free",
    extraSubmit: "Send and refill",
    optimizeButton: "Optimize",
    getExtraButton: "Get extra",
    sourceLabel: "Original",
    sourcePlaceholder: "Paste dictated text, notes, or rough thoughts here",
    resultLabel: "Result",
    resultPlaceholder: "Your refined prompt will appear here",
    copyButton: "Copy result",
    clearButton: "Clear",
    quotaUnknown: "Quota -",
    quotaPrefix: "Quota",
    requestFailed: "Request failed.",
    machine: "Machine",
    machineAuto: "Machine code will load automatically.",
    chooseNiceNote: "Choose a nice note for the author, then refill for free.",
    emptyText: "Enter text to optimize.",
    optimizing: "Optimizing...",
    optimizingLong: "Refining long text...",
    optimized: "Optimized.",
    missingMachine: "Open this page from the KnowSayin app so the machine code is included.",
    pickCompliment: "Pick one nice note for the author.",
    refilling: "Refilling quota...",
    refilled: "Quota refilled. Go back to KnowSayin and keep going.",
    refillFailed: "Could not refill quota. Please try again later.",
    copied: "Copied.",
    selected: "Result selected. Copy it manually.",
    cleared: "Cleared.",
    linkedMachine: "Machine code loaded. Pick a nice note for the author to refill.",
  },
  zh: {
    headline: "整理粗糙 prompt",
    getExtraEyebrow: "补额度",
    extraTitle: "选一句好话送给作者，免费补满额度",
    extraSubmit: "送出并补额度",
    optimizeButton: "优化",
    getExtraButton: "补额度",
    sourceLabel: "原文",
    sourcePlaceholder: "把语音转写、随手记录或粗糙想法粘贴在这里",
    resultLabel: "结果",
    resultPlaceholder: "整理后的 prompt 会出现在这里",
    copyButton: "复制结果",
    clearButton: "清除",
    quotaUnknown: "额度 -",
    quotaPrefix: "额度",
    requestFailed: "请求失败。",
    machine: "机器码",
    machineAuto: "机器码会自动带过来。",
    chooseNiceNote: "选一句好话送给作者，马上免费补满额度。",
    emptyText: "请输入要优化的文字。",
    optimizing: "正在优化...",
    optimizingLong: "正在整理长文本...",
    optimized: "已优化。",
    missingMachine: "请从 KnowSayin App 打开这个页面，机器码会自动带过来。",
    pickCompliment: "先选一句好话送给作者。",
    refilling: "正在补额度...",
    refilled: "额度已补满，回到 KnowSayin 继续用。",
    refillFailed: "补额度失败，请稍后再试。",
    copied: "已复制。",
    selected: "已选中结果，可手动复制。",
    cleared: "已清除。",
    linkedMachine: "机器码已带过来，选一句好话送给作者即可补额度。",
  },
};

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

function detectLanguage() {
  const forcedLanguage = new URL(window.location.href).searchParams.get("lang") || "";
  if (forcedLanguage.toLowerCase().startsWith("zh")) {
    return "zh";
  }
  if (forcedLanguage.toLowerCase().startsWith("en")) {
    return "en";
  }
  const languages = navigator.languages || [navigator.language || "en"];
  return languages.some((value) => String(value).toLowerCase().startsWith("zh")) ? "zh" : "en";
}

function text(key) {
  return COPY[LANG][key] || COPY.en[key] || key;
}

function applyLocale() {
  document.documentElement.lang = LANG === "zh" ? "zh-CN" : "en";
  document.title = text("headline");
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = text(node.dataset.i18n);
  });
  sourceText.placeholder = text("sourcePlaceholder");
  resultText.placeholder = text("resultPlaceholder");
  optimizeButton.textContent = actionButtonLabel();
  setQuota(state.remaining, state.quotaLimit);
}

function actionButtonLabel() {
  return quotaEmpty() ? text("getExtraButton") : text("optimizeButton");
}

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
      const error = new Error(data.message || text("requestFailed"));
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
    quotaLine.textContent = text("quotaUnknown");
  } else {
    quotaLine.textContent = `${text("quotaPrefix")} ${state.remaining}/${state.quotaLimit}`;
  }
  optimizeButton.textContent = actionButtonLabel();
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
    {
      id: "taste",
      labels: {
        zh: "送给作者：你很有品味",
        en: "For the author: you have excellent taste.",
      },
    },
    {
      id: "kind",
      labels: {
        zh: "送给作者：你真的很用心",
        en: "For the author: you put real care into this.",
      },
    },
    {
      id: "lucky",
      labels: {
        zh: "送给作者：愿你好人一生平安",
        en: "For the author: may good things find you.",
      },
    },
    {
      id: "handsome",
      labels: {
        zh: "送给作者：这个工具做得有点帅",
        en: "For the author: this tool is quietly handsome.",
      },
    },
    {
      id: "tokens",
      labels: {
        zh: "送给作者：谢谢你帮我省 token",
        en: "For the author: thanks for saving my tokens.",
      },
    },
    {
      id: "button",
      labels: {
        zh: "送给作者：这个按钮值得被点击",
        en: "For the author: this button deserves the click.",
      },
    },
    {
      id: "thoughtful",
      labels: {
        zh: "送给作者：你想得真周到",
        en: "For the author: this is thoughtfully made.",
      },
    },
    {
      id: "prompt",
      labels: {
        zh: "送给作者：愿你的 prompt 永远清楚",
        en: "For the author: may your prompts stay clear.",
      },
    },
    {
      id: "useful",
      labels: {
        zh: "送给作者：KnowSayin 真的有用",
        en: "For the author: KnowSayin is genuinely useful.",
      },
    },
    {
      id: "coffee",
      labels: {
        zh: "送给作者：请收下一杯精神咖啡",
        en: "For the author: please accept a virtual coffee.",
      },
    },
  ];
  const compliments = options.length ? options : fallback;
  complimentGrid.replaceChildren();
  compliments.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "compliment-option";
    button.textContent = complimentLabel(option);
    button.dataset.id = option.id;
    button.setAttribute("role", "option");
    button.addEventListener("click", () => selectCompliment(option.id));
    complimentGrid.appendChild(button);
  });
}

function complimentLabel(option) {
  if (option && option.labels) {
    return option.labels[LANG] || option.labels.en || option.labels.zh || "";
  }
  if (option && typeof option.label === "string") {
    return option.label;
  }
  return "";
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
  machineLine.textContent = deviceCode ? `${text("machine")} ${deviceCode}` : text("machineAuto");
}

async function optimize() {
  if (quotaEmpty()) {
    updateExtraPanel(true);
    extraPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    setStatus(text("chooseNiceNote"));
    return;
  }

  const sourceValue = sourceText.value.trim();
  if (!sourceValue) {
    setStatus(text("emptyText"), "error");
    sourceText.focus();
    return;
  }

  optimizeButton.disabled = true;
  copyButton.disabled = true;
  document.body.dataset.busy = "true";
  setStatus(textLength(sourceValue) >= LONG_TEXT_THRESHOLD ? text("optimizingLong") : text("optimizing"));

  try {
    await ensureSession();
    const data = await requestJson(
      "/api/clean",
      {
        text: sourceValue,
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
    setStatus(text("optimized"));
    resultText.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (error.data && error.data.error === "QUOTA_EMPTY") {
      setQuota(0, state.quotaLimit || 20);
      updateExtraPanel(true);
    }
    setStatus(error.message || text("requestFailed"), "error");
  } finally {
    optimizeButton.disabled = false;
    delete document.body.dataset.busy;
  }
}

async function getExtra() {
  const deviceCode = getExtraDeviceCode();
  if (!deviceCode) {
    setStatus(text("missingMachine"), "error");
    return;
  }
  if (!state.selectedCompliment) {
    setStatus(text("pickCompliment"), "error");
    return;
  }

  extraButton.disabled = true;
  setStatus(text("refilling"));
  try {
    const data = await requestJson("/api/extra", {
      deviceCode,
      compliment: state.selectedCompliment,
    });
    if (normalizeDeviceCode(deviceCode) === state.deviceCode) {
      setQuota(Number(data.remaining), Number(data.quotaLimit || data.dailyLimit));
      await refreshUsage();
    }
    setStatus(text("refilled"), "success");
    optimizeButton.textContent = actionButtonLabel();
  } catch (error) {
    setStatus(error.message || text("refillFailed"), "error");
  } finally {
    extraButton.disabled = false;
  }
}

async function copyResult() {
  const resultValue = resultText.value.trim();
  if (!resultValue) {
    return;
  }
  try {
    await navigator.clipboard.writeText(resultValue);
    setStatus(text("copied"), "success");
  } catch {
    resultText.focus();
    resultText.select();
    setStatus(text("selected"));
  }
}

function clearText() {
  sourceText.value = "";
  resultText.value = "";
  copyButton.disabled = true;
  updateCharCount();
  setStatus(text("cleared"));
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
  setStatus(text("linkedMachine"), "success");
}

applyLocale();
updateCharCount();
loadConfig().then(refreshUsage);
