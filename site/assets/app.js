/* Feed UI: loads data/feed.json, renders pinned + per-day items with filters. */
(() => {
  "use strict";

  const CATEGORIES = ["new-model-release", "tooling", "research", "fine-tune", "dataset", "discussion"];
  const SOURCE_TYPES = ["reddit", "github_repo", "github_release", "hf_model", "hf_paper", "hackernews", "rss", "youtube", "bluesky"];
  const SOURCE_LABELS = {
    reddit: "Reddit", github_repo: "GitHub repos", github_release: "Releases",
    hf_model: "HF models", hf_paper: "HF papers", hackernews: "Hacker News",
    rss: "Blogs", youtube: "YouTube", bluesky: "Bluesky",
  };

  const state = {
    feed: null,
    search: "",
    categories: new Set(),
    sources: new Set(),
    minImportance: 1,
  };

  // ---------- theme ----------
  const root = document.documentElement;
  const savedTheme = localStorage.getItem("sqp_theme");
  if (savedTheme) root.dataset.theme = savedTheme;
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const dark = root.dataset.theme === "dark" ||
      (!root.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
    root.dataset.theme = dark ? "light" : "dark";
    localStorage.setItem("sqp_theme", root.dataset.theme);
  });

  // ---------- rendering ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function relTime(iso) {
    const then = Date.parse(iso);
    if (Number.isNaN(then)) return "";
    const mins = Math.round((Date.now() - then) / 60000);
    if (mins < 60) return `${mins}m ago`;
    if (mins < 60 * 24) return `${Math.round(mins / 60)}h ago`;
    return `${Math.round(mins / 1440)}d ago`;
  }

  function engagementText(e) {
    if (!e) return "";
    const parts = [];
    if (e.points) parts.push(`▲ ${e.points}`);
    if (e.stars) parts.push(`★ ${e.stars}`);
    if (e.likes) parts.push(`♥ ${e.likes}`);
    if (e.downloads) parts.push(`⇩ ${e.downloads.toLocaleString()}`);
    if (e.comments) parts.push(`💬 ${e.comments}`);
    return parts.join(" · ");
  }

  function matches(item) {
    if (item.importance < state.minImportance) return false;
    if (state.categories.size && !state.categories.has(item.category)) return false;
    if (state.sources.size && !state.sources.has(item.source_type)) return false;
    if (state.search) {
      const hay = `${item.title} ${item.summary} ${item.snippet}`.toLowerCase();
      if (!hay.includes(state.search)) return false;
    }
    return true;
  }

  function cardHtml(item) {
    const alsoOn = (item.also_on || []).map((a) =>
      `<a href="${esc(a.url)}" target="_blank" rel="noopener">also on ${esc(a.source_name)}${
        a.engagement?.points ? ` (${a.engagement.points} pts)` : ""}</a>`).join(" · ");
    const tags = (item.tags || []).map((t) => `<span class="tag">#${esc(t)}</span>`).join(" ");
    const impClass = item.importance >= 8 ? "importance high" : "importance";
    const curatedNote = item.curated ? "" :
      '<span class="uncurated" title="Scored by keyword fallback">keyword-ranked</span>';
    return `<article class="card${item.pinned ? " pinned" : ""}">
      <div class="card-top">
        <span class="badge" style="background: var(--cat-${esc(item.category)}, var(--cat-discussion))">${esc(item.category)}</span>
        <span class="${impClass}" title="Importance">${item.importance}</span>
        <a class="card-title" href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a>
      </div>
      <p class="card-summary">${esc(item.summary)}</p>
      <div class="card-meta">
        <span>${esc(item.source_name)}</span>
        <span>${engagementText(item.engagement)}</span>
        <span>${relTime(item.created_at)}</span>
        ${alsoOn ? `<span>${alsoOn}</span>` : ""}
        ${tags} ${curatedNote}
      </div>
    </article>`;
  }

  function render() {
    const feed = state.feed;
    if (!feed) return;

    // pinned across all days
    const pinned = feed.days.flatMap((d) => d.items).filter((i) => i.pinned && matches(i));
    const pinnedSection = document.getElementById("pinned-section");
    pinnedSection.classList.toggle("hidden", pinned.length === 0);
    document.getElementById("pinned-items").innerHTML = pinned.map(cardHtml).join("");

    const daysEl = document.getElementById("days");
    let any = pinned.length > 0;
    daysEl.innerHTML = feed.days.map((day, idx) => {
      const items = day.items.filter((i) => matches(i) && !i.pinned);
      if (!items.length) return "";
      any = true;
      const label = idx === 0 ? `Today · ${day.date}` : day.date;
      const open = idx < 2 ? " open" : "";
      return `<details class="day"${open}><summary>${esc(label)} (${items.length})</summary>
        ${items.map(cardHtml).join("")}</details>`;
    }).join("");

    document.getElementById("empty-state").classList.toggle("hidden", any);
  }

  // ---------- controls ----------
  function chip(label, value, set) {
    const el = document.createElement("button");
    el.className = "chip";
    el.textContent = label;
    el.addEventListener("click", () => {
      set.has(value) ? set.delete(value) : set.add(value);
      el.classList.toggle("active");
      render();
    });
    return el;
  }
  const catChips = document.getElementById("category-chips");
  CATEGORIES.forEach((c) => catChips.appendChild(chip(c, c, state.categories)));
  const srcChips = document.getElementById("source-chips");
  SOURCE_TYPES.forEach((s) => srcChips.appendChild(chip(SOURCE_LABELS[s] || s, s, state.sources)));

  document.getElementById("search").addEventListener("input", (e) => {
    state.search = e.target.value.trim().toLowerCase();
    render();
  });
  const slider = document.getElementById("importance");
  slider.addEventListener("input", () => {
    state.minImportance = Number(slider.value);
    document.getElementById("importance-value").textContent = slider.value;
    render();
  });

  // ---------- status strip ----------
  function showStatus(feed) {
    const failures = Object.entries(feed.sources_status || {})
      .filter(([, s]) => !s.ok).map(([name]) => name);
    const uncurated = feed.days[0]?.items.some((i) => !i.curated);
    const strip = document.getElementById("status-strip");
    const msgs = [];
    if (failures.length) msgs.push(`⚠️ Source failures in last run: ${failures.join(", ")}`);
    if (uncurated) msgs.push("⚠️ AI curation was unavailable — items are keyword-ranked");
    strip.textContent = msgs.join(" · ");
    strip.classList.toggle("hidden", msgs.length === 0);
  }

  // ---------- boot ----------
  async function boot() {
    let feed;
    try {
      const resp = await fetch("data/feed.json", { cache: "no-cache" });
      feed = await resp.json();
    } catch {
      document.getElementById("days").innerHTML =
        '<p class="empty">No feed data yet — run the pipeline first.</p>';
      return;
    }

    // live overrides: pins/hides apply before the next deploy (best-effort)
    try {
      const parts = location.hostname.split(".");
      if (parts[1] === "github" && parts[2] === "io") {
        const owner = parts[0];
        const repo = location.pathname.split("/")[1];
        const ovResp = await fetch(
          `https://raw.githubusercontent.com/${owner}/${repo}/main/data/overrides.json`,
          { cache: "no-cache" });
        if (ovResp.ok) {
          const ov = await ovResp.json();
          feed.days.forEach((day) => {
            day.items = day.items.filter((i) => !ov[i.id]?.hidden);
            day.items.forEach((i) => {
              if (ov[i.id]) {
                i.pinned = !!ov[i.id].pinned;
                i.tags = ov[i.id].tags || i.tags;
              }
            });
          });
        }
      }
    } catch { /* best-effort only */ }

    state.feed = feed;
    const updated = document.getElementById("updated-at");
    updated.textContent = `Updated ${relTime(feed.generated_at)}`;
    updated.title = feed.generated_at;
    showStatus(feed);
    render();
  }

  boot();
})();
