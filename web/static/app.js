"use strict";

// ── helpers ───────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

function updateStatus(text, ok) {
  const el = $("save-status");
  el.textContent = text || "";
  el.className = "save-status " + (ok ? "ok" : text ? "err" : "");
  if (text) setTimeout(() => { el.textContent = ""; el.className = "save-status"; }, 4000);
}

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function num(str) {
  const n = parseFloat(str);
  return Number.isFinite(n) ? n : null;
}

function int(str) {
  const n = parseInt(str, 10);
  return Number.isFinite(n) ? n : null;
}

// ── load state into form ─────────────────────────────────────────────────
const SECRET_KEYS = [
  "ollama-api-key", "preconscious-key", "discord-token", "notion-key",
  "notion-default-page-id", "tavily-api-key", "obsidian-host",
  "obsidian-api-key", "github-token", "groq-api-key",
];

const FLAG_KEYS = ["browser-headless", "thinking", "stream-thinking"];

function fill(config) {
  $("mode").checked = !config.local;

  $("local-model").value = config.model || "";
  $("cloud-model").value = config["cloud-model"] || "";
  $("preconscious-model").value = config["preconscious-model"] || "";
  $("home-dir").value = config.home_dir || "";
  $("context-window").value = config.context_window ?? "";
  $("preserve-count").value = config.preserve_count ?? "";
  $("max-tools-per-load").value = config.max_tools_per_load ?? "";

  $("pct-static").value = config.limits_pct?.static ?? "";
  $("pct-conversation").value = config.limits_pct?.conversation ?? "";
  $("pct-episodic").value = config.limits_pct?.episodic ?? "";
  $("pct-output").value = config.limits_pct?.output ?? "";

  $("git-user-name").value = config.git_user_name ?? "";
  $("git-user-email").value = config.git_user_email ?? "";

  for (const f of FLAG_KEYS) $(f).checked = !!config[f];

  $("setup-complete").checked = !!config.setup_complete;

  const secrets = config.secrets || {};
  for (const k of SECRET_KEYS) $(k).value = secrets[k] || "";
}

function hasFlag(id) { return $(id).checked; }

function collectConfig() {
  return {
    local: !$("mode").checked,
    model: $("local-model").value.trim() || "llama3.2:latest",
    "cloud-model": $("cloud-model").value.trim() || "minimax-m3:cloud",
    "preconscious-model": $("preconscious-model").value.trim() || null,
    home_dir: $("home-dir").value.trim() || "/Users/tafadzwamandeya/Documents",
    context_window: int($("context-window").value) || 128000,
    preserve_count: int($("preserve-count").value) || 12,
    max_tools_per_load: int($("max-tools-per-load").value) || 15,
    limits_pct: {
      static: num($("pct-static").value) ?? 18.75,
      conversation: num($("pct-conversation").value) ?? 37.5,
      episodic: num($("pct-episodic").value) ?? 12.5,
      output: num($("pct-output").value) ?? 6.25,
    },
    git_user_name: $("git-user-name").value.trim(),
    git_user_email: $("git-user-email").value.trim(),
    browser_headless: hasFlag("browser-headless"),
    thinking: hasFlag("thinking"),
    stream_thinking: hasFlag("stream-thinking"),
  };
}

function collectSecrets() {
  const s = {};
  for (const k of SECRET_KEYS) s[k] = $(k).value.trim();
  return s;
}

function collectDraft() {
  const draft = collectConfig();
  const complete = $("setup-complete");
  if (complete) draft.setup_complete = complete.checked;
  const secrets = {};
  for (const k of SECRET_KEYS) secrets[k] = !!$(k).value.trim();
  draft.secrets = secrets;
  const list = $("email-list");
  draft.email_count = list ? list.querySelectorAll(".del").length : 0;
  return draft;
}

async function saveAll({ finish = false } = {}) {
  const cfg = collectConfig();
  if (finish) cfg.setup_complete = true;
  try {
    await api("PUT", "/api/config", cfg);
    await api("PUT", "/api/secrets", { secrets: collectSecrets() });
    if (finish) $("setup-complete").checked = true;
    updateStatus(finish ? "Setup complete — Evy is ready." : "Saved — applied live.", true);
    return true;
  } catch (err) {
    updateStatus(err.message, false);
    return false;
  }
}

// ── emails ───────────────────────────────────────────────────────────────
function esc(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function loadEmails() {
  try {
    const conns = await api("GET", "/api/emails");
    const tbody = $("email-list");
    if (!conns.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="muted">No email connections yet.</td></tr>';
      return;
    }
    tbody.innerHTML = conns.map((c) => `
      <tr>
        <td>${esc(c.email)}</td>
        <td>${esc(c.description)}</td>
        <td class="muted"><button class="btn del" data-id="${esc(c.id)}">Delete</button></td>
      </tr>`).join("");
    tbody.querySelectorAll(".del").forEach((b) => {
      b.addEventListener("click", async () => {
        try {
          await api("DELETE", "/api/emails/" + encodeURIComponent(b.dataset.id));
          updateStatus("Email connection deleted.", true);
          loadEmails();
        } catch (err) {
          updateStatus(err.message, false);
        }
      });
    });
  } catch (err) {
    $("email-list").innerHTML = `<tr><td colspan="3" class="muted">${esc(err.message)}</td></tr>`;
  }
}

// ── theme / misc ─────────────────────────────────────────────────────────
function applyTheme(dark) {
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $("theme").checked = dark;
}

function updatePctSum() {
  const pcts = [$("pct-static"), $("pct-conversation"), $("pct-episodic"), $("pct-output")];
  const sum = pcts.reduce((a, p) => a + (parseFloat(p.value) || 0), 0);
  const el = $("pct-sum");
  el.textContent = ` ${sum.toFixed(2).replace(/\.?0+$/, "")}%`;
  el.style.fontWeight = sum <= 0 || sum > 100 ? "600" : "normal";
}

// ── wizard ───────────────────────────────────────────────────────────────
const steps = Array.from(document.querySelectorAll(".step"));
let currentStep = 0;

function showStep(index, { animateComment = true } = {}) {
  if (!steps.length) return;
  currentStep = Math.max(0, Math.min(steps.length - 1, index));
  steps.forEach((el, i) => el.classList.toggle("active", i === currentStep));

  const progress = $("step-progress");
  if (progress) progress.textContent = `Step ${currentStep + 1} of ${steps.length}`;

  const intro = $("intro");
  if (intro) intro.style.display = currentStep === 0 ? "" : "none";

  const step = steps[currentStep];
  const back = step.querySelector('[data-nav="back"]');
  if (back) back.classList.toggle("visible", currentStep > 0);

  if (animateComment) showBubble(step.dataset.comment || "");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ── validation ───────────────────────────────────────────────────────────
const PCT_IDS = ["pct-static", "pct-conversation", "pct-episodic", "pct-output"];

function clearStepErrors(step) {
  if (!step) return;
  step.querySelectorAll(".invalid").forEach((el) => el.classList.remove("invalid"));
  step.querySelectorAll(".field-error").forEach((el) => el.remove());
}

function showErrors(errs) {
  const byField = new Map();
  let first = null;
  for (const [id, msg] of errs) {
    const input = $(id);
    if (!input) continue;
    input.classList.add("invalid");
    const field = input.closest(".field") || input.closest(".checks") || input.parentElement;
    if (field && !byField.has(field)) byField.set(field, []);
    if (field) byField.get(field).push(msg);
    if (!first) first = input;
  }
  for (const [field, msgs] of byField) {
    const p = document.createElement("p");
    p.className = "field-error";
    p.textContent = msgs.join(" ");
    field.appendChild(p);
  }
  if (first) {
    first.focus();
    first.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

// Mandatory information per step. Returns [fieldId, message] pairs.
function validateStep(step) {
  if (!step) return [];
  const errs = [];

  if (step.dataset.step === "llm") {
    if (!$("local-model").value.trim()) {
      errs.push(["local-model", "Enter a local model name."]);
    }
    if (!$("ollama-api-key").value.trim()) {
      errs.push(["ollama-api-key", "An Ollama API key is required."]);
    }
    if ($("mode").checked && !$("cloud-model").value.trim()) {
      errs.push(["cloud-model", "Cloud mode requires a cloud model name."]);
    }
  }

  if (step.dataset.step === "preferences") {
    const home = $("home-dir").value.trim();
    if (!home) {
      errs.push(["home-dir", "Set Evy's home directory — her file-access boundary."]);
    } else if (!/^(~|\/)/.test(home)) {
      errs.push(["home-dir", "Use an absolute path starting with / or ~."]);
    }

    const cw = $("context-window").value.trim();
    if (cw && !(int(cw) > 0)) {
      errs.push(["context-window", "Context window must be a positive number."]);
    }

    const sum = PCT_IDS.reduce((a, id) => a + (parseFloat($(id).value) || 0), 0);
    if (!(sum > 0) || sum > 100) {
      errs.push([PCT_IDS[0], `Token budget must be above 0% and at most 100% (currently ${sum.toFixed(2).replace(/\.?0+$/, "")}%).`]);
    }
  }

  return errs;
}

document.querySelectorAll('.step-nav [data-nav]').forEach((btn) => {
  btn.addEventListener("click", async () => {
    const nav = btn.dataset.nav;
    const step = steps[currentStep];
    clearStepErrors(step);

    if (nav === "back") {
      showStep(currentStep - 1);
      return;
    }

    let errs = validateStep(step);
    if (nav === "finish" && currentStep > 0) {
      for (let i = 0; i < currentStep; i++) errs = errs.concat(validateStep(steps[i]));
    }
    if (errs.length) {
      showErrors(errs);
      updateStatus("Fix the highlighted fields before continuing.", false);
      return;
    }

    btn.disabled = true;
    const ok = await saveAll({ finish: nav === "finish" });
    btn.disabled = false;
    if (!ok) return;
    if (nav === "finish") showBubble("Setup complete — that's everything. Go wake her up.");
    else showStep(currentStep + 1);
  });
});

// Clear a field's error as soon as the user edits it.
document.querySelectorAll("main input").forEach((el) => {
  const clear = () => {
    el.classList.remove("invalid");
    const field = el.closest(".field") || el.closest(".checks");
    if (field) field.querySelectorAll(".field-error").forEach((p) => p.remove());
  };
  el.addEventListener("input", clear);
  el.addEventListener("change", clear);
});

// ── cube helper ──────────────────────────────────────────────────────────
const cubeEl = $("cube");
const bubble = $("cubeBubble");
const tooltip = $("cubeTooltip");
let bubbleTimer = null;
let tooltipTimer = null;
const TOOLTIP_MS = 5000;

function showTooltip() {
  if (!tooltip || qaModal.classList.contains("open")) return;
  clearTimeout(tooltipTimer);
  tooltip.classList.add("visible");
  tooltipTimer = setTimeout(() => tooltip.classList.remove("visible"), TOOLTIP_MS);
}

function hideTooltip() {
  clearTimeout(tooltipTimer);
  tooltip.classList.remove("visible");
}

function showBubble(text) {
  if (!bubble) return;
  if (!text) {
    bubble.classList.remove("visible");
    return;
  }
  bubble.textContent = text;
  hideTooltip();
  bubble.classList.add("visible");
  clearTimeout(bubbleTimer);
  bubbleTimer = setTimeout(() => bubble.classList.remove("visible"), 7000);
}

function hideBubble() {
  clearTimeout(bubbleTimer);
  bubble.classList.remove("visible");
  hideTooltip();
}

if (cubeEl) {
  const pupilLeft = $("pupilLeft");
  const pupilRight = $("pupilRight");
  const eyeLeft = $("eyeLeft");
  const eyeRight = $("eyeRight");

  const FAR = 340, NEAR = 150, CLOSE = 55;
  const IDLE_SCALE = 1, MAX_SCALE = 1.35, MIN_SCALE = 0.4;
  const BASE_ROT_X = -14, BASE_ROT_Y = 24, MAX_PUPIL_OFFSET = 4.5;
  const HEAD_TURN_Y = 36, HEAD_TURN_X = 22;

  let targetX = window.innerWidth / 2;
  let targetY = window.innerHeight / 2;
  let hasPointer = false;

  window.addEventListener("mousemove", (e) => {
    targetX = e.clientX;
    targetY = e.clientY;
    hasPointer = true;
  });
  window.addEventListener("mouseleave", () => { hasPointer = false; });

  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

  function scaleForDistance(dist) {
    if (dist > FAR) return IDLE_SCALE;
    if (dist > NEAR) {
      const t = (FAR - dist) / (FAR - NEAR);
      return IDLE_SCALE + t * (MAX_SCALE - IDLE_SCALE);
    }
    if (dist > CLOSE) {
      const t = (NEAR - dist) / (NEAR - CLOSE);
      return MAX_SCALE - t * (MAX_SCALE - IDLE_SCALE);
    }
    const t = (CLOSE - dist) / CLOSE;
    return IDLE_SCALE - t * (IDLE_SCALE - MIN_SCALE);
  }

  function update() {
    const rect = cubeEl.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const dx = targetX - cx;
    const dy = targetY - cy;
    const dist = Math.hypot(dx, dy);
    const scale = hasPointer ? scaleForDistance(dist) : IDLE_SCALE;

    const nx = clamp(dx / (window.innerWidth / 2), -1, 1);
    const ny = clamp(dy / (window.innerHeight / 2), -1, 1);
    const angleX = hasPointer ? -ny * HEAD_TURN_X : 0;
    const angleY = hasPointer ? nx * HEAD_TURN_Y : 0;

    cubeEl.style.transform =
      `scale(${scale}) rotateX(${BASE_ROT_X + angleX}deg) rotateY(${BASE_ROT_Y + angleY}deg)`;

    const angle = Math.atan2(dy, dx);
    const pupilDist = hasPointer ? Math.min(MAX_PUPIL_OFFSET, dist / 20) : 0;
    const px = Math.cos(angle) * pupilDist;
    const py = Math.sin(angle) * pupilDist * 0.6;

    pupilLeft.style.transform = `translate(calc(-50% + ${px}px), calc(-50% + ${py}px))`;
    pupilRight.style.transform = `translate(calc(-50% + ${px}px), calc(-50% + ${py}px))`;
    requestAnimationFrame(update);
  }
  requestAnimationFrame(update);

  function blink() {
    eyeLeft.classList.add("blink");
    eyeRight.classList.add("blink");
    setTimeout(() => {
      eyeLeft.classList.remove("blink");
      eyeRight.classList.remove("blink");
    }, 120);
    setTimeout(blink, 2600 + Math.random() * 3200);
  }
  setTimeout(blink, 2000);

  cubeEl.addEventListener("mouseenter", () => {
    if (qaModal.classList.contains("open")) return;
    clearTimeout(bubbleTimer);
    bubble.classList.remove("visible");
    showTooltip();
  });
  cubeEl.addEventListener("mouseleave", () => {
    hideTooltip();
    if (!qaModal.classList.contains("open") && steps[currentStep]) {
      showBubble(steps[currentStep].dataset.comment || "");
    }
  });
}

// ── Q&A modal ────────────────────────────────────────────────────────────
const qaModal = $("qaModal");
const qaInput = $("qaInput");
const qaAsk = $("qaAsk");
const qaNote = $("qaNote");
const qaThread = $("qaThread");
const qaHistory = [];
const QA_MEMORY = 5;

function setNote(text, isErr) {
  qaNote.textContent = text || "";
  qaNote.className = "qa-note" + (isErr ? " err" : "");
}

function openQA() {
  qaModal.classList.add("open");
  qaModal.setAttribute("aria-hidden", "false");
  hideBubble();
  qaInput.focus();
}

function closeQA() {
  qaModal.classList.remove("open");
  qaModal.setAttribute("aria-hidden", "true");
}

async function askQuestion() {
  const question = qaInput.value.trim();
  if (!question) { qaInput.focus(); return; }

  const cloud = $("mode").checked;
  const key = $("ollama-api-key").value.trim();
  if (cloud && !key) {
    setNote("Add your Ollama API key in the LLM step to ask questions here.", true);
    return;
  }

  const pair = document.createElement("div");
  pair.className = "qa-pair";
  const qEl = document.createElement("p");
  qEl.className = "qa-q";
  qEl.textContent = question;
  const aEl = document.createElement("p");
  aEl.className = "qa-a pending";
  aEl.textContent = "Thinking…";
  pair.append(qEl, aEl);
  qaThread.innerHTML = "";
  qaThread.appendChild(pair);
  qaThread.scrollTop = qaThread.scrollHeight;

  qaInput.value = "";
  setNote("", false);
  qaAsk.disabled = true;
  const stepEl = steps[currentStep];
  try {
    const data = await api("POST", "/api/ask", {
      question,
      step: stepEl?.dataset.step || "",
      step_title: stepEl?.dataset.title || "",
      draft: collectDraft(),
      history: qaHistory.slice(),
    });
    aEl.className = "qa-a";
    aEl.textContent = data.answer || "(no answer)";
    qaHistory.push({ question, answer: data.answer || "" });
    if (qaHistory.length > QA_MEMORY) qaHistory.shift();
  } catch (err) {
    aEl.className = "qa-a err";
    aEl.textContent = err.message;
  } finally {
    qaAsk.disabled = false;
    qaThread.scrollTop = qaThread.scrollHeight;
  }
}

if (qaModal && cubeEl) {
  cubeEl.addEventListener("click", (e) => {
    e.stopPropagation();
    if (qaModal.classList.contains("open")) closeQA();
    else openQA();
  });
  $("qaClose").addEventListener("click", (e) => { e.stopPropagation(); closeQA(); });
  qaAsk.addEventListener("click", askQuestion);
  qaInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) askQuestion();
  });
  qaModal.addEventListener("click", (e) => e.stopPropagation());
  document.addEventListener("click", (e) => {
    if (qaModal.classList.contains("open") && !qaModal.contains(e.target) && e.target !== cubeEl) {
      closeQA();
    }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeQA(); });
}

// ── field / button listeners ─────────────────────────────────────────────
$("email-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("POST", "/api/emails", {
      email: $("email-addr").value.trim(),
      app_password: $("email-pass").value.trim(),
      description: $("email-desc").value.trim(),
    });
    $("email-form").reset();
    updateStatus("Email connection added.", true);
    loadEmails();
  } catch (err) {
    updateStatus(err.message, false);
  }
});

$("theme").addEventListener("change", (e) => {
  const dark = e.target.checked;
  applyTheme(dark);
  try { localStorage.setItem("evy-theme", dark ? "dark" : "light"); } catch (err) {}
});

document.querySelectorAll(".eye").forEach((btn) => {
  btn.addEventListener("click", () => {
    const input = $(btn.dataset.eye);
    if (!input) return;
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    btn.textContent = show ? "hide" : "view";
  });
});

for (const id of ["pct-static", "pct-conversation", "pct-episodic", "pct-output"]) {
  $(id).addEventListener("input", updatePctSum);
}

$("save-all").addEventListener("click", () => saveAll());
$("migrate").addEventListener("click", async () => {
  try {
    const res = await api("POST", "/api/migrate");
    updateStatus("Migrated from .env — " + Object.entries(res.secrets).length + " secrets present.", true);
  } catch (err) {
    updateStatus(err.message, false);
  }
});

// ── topbar border on scroll ──────────────────────────────────────────────
(function topbarScroll() {
  const topbar = document.querySelector(".topbar");
  if (!topbar) return;
  const update = () => topbar.classList.toggle("scrolled", window.scrollY > 4);
  window.addEventListener("scroll", update, { passive: true });
  update();
})();

// ── init ─────────────────────────────────────────────────────────────────
(async function boot() {
  try {
    const saved = localStorage.getItem("evy-theme");
    if (saved) applyTheme(saved === "dark");
  } catch (err) {}
  try {
    const cfg = await api("GET", "/api/config");
    fill(cfg);
    updatePctSum();
  } catch (err) {
    updateStatus("Failed to load config: " + err.message, false);
  }
  loadEmails();
  showStep(0);
})();

// ── background helix ─────────────────────────────────────────────────────
// Mirrors utilities/scripts/helix_engine.py so both hosts share one look.
(function helixBackground() {
  const canvas = $("helix-bg");
  if (!canvas || !canvas.getContext) return;
  const ctx = canvas.getContext("2d");

  const STRAND_CHAR = "✱";
  const RUNG_CHAR = ":";
  const AMPLITUDE_SCALE = 0.35;
  const WAVELENGTH = 3.0;
  const SPEED = 0.05;
  const RUNG_EVERY = 2;
  const FONT = "14px 'Geist Mono', ui-monospace, monospace";
  const CHAR_H = 14;

  let phase = 0;
  const dpr = window.devicePixelRatio || 1;

  function resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();
  window.addEventListener("resize", resize);

  function fgColor() {
    return getComputedStyle(document.documentElement).getPropertyValue("--fg").trim() || "#000";
  }

  function draw() {
    const w = canvas.width / dpr;
    const h = canvas.height / dpr;
    ctx.clearRect(0, 0, w, h);
    ctx.font = FONT;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    const color = fgColor();
    const charW = ctx.measureText(STRAND_CHAR).width || 9;
    const cy = h / 2;
    const radius = Math.min(h * AMPLITUDE_SCALE, h * 0.20);
    const length = Math.floor((w * 0.7) / charW);
    const startX = (w - length * charW) / 2;

    for (let u = 0; u < length; u++) {
      const theta = u / WAVELENGTH + phase;
      const y1 = cy + Math.sin(theta) * radius;
      const y2 = cy + Math.sin(theta + Math.PI) * radius;
      const depth1 = Math.cos(theta);
      const depth2 = Math.cos(theta + Math.PI);
      const px = startX + u * charW + charW / 2;

      ctx.fillStyle = color;

      // Back strand first, then front — matches the engine's draw order.
      const order = [[depth1, y1], [depth2, y2]].sort((a, b) => a[0] - b[0]);
      for (const [depth, y] of order) {
        ctx.globalAlpha = depth >= 0 ? 0.34 : 0.16;
        ctx.fillText(STRAND_CHAR, px, y);
      }

      if (u % RUNG_EVERY === 0 && Math.abs(y1 - y2) > 1.2 * CHAR_H) {
        ctx.globalAlpha = 0.20;
        const top = Math.min(y1, y2);
        const bottom = Math.max(y1, y2);
        for (let ry = top + CHAR_H / 2; ry < bottom; ry += CHAR_H) {
          ctx.fillText(RUNG_CHAR, px, ry);
        }
      }
    }

    ctx.globalAlpha = 1;
    phase += SPEED;
    requestAnimationFrame(draw);
  }
  draw();
})();
