const machineCodeInput = document.querySelector("#machineCode");
const checkoutForm = document.querySelector("#checkoutForm");
const checkoutButton = document.querySelector("#checkoutButton");
const copyCodeButton = document.querySelector("#copyCodeButton");
const statusLine = document.querySelector("#statusLine");
const downloadLink = document.querySelector("#downloadLink");
const githubLink = document.querySelector("#githubLink");
const scene = document.querySelector(".scene");

function normalizeDeviceCode(value) {
  return Array.from(value || "")
    .filter((char) => /[a-z0-9]/i.test(char))
    .join("")
    .toUpperCase()
    .slice(0, 16);
}

function setStatus(message, kind = "") {
  statusLine.textContent = message || "";
  statusLine.dataset.kind = kind;
}

async function requestJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.message || "Request failed.");
    error.data = data;
    error.status = response.status;
    throw error;
  }
  return data;
}

async function loadConfig() {
  try {
    const response = await fetch("/api/config", { headers: { Accept: "application/json" } });
    const data = await response.json();
    if (data.downloadUrl) {
      downloadLink.href = data.downloadUrl;
    }
    if (data.githubUrl) {
      githubLink.href = data.githubUrl;
    }
    if (!data.checkoutEnabled) {
      checkoutButton.textContent = "Copy code for activation";
    }
  } catch {
    githubLink.href = "https://github.com/aginchan-spec/knowsayin";
  }
}

function readMachineFromUrl() {
  const params = new URL(window.location.href).searchParams;
  return normalizeDeviceCode(params.get("machine") || params.get("device") || params.get("code") || "");
}

async function copyMachineCode() {
  const deviceCode = normalizeDeviceCode(machineCodeInput.value);
  machineCodeInput.value = deviceCode;
  if (!deviceCode) {
    setStatus("Enter the machine code shown in the KnowSayin app.", "error");
    machineCodeInput.focus();
    return;
  }

  try {
    await navigator.clipboard.writeText(deviceCode);
    setStatus("Machine code copied.", "success");
  } catch {
    machineCodeInput.focus();
    machineCodeInput.select();
    setStatus("Machine code selected. Copy it manually.", "success");
  }
}

async function startCheckout(event) {
  event.preventDefault();
  const deviceCode = normalizeDeviceCode(machineCodeInput.value);
  machineCodeInput.value = deviceCode;

  if (!deviceCode) {
    setStatus("Enter the machine code shown in the KnowSayin app.", "error");
    machineCodeInput.focus();
    return;
  }

  checkoutButton.disabled = true;
  setStatus("Preparing upgrade...");

  try {
    const data = await requestJson("/api/checkout", { deviceCode });
    if (data.checkoutUrl) {
      window.location.assign(data.checkoutUrl);
      return;
    }
    setStatus("Upgrade is not ready yet. Copy your code for manual activation.", "error");
  } catch (error) {
    if (error.data && error.data.deviceCode) {
      machineCodeInput.value = error.data.deviceCode;
    }
    setStatus(error.message || "Upgrade is not ready yet. Copy your code for manual activation.", "error");
  } finally {
    checkoutButton.disabled = false;
  }
}

function updateScenePointer(event) {
  if (!scene) {
    return;
  }
  const x = Math.round((event.clientX / window.innerWidth) * 100);
  const y = Math.round((event.clientY / window.innerHeight) * 100);
  scene.style.setProperty("--mx", `${x}%`);
  scene.style.setProperty("--my", `${y}%`);
}

machineCodeInput.addEventListener("input", () => {
  machineCodeInput.value = normalizeDeviceCode(machineCodeInput.value);
  setStatus("");
});
checkoutForm.addEventListener("submit", startCheckout);
copyCodeButton.addEventListener("click", copyMachineCode);
window.addEventListener("pointermove", updateScenePointer, { passive: true });

const initialMachineCode = readMachineFromUrl();
if (initialMachineCode) {
  machineCodeInput.value = initialMachineCode;
  setStatus("Machine code loaded from the app.", "success");
}

loadConfig();
