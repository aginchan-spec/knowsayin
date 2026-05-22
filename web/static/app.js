const sourceText = document.querySelector("#sourceText");
const resultText = document.querySelector("#resultText");
const optimizeButton = document.querySelector("#optimizeButton");
const copyButton = document.querySelector("#copyButton");
const clearButton = document.querySelector("#clearButton");
const statusLine = document.querySelector("#status");
const quota = document.querySelector("#quota");
const charCount = document.querySelector("#charCount");
const passPanel = document.querySelector("#passPanel");
const passInput = document.querySelector("#passInput");
const savePassButton = document.querySelector("#savePassButton");

const PASS_KEY = "justsaying.friendPass";
const BASE_PATH = window.JUSTSAYING_BASE_PATH || "";
const LONG_TEXT_THRESHOLD = 800;

function apiPath(path) {
  return BASE_PATH + path;
}

function getPassFromLocation() {
  const url = new URL(window.location.href);
  const queryPass = url.searchParams.get("pass");
  const passPrefix = BASE_PATH + "/p/";
  if (window.location.pathname.startsWith(passPrefix)) {
    return decodeURIComponent(window.location.pathname.slice(passPrefix.length));
  }
  return queryPass || "";
}

function currentPass() {
  return localStorage.getItem(PASS_KEY) || "";
}

function setStatus(message, kind = "") {
  statusLine.textContent = message || "";
  statusLine.dataset.kind = kind;
}

function setQuota(remaining, dailyLimit) {
  if (Number.isFinite(remaining) && Number.isFinite(dailyLimit)) {
    quota.textContent = "今日剩余 " + remaining + "/" + dailyLimit;
    return;
  }
  quota.textContent = "今日剩余 -";
}

function textLength(value) {
  return Array.from(value || "").length;
}

function updateCharCount(maxChars = sourceText.maxLength) {
  const current = textLength(sourceText.value);
  const limit = Number.isFinite(maxChars) && maxChars > 0 ? maxChars : sourceText.maxLength;
  charCount.textContent = current + " / " + limit;
  charCount.dataset.kind = current >= limit ? "error" : "";
}

async function requestJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.message || "请求失败");
    error.data = data;
    error.status = response.status;
    throw error;
  }
  return data;
}

async function refreshUsage() {
  try {
    const data = await requestJson(apiPath("/api/usage"), { pass: currentPass() });
    setQuota(data.remaining, data.dailyLimit);
    if (data.maxChars) {
      sourceText.maxLength = data.maxChars;
      updateCharCount(data.maxChars);
    }
    passPanel.hidden = true;
  } catch (error) {
    if (error.data && error.data.error === "PASS_REQUIRED") {
      passPanel.hidden = false;
      setStatus("");
      return;
    }
    if (error.data && error.data.error === "PASS_INVALID") {
      passPanel.hidden = false;
      setStatus("访问口令无效或已停用。", "error");
      return;
    }
  }
}

async function optimize() {
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
    const data = await requestJson(apiPath("/api/clean"), {
      pass: currentPass(),
      text,
      mode: "medium",
    });
    resultText.value = data.result || "";
    copyButton.disabled = !resultText.value;
    setQuota(data.remaining, data.dailyLimit);
    if (data.maxChars) {
      sourceText.maxLength = data.maxChars;
      updateCharCount(data.maxChars);
    }
    setStatus("已优化。");
    document.querySelector(".result-editor").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (error.data && error.data.error === "PASS_REQUIRED") {
      passPanel.hidden = false;
    }
    setStatus(error.message || "优化失败。", "error");
  } finally {
    optimizeButton.disabled = false;
    delete document.body.dataset.busy;
  }
}

async function copyResult() {
  const text = resultText.value.trim();
  if (!text) {
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    setStatus("已复制。");
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

function savePass() {
  const value = passInput.value.trim();
  if (!value) {
    setStatus("请输入访问口令。", "error");
    return;
  }
  localStorage.setItem(PASS_KEY, value);
  passInput.value = "";
  refreshUsage();
}

const initialPass = getPassFromLocation();
if (initialPass) {
  localStorage.setItem(PASS_KEY, initialPass);
  history.replaceState(null, "", BASE_PATH ? BASE_PATH + "/" : "/");
}

savePassButton.addEventListener("click", savePass);
passInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    savePass();
  }
});
optimizeButton.addEventListener("click", optimize);
copyButton.addEventListener("click", copyResult);
clearButton.addEventListener("click", clearText);
sourceText.addEventListener("input", () => {
  updateCharCount();
  setStatus("");
});

updateCharCount();
refreshUsage();
