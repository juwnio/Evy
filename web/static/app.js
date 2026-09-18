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

function collectConfig(extra = {}) {
  const cfg = {
    local: !$("mode").checked,
    model: $("local-model").value.trim() || "llama3.2:latest",
    "cloud-model": $("cloud-model").value.trim() || "minimax-m3:cloud",
    "preconscious-model": $("preconscious-model").value.trim() || null,
    home_dir: $("home-dir").value.trim() || "/Users/tafadzwamandeya/Documents",
    context_window: int($("context-window").value) || 128000,
    preserve_count: int($("preserve-count").value) || 12,
    max_tools_per_load: int($("max-tools-per-load").value) || 15,
    limits_pct: {
      static: num($("pct-static").value) ?? 0.20,
      conversation: num($("pct-conversation").value) ?? 0.40,
      episodic: num($("pct-episodic").value) ?? 0.15,
      output: num($("pct-output").value) ?? 0.05,
    },
    git_user_name: $("git-user-name").value.trim() || "eveagnt-byte",
    git_user_email: $("git-user-email").value.trim() || "eve.agnt@gmail.com",
    ...extra,
  };
  for (const f of FLAG_KEYS) cfg[f] = hasFlag(f);
  return cfg;
}

function collectSecrets() {
  const s = {};
  for (const k of SECRET_KEYS) s[k] = $(k).value.trim();
  return s;
}

async function saveAll({ finish = false } = {}) {
  const cfg = collectConfig();
  if (finish) cfg.setup_complete = true;
  try {
    await api("PUT", "/api/config", cfg);
    await api("PUT", "/api/secrets", { secrets: collectSecrets() });
    updateStatus("Saved — applied live.", true);
  } catch (err) {
    updateStatus(err.message, false);
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

// ── init ─────────────────────────────────────────────────────────────────
function applyTheme(dark) {
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $("theme").checked = dark;
}

function updatePctSum() {
  const pcts = [$("pct-static"), $("pct-conversation"), $("pct-episodic"), $("pct-output")];
  const sum = pcts.reduce((a, p) => a + (parseFloat(p.value) || 0), 0);
  $("pct-sum").textContent = ` sum ${(sum * 100).toFixed(0)}%`;
  $("pct-sum").style.fontWeight = Math.abs(sum - 1) > 0.05 ? "600" : "normal";
}

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
$("save-all-2").addEventListener("click", () => saveAll());
$("save-finish").addEventListener("click", () => saveAll({ finish: true }));
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