/* 知识星图：星团式布局 + 呼吸漂移 + 发光精灵，无任何外部依赖 */
window.KBGraph = (function () {
  "use strict";

  const COLORS = {
    category: "#c4b5fd",
    doc: "#7aa2f7",
    tag: "#5eead4",
    term: "#f5c26b",
  };
  const TYPE_NAME = { doc: "文档", term: "关键词", tag: "标签", category: "分类" };
  const BASE_R = { category: 11, doc: 6.2, tag: 4, term: 2.6 };
  const GOLD = Math.PI * (3 - Math.sqrt(5));

  let canvas = null;
  let ctx = null;
  let host = null;
  let dpr = 1;
  let W = 0;
  let H = 0;

  let nodes = [];
  let edges = [];
  let index = new Map();
  let stars = [];
  let sprites = new Map();

  let scale = 1;
  let tx = 0;
  let ty = 0;
  let alpha = 0;
  let active = false;
  let startedAt = 0;
  let clock = 0;

  let hover = null;
  let dragNode = null;
  let panning = false;
  let moved = false;
  let pointer = { x: 0, y: 0 };

  let showLabels = true;
  let filters = { doc: true, term: false, tag: true, category: true };
  let highlight = new Set();
  let pendingFit = false;
  let layout = { termX: 300 };

  let hooks = { openDoc: () => {}, searchTerm: () => {} };

  /* ------------------------------------------------------------ 初始化 */

  function init(canvasEl, hostEl, callbacks) {
    canvas = canvasEl;
    host = hostEl;
    ctx = canvas.getContext("2d");
    hooks = Object.assign(hooks, callbacks || {});
    resize();
    bindEvents();
    if (window.ResizeObserver) {
      new ResizeObserver(() => resize()).observe(host);
    } else {
      window.addEventListener("resize", resize);
    }
    return api;
  }

  function resize() {
    if (!canvas || !host) return;
    const rect = host.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = rect.width;
    H = rect.height;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    makeStars();
    if (nodes.length) {
      layoutClusters();
      nodes.forEach((n) => {
        if (n.type === "category" || n.type === "doc") {
          n.x = n.bx;
          n.y = n.by;
        }
      });
      alpha = Math.max(alpha, 0.4);
      kick(0.5);
    }
    draw();
  }

  function makeStars() {
    stars = [];
    const count = Math.round((W * H) / 20000);
    for (let i = 0; i < count; i += 1) {
      stars.push({
        x: Math.random() * W,
        y: Math.random() * H,
        r: Math.random() * 1.1 + 0.25,
        a: Math.random() * 0.32 + 0.06,
        p: Math.random() * Math.PI * 2,
      });
    }
  }

  function bindEvents() {
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("pointerdown", onDown);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointerleave", () => {
      if (!dragNode) {
        hover = null;
        hideTip();
      }
    });
    canvas.addEventListener("dblclick", () => fit());
  }

  /* ------------------------------------------------------------ 发光精灵 */

  function sprite(color) {
    if (sprites.has(color)) return sprites.get(color);
    const size = 96;
    const c = document.createElement("canvas");
    c.width = size;
    c.height = size;
    const g = c.getContext("2d");
    const r = size / 2;
    const grad = g.createRadialGradient(r, r, 0, r, r, r);
    grad.addColorStop(0, color);
    grad.addColorStop(0.22, color);
    grad.addColorStop(0.4, hexA(color, 0.4));
    grad.addColorStop(1, hexA(color, 0));
    g.fillStyle = grad;
    g.beginPath();
    g.arc(r, r, r, 0, Math.PI * 2);
    g.fill();
    sprites.set(color, c);
    return c;
  }

  function hexA(hex, a) {
    const v = hex.replace("#", "");
    const n = parseInt(v.length === 3 ? v.replace(/(.)/g, "$1$1") : v, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }

  /* ------------------------------------------------------------ 数据 */

  function load(data) {
    nodes = [];
    edges = [];
    index = new Map();
    const now = Math.random() * 100;

    (data.nodes || []).forEach((raw, i) => {
      const node = {
        id: raw.id,
        type: raw.type,
        label: raw.label || raw.id,
        weight: raw.weight || 1,
        docId: raw.doc_id || null,
        category: raw.category || "",
        degree: 0,
        r: 0,
        phase: now + i * 0.7,
        vx: 0,
        vy: 0,
      };
      nodes.push(node);
      index.set(node.id, node);
    });

    (data.edges || []).forEach((raw) => {
      const a = index.get(raw.source);
      const b = index.get(raw.target);
      if (!a || !b) return;
      a.degree += 1;
      b.degree += 1;
      edges.push({ a, b, type: raw.type, weight: raw.weight || 1 });
    });

    nodes.forEach((node) => { node.r = radiusOf(node); });

    layoutClusters();
    nodes.forEach((node) => {
      node.x = node.bx;
      node.y = node.by;
    });
    startedAt = performance.now();
    alpha = 1;
    pendingFit = true;
    kick(1);
    return { nodes: nodes.length, edges: edges.length };
  }

  function radiusOf(node) {
    const base = BASE_R[node.type] || 3;
    if (node.type === "doc") return base + Math.min(5.5, Math.log10((Number(node.weight) || 0) + 10) * 1.6);
    if (node.type === "category") return base + Math.min(5, (node.weight || 1) * 1.1);
    if (node.type === "tag") return base + Math.min(1.6, (node.weight || 1) * 0.22);
    return base;
  }

  /* ------------------------------------------------------------ 星团布局 */

  function layoutClusters() {
    const cats = nodes
      .filter((n) => n.type === "category")
      .sort((a, b) => (b.weight || 1) - (a.weight || 1));

    const byCat = new Map();
    cats.forEach((c) => byCat.set(c.id, []));
    nodes.forEach((n) => {
      if (n.type !== "doc") return;
      const key = "cat:" + (n.category || "");
      if (byCat.has(key)) byCat.get(key).push(n);
    });

    const totalDocs = Math.max(1, nodes.filter((n) => n.type === "doc").length);
    const bandTotal = H * 0.8;
    const catX = -Math.min(W * 0.32, 430);
    const docOffset = Math.min(240, Math.max(170, W * 0.16));

    let cursor = -bandTotal / 2;
    let maxRight = catX + docOffset;

    cats.forEach((cat, ci) => {
      const docs = (byCat.get(cat.id) || []).sort((a, b) => (b.weight || 1) - (a.weight || 1));
      const k = docs.length;
      const band = Math.max(110, bandTotal * (k / totalDocs));
      const cy = cursor + band / 2;
      cat.bx = catX + Math.sin(ci * 1.7) * 16;
      cat.by = cy;

      const cx = catX + docOffset;
      const spacing = k <= 6 ? 40 : k <= 20 ? 34 : 30;
      docs.forEach((doc, j) => {
        const angle = j * GOLD + ci * 0.9;
        const rad = spacing * Math.sqrt(j + 0.6);
        const wobble = 1 + Math.sin(j * 1.3 + ci) * 0.12;
        doc.bx = cx + Math.cos(angle) * rad * 1.15 * wobble;
        doc.by = cy + Math.sin(angle) * rad * 0.82;
        maxRight = Math.max(maxRight, doc.bx);
      });

      // 关键词/标签先挂在文档附近，运行时会自己散开
      cursor += band;
    });

    nodes.forEach((node) => {
      if (node.bx !== undefined) return;
      const linked = edges.filter((e) => e.a === node || e.b === node);
      const base = linked.length ? (linked[0].a === node ? linked[0].b : linked[0].a) : null;
      node.bx = (base ? base.bx || 0 : maxRight) + 90 + Math.random() * 60;
      node.by = (base ? base.by || 0 : 0) + (Math.random() - 0.5) * 50;
    });

    layout.termX = maxRight + 120;
  }

  /* ------------------------------------------------------------ 漂移 */

  function drift(node) {
    const t = clock;
    const amp = node.type === "category" ? 3.2 : node.type === "term" ? 4 : 2.4;
    return {
      x: Math.sin(t * 0.42 + node.phase) * amp + Math.sin(t * 0.19 + node.phase * 1.7) * amp * 0.45,
      y: Math.cos(t * 0.36 + node.phase * 1.2) * amp + Math.cos(t * 0.23 + node.phase) * amp * 0.4,
    };
  }

  function px(node) {
    return node.x + drift(node).x;
  }

  function py(node) {
    return node.y + drift(node).y;
  }

  /* ------------------------------------------------------------ 物理（只作用于关键词/标签） */

  function step() {
    const a0 = alpha;
    const t = performance.now() / 1000;
    clock = t;

    // 关键词之间轻微排斥，避免叠成一团
    for (let i = 0; i < nodes.length; i += 1) {
      const a = nodes[i];
      if (a.type !== "term" && a.type !== "tag") continue;
      if (!filters[a.type]) continue;
      for (let j = i + 1; j < nodes.length; j += 1) {
        const b = nodes[j];
        if (!filters[b.type]) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const d2 = dx * dx + dy * dy;
        if (d2 > 40000 || d2 < 0.01) continue;
        const d = Math.sqrt(d2);
        const min = a.r + b.r + 10;
        if (d < min) {
          const push = ((min - d) / d) * 0.12 * a0;
          a.vx -= dx * push;
          a.vy -= dy * push;
          if (b.type === "term" || b.type === "tag") {
            b.vx += dx * push;
            b.vy += dy * push;
          }
        }
      }
    }

    edges.forEach((edge) => {
      const a = edge.a;
      const b = edge.b;
      const aMove = a.type === "term" || a.type === "tag";
      const bMove = b.type === "term" || b.type === "tag";
      if (!aMove && !bMove) return;
      if (!filters[a.type] || !filters[b.type]) return;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.hypot(dx, dy) || 1;
      const rest = edge.type === "tag" ? 80 : 62;
      const strength = ((dist - rest) / dist) * 0.03 * a0;
      const fx = dx * strength;
      const fy = dy * strength;
      if (aMove) { a.vx += fx; a.vy += fy; }
      if (bMove) { b.vx -= fx; b.vy -= fy; }
    });

    nodes.forEach((node) => {
      if (node.type !== "term" && node.type !== "tag") return;
      if (!filters[node.type] || node === dragNode) return;
      node.vx += (layout.termX - node.x) * 0.004 * a0;
      node.vy += (node.by - node.y) * 0.004 * a0;
      node.vx *= 0.88;
      node.vy *= 0.88;
      const speed = Math.hypot(node.vx, node.vy);
      if (speed > 6) {
        node.vx = (node.vx / speed) * 6;
        node.vy = (node.vy / speed) * 6;
      }
      node.x += node.vx;
      node.y += node.vy;
    });

    alpha *= 0.975;
    if (alpha < 0.002) alpha = 0;
  }

  function kick(value) {
    alpha = Math.max(alpha, value == null ? 0.55 : value);
    if (!active) loop();
  }

  function loop() {
    active = true;
    step();
    if (pendingFit && alpha < 0.02) {
      pendingFit = false;
      fit();
    }
    draw();
    if (alpha > 0.002 || dragNode || panning) {
      requestAnimationFrame(loop);
    } else {
      active = false;
      idleLoop();
    }
  }

  // 静止时也保持轻微呼吸感（低帧率重绘）
  let idleTimer = 0;
  function idleLoop() {
    if (idleTimer) return;
    idleTimer = window.setTimeout(() => {
      idleTimer = 0;
      if (!active) {
        clock = performance.now() / 1000;
        draw();
        idleLoop();
      }
    }, 120);
  }

  /* ------------------------------------------------------------ 绘制 */

  function visible(node) {
    return filters[node.type];
  }

  function dimmed(node) {
    if (!highlight.size) return false;
    if (node.type === "doc") return !highlight.has(node.docId);
    return true;
  }

  function roundRect(c, x, y, w, h, r) {
    if (c.roundRect) {
      c.beginPath();
      c.roundRect(x, y, w, h, r);
      return;
    }
    c.beginPath();
    c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r);
    c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r);
    c.arcTo(x, y, x + w, y, r);
    c.closePath();
  }

  function draw() {
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const bg = ctx.createRadialGradient(W * 0.5, H * 0.42, 40, W * 0.5, H * 0.5, Math.max(W, H) * 0.8);
    bg.addColorStop(0, "rgba(24, 33, 56, 0.9)");
    bg.addColorStop(0.55, "rgba(9, 13, 22, 0.95)");
    bg.addColorStop(1, "#05080f");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    const t = clock || performance.now() / 1000;
    const elapsed = (performance.now() - startedAt) / 1000;

    ctx.save();
    ctx.translate(tx, ty);
    ctx.scale(scale, scale);

    stars.forEach((star) => {
      const twinkle = 0.55 + 0.45 * Math.sin(t * 0.6 + star.p);
      ctx.globalAlpha = star.a * twinkle;
      ctx.fillStyle = "#9fb6d8";
      ctx.beginPath();
      ctx.arc((star.x - tx) / scale, (star.y - ty) / scale, star.r / scale, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;

    // 星团光晕
    nodes.forEach((node) => {
      if (node.type !== "category" || !filters.category) return;
      const radius = 110 + (node.weight || 1) * 22;
      const halo = ctx.createRadialGradient(px(node), py(node), 8, px(node), py(node), radius);
      halo.addColorStop(0, "rgba(196, 181, 253, 0.16)");
      halo.addColorStop(0.55, "rgba(140, 120, 220, 0.05)");
      halo.addColorStop(1, "rgba(140, 120, 220, 0)");
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(px(node), py(node), radius, 0, Math.PI * 2);
      ctx.fill();
    });

    // 悬停邻接
    const nearSet = new Set();
    if (hover) {
      nearSet.add(hover);
      edges.forEach((edge) => {
        if (edge.a === hover || edge.b === hover) {
          nearSet.add(edge.a);
          nearSet.add(edge.b);
        }
      });
    }

    edges.forEach((edge) => {
      if (!visible(edge.a) || !visible(edge.b)) return;
      const focused = hover && (edge.a === hover || edge.b === hover);
      const dim = dimmed(edge.a) || dimmed(edge.b);
      let a = edge.type === "category" ? 0.15 : edge.type === "tag" ? 0.11 : 0.08;
      if (focused) a = 0.72;
      else if (hover) a *= 0.28;
      if (dim) a *= 0.2;
      ctx.globalAlpha = a;
      if (focused) {
        const g = ctx.createLinearGradient(px(edge.a), py(edge.a), px(edge.b), py(edge.b));
        g.addColorStop(0, COLORS[edge.a.type]);
        g.addColorStop(1, COLORS[edge.b.type]);
        ctx.strokeStyle = g;
      } else {
        ctx.strokeStyle = edge.type === "category" ? "#8fa3d4" : edge.type === "tag" ? "#4fd1c5" : "#6f8fc7";
      }
      ctx.lineWidth = (focused ? 1.6 : edge.type === "category" ? 1 : 0.65) / scale;
      ctx.beginPath();
      ctx.moveTo(px(edge.a), py(edge.a));
      ctx.lineTo(px(edge.b), py(edge.b));
      ctx.stroke();
    });
    ctx.globalAlpha = 1;

    nodes.forEach((node) => {
      if (!visible(node)) return;
      const color = COLORS[node.type] || "#9fb0c8";
      const isHover = node === hover;
      const dim = dimmed(node);
      const near = nearSet.has(node);
      const spawn = Math.min(1, Math.max(0, (elapsed - 0.04 * (node.phase % 10)) / 0.7));
      const ease = 1 - Math.pow(1 - spawn, 3);
      const breathe = node.type === "category" ? 1 + Math.sin(t * 1.4 + node.phase) * 0.05 : 1;
      const r = node.r * ease * breathe + (isHover ? 2.2 : 0);
      const x = px(node);
      const y = py(node);

      ctx.globalAlpha = dim ? 0.12 : near || !hover ? 1 : 0.4;

      const glowScale = isHover ? 5.2 : node.type === "category" ? 4.6 : 2.9;
      const gsize = Math.max(6, r * glowScale * 2);
      ctx.globalAlpha *= isHover ? 0.95 : node.type === "category" ? 0.8 : 0.55;
      ctx.drawImage(sprite(color), x - gsize / 2, y - gsize / 2, gsize, gsize);
      ctx.globalAlpha = dim ? 0.12 : near || !hover ? 1 : 0.4;

      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x, y, Math.max(0.6, r * 0.62), 0, Math.PI * 2);
      ctx.fill();

      if (node.type === "category") {
        ctx.strokeStyle = "rgba(232, 236, 248, 0.5)";
        ctx.lineWidth = 1 / scale;
        ctx.beginPath();
        ctx.arc(x, y, r + 4 / scale, 0, Math.PI * 2);
        ctx.stroke();
      }

      if (highlight.size && node.type === "doc" && highlight.has(node.docId)) {
        ctx.globalAlpha = 0.95;
        ctx.strokeStyle = "#f5c26b";
        ctx.lineWidth = 1.4 / scale;
        ctx.beginPath();
        ctx.arc(x, y, r + 6 / scale, 0, Math.PI * 2);
        ctx.stroke();
      }
    });
    ctx.globalAlpha = 1;

    // 标签
    const zoom = scale;
    nodes.forEach((node) => {
      if (!visible(node)) return;
      const isHover = node === hover;
      const isCategory = node.type === "category";
      const isDoc = node.type === "doc";
      let show = isHover || isCategory;
      if (!show && isDoc && showLabels) show = node.degree >= 3 || zoom > 0.9;
      if (!show && !isDoc && !isCategory && showLabels) show = zoom > 1.4;
      if (!show) return;

      const size = (isCategory ? 13 : isDoc ? 11.5 : 10) + (isHover ? 1 : 0);
      const label = node.label.length > 18 ? node.label.slice(0, 17) + "…" : node.label;
      const x = px(node);
      const y = py(node) + node.r + (size * 1.3) / scale;

      ctx.font = `600 ${size / scale}px -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif`;
      if (isCategory || isHover) {
        const textW = ctx.measureText(label).width * scale;
        const padX = 7;
        ctx.globalAlpha = dimmed(node) ? 0.15 : 0.72;
        ctx.fillStyle = "rgba(7, 10, 18, 0.78)";
        roundRect(ctx, x - textW / 2 - padX, y - size / scale, textW + padX * 2, (size * 1.75) / scale, (size * 0.6) / scale);
        ctx.fill();
      }

      ctx.globalAlpha = dimmed(node) ? 0.16 : isHover ? 1 : 0.9;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = isHover ? "#ffffff" : isCategory ? "#ece8ff" : "rgba(216, 227, 246, 0.92)";
      ctx.fillText(label, x, y);
    });

    ctx.restore();
    ctx.globalAlpha = 1;
  }

  /* ------------------------------------------------------------ 交互 */

  function toWorld(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: (clientX - rect.left - tx) / scale,
      y: (clientY - rect.top - ty) / scale,
    };
  }

  function hitTest(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    let best = null;
    let bestDistance = Infinity;
    nodes.forEach((node) => {
      if (!visible(node)) return;
      const sx = px(node) * scale + tx + rect.left;
      const sy = py(node) * scale + ty + rect.top;
      const radius = Math.max(node.r * scale, 9);
      const distance = Math.hypot(clientX - sx, clientY - sy);
      if (distance < radius + 5 && distance < bestDistance) {
        best = node;
        bestDistance = distance;
      }
    });
    return best;
  }

  function onWheel(event) {
    event.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mx = event.clientX - rect.left;
    const my = event.clientY - rect.top;
    const worldX = (mx - tx) / scale;
    const worldY = (my - ty) / scale;
    const factor = Math.exp(-event.deltaY * 0.0015);
    scale = Math.min(5, Math.max(0.2, scale * factor));
    tx = mx - worldX * scale;
    ty = my - worldY * scale;
    draw();
  }

  function onDown(event) {
    if (event.button !== 0) return;
    pointer = { x: event.clientX, y: event.clientY };
    moved = false;
    const node = hitTest(event.clientX, event.clientY);
    if (node) {
      dragNode = node;
      node.vx = 0;
      node.vy = 0;
    } else {
      panning = true;
      canvas.style.cursor = "grabbing";
    }
    kick(0.3);
  }

  function onMove(event) {
    if (dragNode) {
      const world = toWorld(event.clientX, event.clientY);
      const d = drift(dragNode);
      dragNode.x = world.x - d.x;
      dragNode.y = world.y - d.y;
      dragNode.bx = dragNode.x;
      dragNode.by = dragNode.y;
      dragNode.vx = 0;
      dragNode.vy = 0;
      moved = true;
      kick(0.2);
      return;
    }
    if (panning) {
      tx += event.clientX - pointer.x;
      ty += event.clientY - pointer.y;
      pointer = { x: event.clientX, y: event.clientY };
      moved = true;
      draw();
      return;
    }
    if (!canvas || event.target !== canvas) {
      if (hover) {
        hover = null;
        hideTip();
        canvas.style.cursor = "grab";
        draw();
      }
      return;
    }
    const node = hitTest(event.clientX, event.clientY);
    canvas.style.cursor = node ? "pointer" : "grab";
    if (node !== hover) {
      hover = node;
      if (node) showTip(node, event);
      else hideTip();
      draw();
    } else if (node) {
      positionTip(event);
    }
  }

  function onUp() {
    if (dragNode) {
      const node = dragNode;
      dragNode = null;
      if (!moved) {
        if (node.type === "doc" && node.docId) hooks.openDoc(node.docId);
        else if (node.type === "term") hooks.searchTerm(node.label);
        else if (node.type === "category") hooks.searchTerm(node.label === "未分类" ? "" : node.label);
      }
      kick(0.2);
    }
    panning = false;
    if (canvas) canvas.style.cursor = "grab";
  }

  function showTip(node, event) {
    const tip = document.getElementById("graph-tip");
    if (!tip) return;
    const kind = TYPE_NAME[node.type] || node.type;
    const extra = node.type === "doc"
      ? `<div class="kind">${escapeHtml(node.category || "未分类")} · 关联 ${node.degree}</div>`
      : `<div class="kind">${kind} · 出现于 ${node.degree} 处</div>`;
    tip.innerHTML = `<b>${escapeHtml(node.label)}</b>${extra}`;
    tip.classList.remove("hidden");
    positionTip(event);
  }

  function positionTip(event) {
    const tip = document.getElementById("graph-tip");
    if (!tip || tip.classList.contains("hidden")) return;
    const rect = host.getBoundingClientRect();
    const x = Math.min(event.clientX - rect.left + 16, rect.width - tip.offsetWidth - 10);
    const y = Math.min(event.clientY - rect.top + 14, rect.height - tip.offsetHeight - 10);
    tip.style.left = Math.max(6, x) + "px";
    tip.style.top = Math.max(6, y) + "px";
  }

  function hideTip() {
    const tip = document.getElementById("graph-tip");
    if (tip) tip.classList.add("hidden");
  }

  function escapeHtml(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  /* ------------------------------------------------------------ 视图控制 */

  function fit(padding) {
    const pad = padding || 80;
    const list = nodes.filter(visible);
    if (!list.length) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    list.forEach((node) => {
      const x = px(node);
      const y = py(node);
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    });
    const width = Math.max(maxX - minX, 140);
    const height = Math.max(maxY - minY, 140);
    scale = Math.min((W - pad * 2) / width, (H - pad * 2) / height, 2);
    scale = Math.max(0.2, scale);
    tx = W / 2 - ((minX + maxX) / 2) * scale;
    ty = H / 2 - ((minY + maxY) / 2) * scale;
    draw();
  }

  function reheat() {
    nodes.forEach((node) => {
      node.vx = (Math.random() - 0.5) * 2;
      node.vy = (Math.random() - 0.5) * 2;
    });
    startedAt = performance.now();
    alpha = 1;
    kick(1);
  }

  function setFilter(type, on) {
    filters[type] = !!on;
    if (!active) draw();
  }

  function setLabels(on) {
    showLabels = !!on;
    if (!active) draw();
  }

  function setHighlight(docIds) {
    highlight = new Set(docIds || []);
    if (!active) draw();
  }

  function focusDoc(docId) {
    const node = nodes.find((n) => n.docId === docId);
    if (!node) return;
    tx = W / 2 - px(node) * scale;
    ty = H / 2 - py(node) * scale;
    hover = node;
    draw();
  }

  function resizePublic() {
    resize();
  }

  const api = {
    init,
    load,
    fit,
    reheat,
    setFilter,
    setLabels,
    setHighlight,
    focusDoc,
    resize: resizePublic,
    draw,
  };
  return api;
})();
