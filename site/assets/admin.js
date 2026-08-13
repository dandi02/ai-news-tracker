/* Admin console: edits config/sources.yaml + data/overrides.json via the GitHub
   contents API and triggers pipeline runs via workflow_dispatch. */
(() => {
  "use strict";

  const LS_TOKEN = "sqp_tracker_pat";
  const LS_REPO = "sqp_tracker_repo";
  const API = "https://api.github.com";
  const WORKFLOW = "build.yml";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  let repo = localStorage.getItem(LS_REPO) || "";
  let token = localStorage.getItem(LS_TOKEN) || "";
  let sourcesDoc = null;   // parsed sources.yaml
  let sourcesSha = null;
  let overrides = {};      // data/overrides.json content
  let overridesSha = null; // null => file may not exist yet

  // ---------- GitHub API helpers ----------
  async function gh(path, opts = {}) {
    const resp = await fetch(`${API}${path}`, {
      ...opts,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        ...(opts.headers || {}),
      },
    });
    if (!resp.ok && resp.status !== 404) {
      throw new Error(`GitHub ${resp.status}: ${(await resp.text()).slice(0, 200)}`);
    }
    return resp;
  }

  const b64encode = (str) => btoa(String.fromCharCode(...new TextEncoder().encode(str)));
  const b64decode = (b64) => new TextDecoder().decode(
    Uint8Array.from(atob(b64.replace(/\n/g, "")), (c) => c.charCodeAt(0)));

  async function loadFile(path) {
    const resp = await gh(`/repos/${repo}/contents/${path}`);
    if (resp.status === 404) return { content: null, sha: null };
    const data = await resp.json();
    return { content: b64decode(data.content), sha: data.sha };
  }

  async function saveFile(path, content, sha, message, retried = false) {
    const body = { message, content: b64encode(content) };
    if (sha) body.sha = sha;
    const resp = await gh(`/repos/${repo}/contents/${path}`, {
      method: "PUT", body: JSON.stringify(body),
    });
    if ((resp.status === 409 || resp.status === 422) && !retried) {
      const fresh = await loadFile(path);          // sha conflict: refetch and retry once
      return saveFile(path, content, fresh.sha, message, true);
    }
    if (!resp.ok) throw new Error(`save failed: ${resp.status}`);
    return (await resp.json()).content.sha;
  }

  // ---------- setup gate ----------
  function detectRepo() {
    const parts = location.hostname.split(".");
    if (parts[1] === "github" && parts[2] === "io") {
      const name = location.pathname.split("/")[1];
      if (name) return `${parts[0]}/${name}`;
    }
    return "";
  }

  async function connect() {
    repo = $("repo-input").value.trim();
    token = $("token-input").value.trim();
    $("setup-error").textContent = "";
    try {
      const resp = await gh(`/repos/${repo}`);
      if (resp.status === 404) throw new Error("repository not found (check name & token scope)");
      localStorage.setItem(LS_REPO, repo);
      localStorage.setItem(LS_TOKEN, token);
      await boot();
    } catch (err) {
      $("setup-error").textContent = err.message;
    }
  }

  // ---------- sources editor ----------
  const LIST_SECTIONS = [
    { key: "reddit", title: "Subreddits", fields: ["name"] },
    { key: "github_releases", title: "GitHub release watchlist (owner/repo)", fields: ["repo"] },
    { key: "github_watchlist", title: "GitHub star watchlist — always on the boards (owner/repo)", fields: ["repo"] },
    { key: "feeds", title: "RSS / blog feeds", fields: ["name", "url"] },
    { key: "youtube", title: "YouTube channels", fields: ["name", "channel_id"] },
    { key: "bluesky", title: "Bluesky handles", fields: ["handle"] },
  ];

  function renderSources() {
    const host = $("sources-editor");
    host.innerHTML = "";
    for (const section of LIST_SECTIONS) {
      const entries = sourcesDoc[section.key] || [];
      const div = document.createElement("div");
      div.className = "src-section";
      div.innerHTML = `<h3>${esc(section.title)}</h3>`;
      entries.forEach((entry, i) => {
        const row = document.createElement("div");
        row.className = "src-row";
        row.innerHTML = `
          <input type="checkbox" ${entry.enabled !== false ? "checked" : ""} title="enabled">
          ${section.fields.map((f) =>
            `<input type="text" data-field="${f}" value="${esc(entry[f] || "")}" placeholder="${f}">`).join("")}
          <button class="rm" title="remove">✕</button>`;
        row.querySelector("input[type=checkbox]").addEventListener("change", (e) => {
          entry.enabled = e.target.checked;
        });
        row.querySelectorAll("input[type=text]").forEach((inp) => {
          inp.addEventListener("input", () => { entry[inp.dataset.field] = inp.value.trim(); });
        });
        row.querySelector(".rm").addEventListener("click", () => {
          entries.splice(i, 1);
          renderSources();
        });
        div.appendChild(row);
      });
      const add = document.createElement("button");
      add.className = "ghost add-row";
      add.textContent = "+ add";
      add.addEventListener("click", () => {
        const blank = { enabled: true };
        section.fields.forEach((f) => { blank[f] = ""; });
        (sourcesDoc[section.key] = sourcesDoc[section.key] || []).push(blank);
        renderSources();
      });
      div.appendChild(add);
      host.appendChild(div);
    }
  }

  async function saveSources() {
    $("save-status").textContent = "saving…";
    try {
      const yamlText = jsyaml.dump(sourcesDoc, { lineWidth: 120 });
      sourcesSha = await saveFile("config/sources.yaml", yamlText, sourcesSha,
        "admin: update sources");
      $("save-status").textContent = "✓ saved";
      if (confirm("Sources saved. Trigger a re-scan now so the feed picks them up?")) rescan();
    } catch (err) {
      $("save-status").textContent = `✗ ${err.message}`;
    }
  }

  // ---------- curation ----------
  let feedItems = [];

  async function loadCuration() {
    try {
      const resp = await fetch("data/feed.json", { cache: "no-cache" });
      const feed = await resp.json();
      feedItems = feed.days[0]?.items || [];
    } catch {
      feedItems = [];
    }
    renderCuration();
  }

  function renderCuration() {
    const host = $("curate-list");
    if (!feedItems.length) {
      host.innerHTML = '<p class="empty">No items in today\'s feed (run the pipeline first).</p>';
      return;
    }
    host.innerHTML = "";
    for (const item of feedItems) {
      const ov = overrides[item.id] || {};
      const row = document.createElement("article");
      row.className = "card";
      row.innerHTML = `
        <div class="card-top">
          <span class="badge" style="background: var(--cat-${esc(item.category)}, var(--cat-discussion))">${esc(item.category)}</span>
          <span class="importance">${item.importance}</span>
          <a class="card-title" href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a>
        </div>
        <div class="card-meta cur-actions">
          <span>${esc(item.source_name)}</span>
          <span style="flex:1"></span>
          <button class="ghost pin ${ov.pinned ? "on" : ""}">📌 Pin</button>
          <button class="ghost hide ${ov.hidden ? "on" : ""}">🙈 Hide</button>
          <button class="ghost tag">🏷 ${(ov.tags || []).join(", ") || "Tag"}</button>
        </div>`;
      const upsert = () => (overrides[item.id] = overrides[item.id] || {});
      row.querySelector(".pin").addEventListener("click", (e) => {
        const o = upsert(); o.pinned = !o.pinned;
        e.target.classList.toggle("on", o.pinned);
      });
      row.querySelector(".hide").addEventListener("click", (e) => {
        const o = upsert(); o.hidden = !o.hidden;
        e.target.classList.toggle("on", o.hidden);
      });
      row.querySelector(".tag").addEventListener("click", (e) => {
        const o = upsert();
        const current = (o.tags || []).join(", ");
        const next = prompt("Tags (comma-separated):", current);
        if (next !== null) {
          o.tags = next.split(",").map((t) => t.trim()).filter(Boolean);
          e.target.textContent = `🏷 ${o.tags.join(", ") || "Tag"}`;
        }
      });
      host.appendChild(row);
    }
  }

  async function saveOverrides() {
    $("curate-status").textContent = "saving…";
    try {
      // drop empty override entries
      for (const [k, v] of Object.entries(overrides)) {
        if (!v.pinned && !v.hidden && !(v.tags || []).length) delete overrides[k];
      }
      overridesSha = await saveFile("data/overrides.json",
        JSON.stringify(overrides, null, 1), overridesSha, "admin: curation update");
      $("curate-status").textContent = "✓ saved (live within ~1 min)";
    } catch (err) {
      $("curate-status").textContent = `✗ ${err.message}`;
    }
  }

  // ---------- re-scan ----------
  async function rescan() {
    $("run-status").textContent = "triggering…";
    try {
      const resp = await gh(`/repos/${repo}/actions/workflows/${WORKFLOW}/dispatches`, {
        method: "POST", body: JSON.stringify({ ref: "main" }),
      });
      if (resp.status !== 204) throw new Error(`dispatch failed: ${resp.status}`);
      $("run-status").textContent = "run queued…";
      setTimeout(pollRun, 5000);
    } catch (err) {
      $("run-status").textContent = `✗ ${err.message}`;
    }
  }

  async function pollRun() {
    try {
      const resp = await gh(`/repos/${repo}/actions/workflows/${WORKFLOW}/runs?per_page=1`);
      const run = (await resp.json()).workflow_runs?.[0];
      if (!run) return;
      const link = `<a href="${esc(run.html_url)}" target="_blank" rel="noopener">view</a>`;
      if (run.status !== "completed") {
        $("run-status").innerHTML = `run ${esc(run.status)}… ${link}`;
        setTimeout(pollRun, 10000);
      } else {
        $("run-status").innerHTML =
          `run ${run.conclusion === "success" ? "✓ succeeded" : `✗ ${esc(run.conclusion)}`} ${link}`;
      }
    } catch { /* polling is best-effort */ }
  }

  // ---------- boot ----------
  async function boot() {
    $("setup").classList.add("hidden");
    $("app").classList.remove("hidden");
    $("forget-token").classList.remove("hidden");

    const src = await loadFile("config/sources.yaml");
    sourcesDoc = jsyaml.load(src.content) || {};
    sourcesSha = src.sha;
    renderSources();

    const ov = await loadFile("data/overrides.json");
    overrides = ov.content ? JSON.parse(ov.content) : {};
    overridesSha = ov.sha;
    await loadCuration();
  }

  // ---------- page link hub (visible without a token) ----------
  function renderPageLinks() {
    const base = location.href.replace(/admin\.html.*$/, "");
    const repoGuess = localStorage.getItem(LS_REPO) || detectRepo();
    const links = [
      ["News feed — share this with the team", base],
      ["RSS feed — for feed readers (Feedly etc.)", base + "feed.xml"],
      ["Admin console — this page", base + "admin.html"],
    ];
    if (repoGuess) {
      links.push(
        ["Code & settings — the GitHub repository", `https://github.com/${repoGuess}`],
        ["Run history & logs — see every daily build", `https://github.com/${repoGuess}/actions`],
        ["Edit sources directly on GitHub — no token needed", `https://github.com/${repoGuess}/edit/main/config/sources.yaml`],
      );
    }
    document.getElementById("links-list").innerHTML = links.map(([label, url]) =>
      `<li><strong>${esc(label)}</strong><br><a href="${esc(url)}">${esc(url)}</a></li>`).join("");
  }
  renderPageLinks();

  // tabs
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      $("tab-sources").classList.toggle("hidden", btn.dataset.tab !== "sources");
      $("tab-curate").classList.toggle("hidden", btn.dataset.tab !== "curate");
    });
  });

  $("connect-btn").addEventListener("click", connect);
  $("save-sources").addEventListener("click", saveSources);
  $("save-overrides").addEventListener("click", saveOverrides);
  $("rescan-btn").addEventListener("click", rescan);
  $("forget-token").addEventListener("click", () => {
    localStorage.removeItem(LS_TOKEN);
    location.reload();
  });

  if (token && repo) {
    boot().catch((err) => {
      $("app").classList.add("hidden");
      $("setup").classList.remove("hidden");
      $("setup-error").textContent = `Reconnect needed: ${err.message}`;
      $("repo-input").value = repo;
    });
  } else {
    $("setup").classList.remove("hidden");
    $("repo-input").value = repo || detectRepo();
  }
})();
