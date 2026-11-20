/* Little KB 前端：原生 JS，无构建步骤 */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  /* 与星图配色一致的分类色板 */
  const CAT_HUES = [
    "#a78bfa", "#60a5fa", "#34d399", "#f472b6",
    "#fbbf24", "#38bdf8", "#c084fc", "#4ade80",
    "#fb923c", "#e879f9", "#22d3ee", "#a3e635",
  ];
  const el = (tag, cls, html) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (html !== undefined) node.innerHTML = html;
    return node;
  };

  const state = {
    groups: [],
    activeCat: null,      // null = 全部；"" = 未分类；其它为分类名
    mode: "browse",       // browse | search
    hits: [],
    terms: [],
    currentDoc: null,
    query: "",
    searchTimer: 0,
    requestSeq: 0,
    view: "graph",        // doc | graph（默认首屏为星图）
    page: "home",         // home | list | doc
    lastPage: "home",     // 文档页的返回目标
    graphLoaded: false,
  };

  /* ------------------------------------------------------------------ 工具 */

  function escapeHtml(text) {
    return String(text ?? "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function escapeRe(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function humanSize(bytes) {
    const n = Number(bytes) || 0;
    if (n < 1024) return n + " B";
    const units = ["KB", "MB", "GB", "TB"];
    let value = n / 1024;
    let i = 0;
    while (value >= 1024 && i < units.length - 1) { value /= 1024; i += 1; }
    return value.toFixed(1) + " " + units[i];
  }

  /** 清理检索片段中的 Markdown 表格残留符号，避免出现一长串竖线 */
  function cleanSnippet(html) {
    return String(html || "")
      .split(/\n+/)
      .map((line) => line.trim())
      .filter((line) => line && !/^[|\s:\-—]+$/.test(line))
      .join(" ")
      .replace(/\|/g, " ")
      .replace(/\s{2,}/g, " ")
      .trim();
  }

  function relTime(stamp) {
    if (!stamp) return "";
    const date = new Date(stamp.replace(" ", "T"));
    if (Number.isNaN(date.getTime())) return stamp;
    const diff = (Date.now() - date.getTime()) / 1000;
    if (diff < 60) return "刚刚";
    if (diff < 3600) return Math.floor(diff / 60) + " 分钟前";
    if (diff < 86400) return Math.floor(diff / 3600) + " 小时前";
    if (diff < 86400 * 30) return Math.floor(diff / 86400) + " 天前";
    return stamp.slice(0, 10);
  }

  function toast(message, kind = "") {
    const node = el("div", "toast " + kind, escapeHtml(message));
    $("#toasts").appendChild(node);
    setTimeout(() => {
      node.style.opacity = "0";
      node.style.transition = "opacity .25s";
      setTimeout(() => node.remove(), 260);
    }, 3200);
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    const type = res.headers.get("content-type") || "";
    const payload = type.includes("application/json") ? await res.json() : await res.text();
    if (!res.ok) {
      const message = (payload && payload.error) || "请求失败：" + res.status;
      throw new Error(message);
    }
    return payload;
  }

  /* -------------------------------------------------------------- Markdown */

  function inline(text) {
    let out = escapeHtml(text);
    const codes = [];
    out = out.replace(/`([^`]+)`/g, (_m, code) => {
      codes.push("<code>" + code + "</code>");
      return "\u0000" + (codes.length - 1) + "\u0000";
    });
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    out = out.replace(/(^|[^_\w])_([^_\n]+)_/g, "$1<em>$2</em>");
    out = out.replace(
      /\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noreferrer noopener">$1</a>'
    );
    out = out.replace(
      /(^|[\s(])(https?:\/\/[^\s<)]+)/g,
      '$1<a href="$2" target="_blank" rel="noreferrer noopener">$2</a>'
    );
    out = out.replace(/\u0000(\d+)\u0000/g, (_m, i) => codes[Number(i)]);
    return out;
  }

  function isTableSep(line) {
    return /^\s*\|?[\s:|-]*-[\s:|-]*\|[\s:|-]*$/.test(line) && line.includes("-");
  }

  function splitRow(line) {
    return line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => c.trim());
  }

  function buildList(items, i, indent) {
    const ordered = items[i].ordered;
    let html = ordered ? "<ol>" : "<ul>";
    while (i < items.length && items[i].indent >= indent) {
      const item = items[i];
      if (item.indent > indent) {
        const nested = buildList(items, i, item.indent);
        html += nested.html;
        i = nested.i;
        continue;
      }
      html += "<li>" + inline(item.text);
      i += 1;
      if (i < items.length && items[i].indent > indent) {
        const nested = buildList(items, i, items[i].indent);
        html += nested.html;
        i = nested.i;
      }
      html += "</li>";
    }
    html += ordered ? "</ol>" : "</ul>";
    return { html, i };
  }

  function renderMarkdown(source) {
    const lines = String(source || "").replace(/\r\n?/g, "\n").split("\n");
    const out = [];
    let para = [];
    let i = 0;

    const flush = () => {
      if (para.length) {
        out.push("<p>" + inline(para.join(" ")) + "</p>");
        para = [];
      }
    };

    while (i < lines.length) {
      const line = lines[i];

      if (/^\s*(```|~~~)/.test(line)) {
        flush();
        const fence = line.trim().slice(0, 3);
        const lang = line.trim().slice(3).trim();
        const buffer = [];
        i += 1;
        while (i < lines.length && !lines[i].trim().startsWith(fence)) {
          buffer.push(lines[i]);
          i += 1;
        }
        i += 1;
        const cls = lang ? ' class="language-' + escapeHtml(lang) + '"' : "";
        out.push("<pre><code" + cls + ">" + escapeHtml(buffer.join("\n")) + "</code></pre>");
        continue;
      }

      if (/^\s*$/.test(line)) { flush(); i += 1; continue; }

      const heading = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
      if (heading) {
        flush();
        const level = heading[1].length;
        out.push("<h" + level + ">" + inline(heading[2]) + "</h" + level + ">");
        i += 1;
        continue;
      }

      if (/^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
        flush();
        out.push("<hr />");
        i += 1;
        continue;
      }

      if (/^\s*>/.test(line)) {
        flush();
        const quote = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) {
          quote.push(lines[i].replace(/^\s*>\s?/, ""));
          i += 1;
        }
        out.push("<blockquote>" + inline(quote.join(" ")) + "</blockquote>");
        continue;
      }

      if (line.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
        flush();
        const head = splitRow(line);
        i += 2;
        const body = [];
        while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") {
          body.push(splitRow(lines[i]));
          i += 1;
        }
        let table = "<table><thead><tr>" +
          head.map((c) => "<th>" + inline(c) + "</th>").join("") +
          "</tr></thead><tbody>";
        body.forEach((row) => {
          table += "<tr>" + row.map((c) => "<td>" + inline(c) + "</td>").join("") + "</tr>";
        });
        out.push(table + "</tbody></table>");
        continue;
      }

      const listMatch = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(line);
      if (listMatch) {
        flush();
        const items = [];
        while (i < lines.length) {
          const m = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(lines[i]);
          if (!m) break;
          items.push({
            indent: Math.floor(m[1].replace(/\t/g, "  ").length / 2),
            ordered: /\d/.test(m[2]),
            text: m[3],
          });
          i += 1;
        }
        out.push(buildList(items, 0, items[0].indent).html);
        continue;
      }

      para.push(line.trim());
      i += 1;
    }
    flush();
    return out.join("\n");
  }

  function highlightHtml(html, terms) {
    const list = (terms || []).filter((t) => t && t.length > 0);
    if (!list.length) return html;
    const pattern = new RegExp(
      "(" + list.slice().sort((a, b) => b.length - a.length).map(escapeRe).join("|") + ")",
      "gi"
    );
    return html
      .split(/(<[^>]+>)/)
      .map((segment) => (segment.startsWith("<") ? segment : segment.replace(pattern, "<mark>$1</mark>")))
      .join("");
  }

  /* ------------------------------------------------------------------ 侧栏 */

  function renderStats(stats) {
    const box = $("#stats");
    box.innerHTML = "";
    const items = [
      [String(stats.documents ?? 0), "文档"],
      [String(stats.chunks ?? 0), "检索切片"],
      [humanSize(stats.bytes ?? 0), "占用"],
    ];
    items.forEach(([value, label]) => {
      const node = el("div", "stat");
      node.appendChild(el("b", "", escapeHtml(value)));
      node.appendChild(el("span", "", escapeHtml(label)));
      box.appendChild(node);
    });
  }

  function renderCats() {
    const box = $("#cats");
    box.innerHTML = "";
    const total = state.groups.reduce((sum, g) => sum + g.count, 0);
    $("#cats-meta").textContent = state.groups.length
      ? state.groups.length + " 个分类 · 共 " + total + " 篇"
      : "";

    state.groups.forEach((group, index) => {
      const card = el("button", "cat-card");
      const hue = CAT_HUES[index % CAT_HUES.length];
      card.innerHTML =
        '<span class="cat-dot" style="background:' + hue + ';box-shadow:0 0 10px ' + hue + '66"></span>' +
        '<span class="cat-name">' + escapeHtml(group.name) + "</span>" +
        '<span class="cat-count">' + group.count + "<i>篇</i></span>" +
        '<span class="cat-arrow" aria-hidden="true">→</span>';
      card.title = group.key ? "打开分类：" + group.key : "根目录下的文件";
      card.onclick = () => openCategory(group.key);
      box.appendChild(card);
    });

    if (!state.groups.length) {
      box.innerHTML = '<div class="empty-hint">还没有分类，上传文件后会自动出现。</div>';
    }

    const options = $("#cat-options");
    options.innerHTML = "";
    state.groups.forEach((group) => {
      if (!group.key) return;
      const opt = document.createElement("option");
      opt.value = group.key;
      options.appendChild(opt);
    });
  }

  function allDocs() {
    return state.groups.flatMap((g) => g.docs || []);
  }

  function renderRecent() {
    const list = $("#recent-list");
    list.innerHTML = "";
    const docs = allDocs()
      .slice()
      .sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")))
      .slice(0, 6);
    $("#recent-meta").textContent = docs.length ? "最近 " + docs.length + " 篇" : "";
    if (!docs.length) {
      list.innerHTML = '<li class="empty-hint">还没有文件，点右上角“上传”开始。</li>';
      return;
    }
    docs.forEach((doc) => list.appendChild(docItem(doc, true)));
  }

  function visibleDocs() {
    if (state.activeCat === null) return state.groups.flatMap((g) => g.docs);
    const group = state.groups.find((g) => g.key === state.activeCat);
    return group ? group.docs : [];
  }

  function docItem(doc, compact) {
    const li = el("li", "doc-item");
    if (state.currentDoc && state.currentDoc.id === doc.id) li.classList.add("active");
    const row = el("div", "row");
    row.appendChild(el("span", "title", escapeHtml(doc.title)));
    if (compact && doc.path && doc.path.includes("/")) {
      row.appendChild(el("span", "badge", escapeHtml(doc.path.split("/")[0])));
    }
    row.appendChild(el("span", "ext", escapeHtml((doc.ext || "txt").replace(".", "") || "txt")));
    li.appendChild(row);
    const meta = el("div", "meta");
    meta.innerHTML =
      "<span>" + escapeHtml(humanSize(doc.size)) + "</span>" +
      "<span>" + escapeHtml(relTime(doc.updated_at)) + "</span>";
    li.appendChild(meta);
    li.onclick = () => openDoc(doc.id);
    return li;
  }

  function showPage(page) {
    state.page = page;
    $("#page-home").classList.toggle("hidden", page !== "home");
    $("#page-list").classList.toggle("hidden", page !== "list");
    $("#doc").classList.toggle("hidden", page !== "doc");
    $("#view-doc").scrollTop = 0;
  }

  function goHome() {
    state.activeCat = null;
    state.mode = "browse";
    state.hits = [];
    state.currentDoc = null;
    state.query = "";
    $("#search").value = "";
    $("#search-clear").classList.add("hidden");
    showPage("home");
    history.replaceState(null, "", "#home");
    document.title = "Little KB · 我的知识库";
    document.querySelectorAll(".doc-item").forEach((node) => node.classList.remove("active"));
  }

  /** 进入分类列表页；传 null 表示"全部文档" */
  function openCategory(cat) {
    state.activeCat = cat;
    state.mode = "browse";
    state.hits = [];
    state.currentDoc = null;
    $("#search").value = "";
    $("#search-clear").classList.add("hidden");
    renderList();
    showPage("list");
    const name = cat === null ? "全部文档" : (cat || "未分类");
    history.replaceState(null, "", "#cat-" + encodeURIComponent(cat === null ? "__all__" : cat));
    document.title = name + " · Little KB";
  }

  function renderList() {
    const list = $("#list");
    list.innerHTML = "";
    const empty = $("#list-empty");
    empty.classList.add("hidden");

    if (state.mode === "search") {
      $("#list-title").textContent = "搜索「" + state.query + "」";
      $("#list-meta").textContent = state.hits.length ? state.hits.length + " 条结果" : "0 条结果";
      if (!state.hits.length) {
        empty.textContent = "没有命中，试试更短的关键词或单个词。";
        empty.classList.remove("hidden");
        return;
      }
      state.hits.forEach((hit) => {
        const li = el("li", "doc-item");
        if (state.currentDoc && state.currentDoc.id === hit.id) li.classList.add("active");
        const row = el("div", "row");
        row.appendChild(el("span", "title", escapeHtml(hit.title)));
        if (hit.category) row.appendChild(el("span", "badge", escapeHtml(hit.category)));
        li.appendChild(row);
        const snippet = el("div", "snippet", cleanSnippet(hit.snippet));
        li.appendChild(snippet);
        li.onclick = () => openDoc(hit.id);
        list.appendChild(li);
      });
      return;
    }

    const docs = visibleDocs();
    const label = state.activeCat === null ? "全部文档" : (state.activeCat || "未分类");
    $("#list-title").textContent = label;
    $("#list-meta").textContent = docs.length ? docs.length + " 篇" : "";
    if (!docs.length) {
      empty.textContent = "这里还没有文件，点右上角“上传”或直接把文件放进 kb 文件夹后重建索引。";
      empty.classList.remove("hidden");
      return;
    }
    docs.forEach((doc) => list.appendChild(docItem(doc)));
  }

  async function loadStats() {
    try {
      renderStats(await api("/api/stats"));
    } catch (err) {
      toast(err.message, "error");
    }
  }

  async function loadTree() {
    try {
      const data = await api("/api/tree");
      state.groups = data.groups || [];
      renderCats();
      renderRecent();
      if (state.page === "list") renderList();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  /* ------------------------------------------------------------------ 检索 */

  async function runSearch(query) {
    state.query = query;
    state.terms = [];
    if (!query) {
      state.mode = "browse";
      state.hits = [];
      $("#search-clear").classList.add("hidden");
      if (state.page === "list") goHome();
      else renderList();
      return;
    }
    $("#search-clear").classList.remove("hidden");
    const seq = ++state.requestSeq;
    const params = new URLSearchParams({ q: query, limit: "30" });
    try {
      const data = await api("/api/search?" + params.toString());
      if (seq !== state.requestSeq) return;
      state.mode = "search";
      state.hits = data.hits || [];
      state.terms = data.terms || [];
      renderList();
      showPage("list");
      history.replaceState(null, "", "#search-" + encodeURIComponent(query));
      document.title = "搜索「" + query + "」 · Little KB";
      if (window.KBGraph && state.graphLoaded) {
        window.KBGraph.setHighlight(state.hits.map((h) => h.id));
      }
    } catch (err) {
      if (seq === state.requestSeq) toast(err.message, "error");
    }
  }

  /* ------------------------------------------------------------------ 图谱 */

  function docHash() {
    if (state.page === "doc" && state.currentDoc) return "#doc-" + state.currentDoc.id;
    if (state.page === "list") {
      return state.mode === "search"
        ? "#search-" + encodeURIComponent(state.query)
        : "#cat-" + encodeURIComponent(state.activeCat === null ? "__all__" : state.activeCat);
    }
    return "#home";
  }

  function switchView(view) {
    state.view = view;
    $("#view-doc").classList.toggle("hidden", view !== "doc");
    $("#view-graph").classList.toggle("hidden", view !== "graph");
    $("#tab-doc").classList.toggle("active", view === "doc");
    $("#tab-graph").classList.toggle("active", view === "graph");
    if (view === "graph") {
      ensureGraph();
      history.replaceState(null, "", "#graph");
    } else {
      history.replaceState(null, "", docHash());
    }
  }

  async function ensureGraph(force = false) {
    if (!window.KBGraph) return;
    window.KBGraph.resize();
    if (state.graphLoaded && !force) {
      window.KBGraph.setHighlight(state.mode === "search" ? state.hits.map((h) => h.id) : []);
      window.KBGraph.draw();
      return;
    }
    try {
      const data = await api("/api/graph?docs=300&terms=6");
      const info = window.KBGraph.load(data);
      state.graphLoaded = true;
      $("#graph-count").textContent = info.nodes
        ? info.nodes + " 个节点 · " + info.edges + " 条连接"
        : "";
      $("#graph-empty").classList.toggle("hidden", info.nodes > 0);
      window.KBGraph.resize();
      window.KBGraph.fit();
      window.KBGraph.setHighlight(state.mode === "search" ? state.hits.map((h) => h.id) : []);
    } catch (err) {
      toast(err.message, "error");
    }
  }

  function invalidateGraph() {
    state.graphLoaded = false;
    $("#graph-count").textContent = "";
    if (state.view === "graph") ensureGraph(true);
  }

  function initGraph() {
    if (!window.KBGraph) return;
    const canvas = $("#graph-canvas");
    const host = $("#view-graph");
    if (!canvas || !host) return;
    window.KBGraph.init(canvas, host, {
      openDoc: (id) => { switchView("doc"); openDoc(id); },
      searchTerm: (term) => {
        if (!term) return;
        switchView("doc");
        $("#search").value = term;
        $("#search").focus();
        runSearch(term);
      },
    });

    $("#g-reheat").onclick = () => window.KBGraph.reheat();
    $("#g-fit").onclick = () => window.KBGraph.fit();
    $("#g-labels").onclick = (event) => {
      const off = event.currentTarget.classList.toggle("off");
      window.KBGraph.setLabels(!off);
    };
    [["g-type-doc", "doc"], ["g-type-term", "term"], ["g-type-tag", "tag"], ["g-type-category", "category"]]
      .forEach(([id, type]) => {
        const box = document.getElementById(id);
        if (box) box.onchange = () => window.KBGraph.setFilter(type, box.checked);
      });
  }

  /* ------------------------------------------------------------------ 阅读 */

  function stripTitleHeading(content, title) {
    const lines = String(content || "").split("\n");
    const first = /^\s{0,3}#\s+(.*?)\s*#*\s*$/.exec(lines[0] || "");
    if (first && first[1].trim() === String(title || "").trim()) {
      return lines.slice(1).join("\n").replace(/^\n+/, "");
    }
    return content;
  }

  function renderDoc(doc) {
    showPage("doc");
    const article = $("#doc");
    article.classList.remove("hidden");
    const tags = (doc.tags || []).map((t) => '<span class="tag">' + escapeHtml(t) + "</span>").join("");
    const meta = [
      escapeHtml(doc.path),
      escapeHtml(humanSize(doc.size)),
      escapeHtml(relTime(doc.updated_at)),
      (doc.chunks ? doc.chunks.length : 0) + " 个切片",
      escapeHtml(doc.status === "text" ? "正文已索引" : "仅文件名索引"),
    ].join(" <span class='dot'>·</span> ");

    const bodyHtml = highlightHtml(renderMarkdown(stripTitleHeading(doc.content, doc.title)), state.terms);

    article.innerHTML =
      '<button class="back-btn doc-back" id="btn-back-doc">' +
        '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>' +
        "返回" +
      "</button>" +
      '<div class="doc-head">' +
        "<h1>" + escapeHtml(doc.title) + "</h1>" +
        '<div class="doc-meta">' + meta + "</div>" +
        (tags ? '<div class="doc-meta" style="margin-top:8px">' + tags + "</div>" : "") +
        '<div class="doc-actions">' +
          '<a class="btn" href="/api/doc/' + doc.id + '/raw" target="_blank" rel="noreferrer">下载原文件</a>' +
          '<button class="btn" id="btn-tags">编辑标签</button>' +
          '<button class="btn" id="btn-title">重命名标题</button>' +
          '<button class="btn btn-danger" id="btn-delete">删除</button>' +
        "</div>" +
      "</div>" +
      '<div class="doc-body">' + (doc.truncated ? '<p class="muted">（内容过长，仅显示前 40 万字符）</p>' : "") +
      (bodyHtml || '<p class="muted">这个文件没有可提取的文本。</p>') + "</div>";

    $("#btn-tags").onclick = async () => {
      const input = window.prompt("标签（逗号分隔）：", (doc.tags || []).join(","));
      if (input === null) return;
      try {
        const data = await api("/api/doc/" + doc.id, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tags: input }),
        });
        state.currentDoc = data.doc;
        renderDoc(data.doc);
        toast("标签已保存", "ok");
        await loadTree();
      } catch (err) { toast(err.message, "error"); }
    };

    $("#btn-title").onclick = async () => {
      const input = window.prompt("文档标题：", doc.title);
      if (input === null || !input.trim()) return;
      try {
        const data = await api("/api/doc/" + doc.id, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: input }),
        });
        state.currentDoc = data.doc;
        renderDoc(data.doc);
        document.title = data.doc.title + " · Little KB";
        toast("标题已更新", "ok");
        await loadTree();
      } catch (err) { toast(err.message, "error"); }
    };

    $("#btn-delete").onclick = async () => {
      if (!window.confirm("删除「" + doc.title + "」？文件会从知识库文件夹中一并移除。")) return;
      try {
        await api("/api/doc/" + doc.id, { method: "DELETE" });
        toast("已删除", "ok");
        state.currentDoc = null;
        goHome();
        await loadTree();
        await loadStats();
        invalidateGraph();
        if (state.mode === "search") runSearch(state.query);
      } catch (err) { toast(err.message, "error"); }
    };

    $("#btn-back-doc").onclick = () => {
      const target = state.lastPage === "doc" ? "home" : state.lastPage;
      showPage(target);
      if (target === "list") {
        const hash = state.mode === "search"
          ? "#search-" + encodeURIComponent(state.query)
          : "#cat-" + encodeURIComponent(state.activeCat === null ? "__all__" : state.activeCat);
        history.replaceState(null, "", hash);
      } else {
        history.replaceState(null, "", "#home");
        document.title = "Little KB · 我的知识库";
      }
    };

    const mark = article.querySelector("mark");
    if (mark) mark.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  async function openDoc(id) {
    try {
      const doc = await api("/api/doc/" + id);
      if (state.view !== "doc") switchView("doc");
      if (state.page !== "doc") state.lastPage = state.page;
      state.currentDoc = doc;
      renderDoc(doc);
      document.title = doc.title + " · Little KB";
      history.replaceState(null, "", "#doc-" + id);
      document.querySelectorAll(".doc-item").forEach((node) => node.classList.remove("active"));
      renderList();
      if (state.mode === "search") renderList();
      $("#view-doc").scrollTop = 0;
    } catch (err) {
      toast(err.message, "error");
    }
  }

  /* ------------------------------------------------------------------ 上传 */

  let pendingFiles = [];

  function renderPendingFiles() {
    const list = $("#file-list");
    list.innerHTML = "";
    pendingFiles.forEach((file, index) => {
      const li = el("li");
      li.innerHTML =
        '<span class="name">' + escapeHtml(file.name) + "</span>" +
        '<span class="size">' + escapeHtml(humanSize(file.size)) + "</span>";
      const remove = el("button", "icon-btn", "✕");
      remove.title = "移除";
      remove.onclick = () => {
        pendingFiles.splice(index, 1);
        renderPendingFiles();
      };
      li.appendChild(remove);
      list.appendChild(li);
    });
    $("#upload-submit").disabled = pendingFiles.length === 0;
    $("#upload-status").textContent = pendingFiles.length
      ? "已选择 " + pendingFiles.length + " 个文件"
      : "";
  }

  function openModal() {
    $("#modal").classList.remove("hidden");
    $("#f-category").value = state.activeCat && state.activeCat !== "" ? state.activeCat : "";
    $("#f-tags").value = "";
    pendingFiles = [];
    renderPendingFiles();
    setTimeout(() => $("#dropzone").focus(), 30);
  }

  function closeModal() {
    $("#modal").classList.add("hidden");
  }

  async function submitUpload() {
    if (!pendingFiles.length) return;
    const form = new FormData();
    pendingFiles.forEach((file) => form.append("files", file, file.name));
    form.append("category", $("#f-category").value.trim());
    form.append("tags", $("#f-tags").value.trim());
    const button = $("#upload-submit");
    button.disabled = true;
    $("#upload-status").textContent = "上传并建立索引中…";
    try {
      const data = await api("/api/upload", { method: "POST", body: form });
      const added = data.added || [];
      if (data.errors && data.errors.length) {
        toast("部分文件失败：" + data.errors.map((e) => e.file + " " + e.error).join("；"), "warn");
      }
      toast("已上传 " + added.length + " 个文件并建立索引", "ok");
      closeModal();
      await loadTree();
      await loadStats();
      invalidateGraph();
      if (added.length && added[0].id) openDoc(added[0].id);
    } catch (err) {
      toast(err.message, "error");
    } finally {
      button.disabled = pendingFiles.length === 0;
      $("#upload-status").textContent = "";
    }
  }

  function wireModal() {
    const dropzone = $("#dropzone");
    const input = $("#file-input");

    const addFiles = (fileList) => {
      Array.from(fileList).forEach((file) => {
        if (!pendingFiles.some((f) => f.name === file.name && f.size === file.size)) {
          pendingFiles.push(file);
        }
      });
      renderPendingFiles();
    };

    dropzone.onclick = (event) => {
      if (event.target === input) return;   // 避免 input.click() 冒泡回来形成递归
      input.click();
    };
    dropzone.onkeydown = (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); input.click(); }
    };
    input.addEventListener("click", (event) => event.stopPropagation());
    input.onchange = () => { addFiles(input.files); input.value = ""; };
    ["dragenter", "dragover"].forEach((type) => {
      dropzone.addEventListener(type, (event) => {
        event.preventDefault();
        dropzone.classList.add("drag");
      });
    });
    ["dragleave", "drop"].forEach((type) => {
      dropzone.addEventListener(type, (event) => {
        event.preventDefault();
        dropzone.classList.remove("drag");
        if (type === "drop" && event.dataTransfer) addFiles(event.dataTransfer.files);
      });
    });
    $("#upload-submit").onclick = submitUpload;
    $("#upload-cancel").onclick = closeModal;
    $("#modal-close").onclick = closeModal;
    $("#modal").addEventListener("mousedown", (event) => {
      if (event.target === $("#modal")) closeModal();
    });
  }

  /* ------------------------------------------------------------------ 主题 */

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("kb-theme", theme);
  }

  /* ------------------------------------------------------------------ 启动 */

  async function reindex() {
    const button = $("#btn-reindex");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "索引中…";
    try {
      const data = await api("/api/reindex", { method: "POST" });
      const r = data.result || {};
      toast(
        "扫描 " + (r.scanned || 0) + " 个文件：新增 " + (r.created || 0) +
        "，更新 " + (r.updated || 0) + "，移除 " + (r.removed || 0) + " · " + (r.took_ms || 0) + " ms",
        "ok"
      );
      await loadTree();
      await loadStats();
      invalidateGraph();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function wireEvents() {
    const search = $("#search");
    search.addEventListener("input", () => {
      window.clearTimeout(state.searchTimer);
      state.searchTimer = window.setTimeout(() => runSearch(search.value.trim()), 170);
    });
    search.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        search.value = "";
        runSearch("");
        search.blur();
      }
    });
    $("#search-clear").onclick = () => {
      search.value = "";
      runSearch("");
      search.focus();
    };

    $("#btn-upload").onclick = openModal;
    $("#btn-upload-2").onclick = openModal;
    $("#btn-reindex").onclick = reindex;
    $("#tab-doc").onclick = () => switchView("doc");
    $("#tab-graph").onclick = () => switchView("graph");
    const gotoGraph = $("#btn-goto-graph");
    if (gotoGraph) gotoGraph.onclick = () => switchView("graph");
    const back = $("#btn-back");
    if (back) back.onclick = () => goHome();
    const viewAll = $("#btn-view-all");
    if (viewAll) viewAll.onclick = () => openCategory(null);
    $("#btn-theme").onclick = () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      applyTheme(next);
    };

    document.addEventListener("keydown", (event) => {
      const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName);
      if (event.key === "/" && !typing) {
        event.preventDefault();
        search.focus();
      }
      if (event.key === "Escape" && !$("#modal").classList.contains("hidden")) closeModal();
    });
  }

  async function boot() {
    const forcedTheme = new URLSearchParams(location.search).get("theme");
    applyTheme(forcedTheme === "light" || forcedTheme === "dark"
      ? forcedTheme
      : (localStorage.getItem("kb-theme") || "dark"));
    wireEvents();
    wireModal();
    initGraph();
    try {
      const config = await api("/api/config");
      $("#kb-path").textContent = config.kb_dir;
      $("#max-size").textContent = String(config.max_upload_mb);
    } catch (_) { /* 非致命 */ }
    await loadTree();
    await loadStats();
    const initialQuery = new URLSearchParams(location.search).get("q");
    if (initialQuery) {
      $("#search").value = initialQuery;
      await runSearch(initialQuery.trim());
    }
    if (new URLSearchParams(location.search).get("upload") === "1") openModal();
    if (!location.hash || location.hash === "#graph") {
      switchView("graph");
    } else {
      const docMatch = /^#doc-(\d+)$/.exec(location.hash);
      const catMatch = /^#cat-(.*)$/.exec(location.hash);
      const searchMatch = /^#search-(.*)$/.exec(location.hash);
      if (docMatch) {
        switchView("doc");
        openDoc(Number(docMatch[1]));
      } else if (catMatch) {
        switchView("doc");
        const raw = decodeURIComponent(catMatch[1]);
        openCategory(raw === "__all__" ? null : raw);
      } else if (searchMatch) {
        switchView("doc");
        const q = decodeURIComponent(searchMatch[1]);
        $("#search").value = q;
        await runSearch(q);
      } else if (location.hash === "#home") {
        switchView("doc");
        showPage("home");
      } else {
        switchView("graph");
      }
    }
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
