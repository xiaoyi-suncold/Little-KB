/* 知识星图：簇状放射布局 + 抗重叠标签 + 轻量发光，无任何外部依赖 */
window.KBGraph = (function () {
  "use strict";

  const COLORS = {
    category: "#a78bfa",
    doc: "#5b9cf8",
    tag: "#2dd4bf",
    term: "#fbbf24",
  };
  const TYPE_NAME = { doc: "文档", term: "关键词", tag: "标签", category: "分类" };
  const BASE_R = { category: 10, doc: 5.2, tag: 3.1, term: 2.2 };
  const GOLD = Math.PI * (3 - Math.sqrt(5));
  const DOC_SPACING = 33;
  /* 每个分类一个色相，文档继承所属分类的颜色，让星团有层次 */
  const CAT_PALETTE = [
    "#a78bfa", "#60a5fa", "#34d399", "#f472b6",
    "#fbbf24", "#38bdf8", "#c084fc", "#4ade80",
    "#fb923c", "#e879f9", "#22d3ee", "#a3e635",
  ];

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
  let clusters = [];

  let scale = 1;
  let tx = 0;
  let ty = 0;
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

  let rafId = 0;
  let lastFrame = 0;

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
    startLoop();
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
      nodes.forEach((node) => {
        node.x = node.bx;
        node.y = node.by;
      });
      fit(64);
    }
    draw();
  }

  function makeStars() {
    stars = [];
    const count = Math.round((W * H) / 26000);
    for (let i = 0; i < count; i += 1) {
      stars.push({
        x: Math.random() * W,
        y: Math.random() * H,
        r: Math.random() * 0.9 + 0.2,
        a: Math.random() * 0.22 + 0.04,
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
        draw();
      }
    });
    canvas.addEventListener("dblclick", () => fit());
  }

  /* ------------------------------------------------------------ 发光精灵 */

  function sprite(color) {
    if (sprites.has(color)) return sprites.get(color);
    const size = 64;
    const c = document.createElement("canvas");
    c.width = size;
    c.height = size;
    const g = c.getContext("2d");
    const r = size / 2;
    const grad = g.createRadialGradient(r, r, 0, r, r, r);
    grad.addColorStop(0, hexA(color, 0.85));
    grad.addColorStop(0.3, hexA(color, 0.32));
    grad.addColorStop(0.62, hexA(color, 0.09));
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
        order: i,
        phase: Math.random() * Math.PI * 2,
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
    fit(64);
    return { nodes: nodes.length, edges: edges.length };
  }

  function radiusOf(node) {
    const base = BASE_R[node.type] || 3;
    if (node.type === "doc") {
      return base + Math.min(3.4, Math.log10((Number(node.weight) || 0) + 10) * 1.1);
    }
    if (node.type === "category") {
      return base + Math.min(4, (node.weight || 1) * 0.5);
    }
    if (node.type === "tag") {
      return base + Math.min(1.2, (node.weight || 1) * 0.16);
    }
    return base;
  }

  /* ------------------------------------------------------------ 簇状放射布局 */

  function layoutClusters() {
    clusters = [];
    const cats = nodes
      .filter((n) => n.type === "category")
      .sort((a, b) => (b.weight || 1) - (a.weight || 1));

    const docsByCat = new Map();
    cats.forEach((c) => docsByCat.set(c.id, []));
    nodes.forEach((n) => {
      if (n.type !== "doc") return;
      const key = "cat:" + (n.category || "");
      if (docsByCat.has(key)) docsByCat.get(key).push(n);
    });

    // 每个簇的半径由文档数量决定，并分配独立色相
    cats.forEach((cat, ci) => {
      const docs = docsByCat.get(cat.id) || [];
      cat.docs = docs;
      cat.clusterR = Math.max(46, DOC_SPACING * Math.sqrt(Math.max(1, docs.length)) + 26);
      cat.color = CAT_PALETTE[ci % CAT_PALETTE.length];
      docs.forEach((doc) => { doc.color = cat.color; });
      clusters.push(cat);
    });

    // 构图：最大的簇居中，其余环绕成轨道，画面重心稳定不留大片空白
    if (cats.length) {
      const core = cats[0];
      core.bx = 0;
      core.by = 0;
      const satellites = cats.slice(1);
      if (satellites.length) {
        const arcBase = satellites.reduce((sum, c) => sum + c.clusterR + 50, 0);
        let cursor = -Math.PI / 2;
        satellites.forEach((cat, i) => {
          const share = (cat.clusterR + 50) / arcBase;
          const ang = cursor + share * Math.PI; // 落在自己扇区的中间
          cursor += share * Math.PI * 2;
          const radius = core.clusterR + cat.clusterR + 42;
          cat.bx = Math.cos(ang) * radius;
          cat.by = Math.sin(ang) * radius;
          // 轻微错落，避免看起来像机械的同心圆
          cat.bx += Math.sin(i * 2.1) * 18;
          cat.by += Math.cos(i * 1.7) * 18;
        });
      }
    }

    // 簇内文档：黄金角螺旋铺开
    cats.forEach((cat, ci) => {
      const docs = cat.docs.sort((a, b) => (b.weight || 1) - (a.weight || 1));
      const k = docs.length;
      const spacing = k <= 8 ? 30 : DOC_SPACING;
      docs.forEach((doc, j) => {
        const ang = j * GOLD + ci * 0.8;
        const rad = spacing * Math.sqrt(j + 0.45);
        doc.bx = cat.bx + Math.cos(ang) * rad;
        doc.by = cat.by + Math.sin(ang) * rad * 0.94;
      });
    });

    // 标签/关键词挂在关联文档周围
    const ringCount = new Map();
    nodes.forEach((node) => {
      if (node.type === "doc" || node.type === "category") return;
      const linked = edges.filter((e) => e.a === node || e.b === node);
      const base = linked.length
        ? (linked[0].a === node ? linked[0].b : linked[0].a)
        : null;
      const anchor = base && base.type !== "category" ? base : (clusters[0] || null);
      const key = anchor ? anchor.id : "root";
      const seq = ringCount.get(key) || 0;
      ringCount.set(key, seq + 1);
      const ang = seq * GOLD;
      const rad = 26 + Math.sqrt(seq) * 9;
      const ax = anchor ? anchor.bx : 0;
      const ay = anchor ? anchor.by : 0;
      node.bx = ax + Math.cos(ang) * rad;
      node.by = ay + Math.sin(ang) * rad;
    });
  }

  /* ------------------------------------------------------------ 轻漂移 */

  function drift(node) {
    const t = clock;
    const amp = node.type === "category" ? 1.1 : 1.7;
    return {
      x: Math.sin(t * 0.33 + node.phase) * amp,
      y: Math.cos(t * 0.28 + node.phase * 1.3) * amp,
    };
  }

  function px(node) {
    return node.x + drift(node).x;
  }

  function py(node) {
    return node.y + drift(node).y;
  }

  /* ------------------------------------------------------------ 渲染循环 */

  function startLoop() {
    if (rafId) return;
    const tick = (ts) => {
      rafId = requestAnimationFrame(tick);
      if (ts - lastFrame < 33) return; // ~30fps，够顺滑也省电
      lastFrame = ts;
      if (!host || host.offsetParent === null) return; // 视图隐藏时不绘制
      clock = ts / 1000;
      draw();
    };
    rafId = requestAnimationFrame(tick);
  }

  /* ------------------------------------------------------------ 绘制 */

  function visible(node) {
    return !!filters[node.type];
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
    if (!ctx || !W || !H) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const bg = ctx.createRadialGradient(W * 0.5, H * 0.45, 30, W * 0.5, H * 0.5, Math.max(W, H) * 0.78);
    bg.addColorStop(0, "#0d1424");
    bg.addColorStop(0.6, "#080c16");
    bg.addColorStop(1, "#04060c");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    const t = clock || performance.now() / 1000;
    const elapsed = (performance.now() - startedAt) / 1000;

    ctx.save();
    ctx.translate(tx, ty);
    ctx.scale(scale, scale);

    // 星尘背景
    stars.forEach((star) => {
      const twinkle = 0.6 + 0.4 * Math.sin(t * 0.5 + star.p);
      ctx.globalAlpha = star.a * twinkle;
      ctx.fillStyle = "#8fa7c9";
      ctx.beginPath();
      ctx.arc((star.x - tx) / scale, (star.y - ty) / scale, star.r / scale, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;

    // 簇的柔光 + 淡虚线边界
    if (filters.category) {
      clusters.forEach((cat) => {
        const radius = cat.clusterR * 1.5;
        const cx = px(cat);
        const cy = py(cat);
        const halo = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
        halo.addColorStop(0, hexA(cat.color, 0.1));
        halo.addColorStop(0.45, hexA(cat.color, 0.045));
        halo.addColorStop(1, hexA(cat.color, 0));
        ctx.fillStyle = halo;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.fill();

        ctx.save();
        ctx.globalAlpha = 0.1;
        ctx.strokeStyle = hexA(cat.color, 0.9);
        ctx.lineWidth = 1 / scale;
        ctx.setLineDash([3 / scale, 7 / scale]);
        ctx.beginPath();
        ctx.arc(cx, cy, cat.clusterR * 0.94, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      });
    }

    // 悬停邻接集合
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

    // 连线
    edges.forEach((edge) => {
      if (!visible(edge.a) || !visible(edge.b)) return;
      const focused = hover && (edge.a === hover || edge.b === hover);
      const dim = dimmed(edge.a) || dimmed(edge.b);
      let a = edge.type === "category" ? 0.16 : edge.type === "tag" ? 0.1 : 0.07;
      if (focused) a = 0.6;
      else if (hover) a *= 0.22;
      if (dim) a *= 0.18;
      ctx.globalAlpha = a;
      if (focused) {
        const g = ctx.createLinearGradient(px(edge.a), py(edge.a), px(edge.b), py(edge.b));
        g.addColorStop(0, COLORS[edge.a.type]);
        g.addColorStop(1, COLORS[edge.b.type]);
        ctx.strokeStyle = g;
      } else {
        ctx.strokeStyle = edge.a.color || edge.b.color || "#4a5f86";
      }
      ctx.lineWidth = (focused ? 1.5 : 0.7) / scale;
      ctx.beginPath();
      ctx.moveTo(px(edge.a), py(edge.a));
      ctx.lineTo(px(edge.b), py(edge.b));
      ctx.stroke();
    });
    ctx.globalAlpha = 1;

    // 节点
    nodes.forEach((node) => {
      if (!visible(node)) return;
      const color = node.color || COLORS[node.type] || "#93a5c0";
      const isHover = node === hover;
      const dim = dimmed(node);
      const near = nearSet.has(node);
      const spawn = Math.min(1, Math.max(0, (elapsed - node.order * 0.004) / 0.55));
      const ease = 1 - Math.pow(1 - spawn, 3);
      const breathe = node.type === "category" ? 1 + Math.sin(t * 1.1 + node.phase) * 0.04 : 1;
      const r = node.r * ease * breathe + (isHover ? 1.8 : 0);
      const x = px(node);
      const y = py(node);

      ctx.globalAlpha = dim ? 0.1 : near || !hover ? 1 : 0.32;

      if (node.type !== "term" && node.type !== "tag") {
        const glowScale = isHover ? 4.2 : node.type === "category" ? 3.4 : 2.6;
        const gsize = Math.max(8, r * glowScale * 2);
        ctx.globalAlpha *= node.type === "category" ? 0.72 : 0.5;
        ctx.drawImage(sprite(color), x - gsize / 2, y - gsize / 2, gsize, gsize);
        ctx.globalAlpha = dim ? 0.1 : near || !hover ? 1 : 0.32;
      }

      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x, y, Math.max(0.7, r * 0.68), 0, Math.PI * 2);
      ctx.fill();

      // 高光点，让星点更锐利
      ctx.fillStyle = "rgba(255, 255, 255, 0.55)";
      ctx.beginPath();
      ctx.arc(x - r * 0.16, y - r * 0.16, Math.max(0.35, r * 0.2), 0, Math.PI * 2);
      ctx.fill();

      if (node.type === "category") {
        // 四芒星闪光，让核心节点有"恒星"的辨识度
        const flare = r * 3.4;
        const lg = ctx.createLinearGradient(x - flare, y, x + flare, y);
        lg.addColorStop(0, hexA(color, 0));
        lg.addColorStop(0.5, hexA(color, 0.5));
        lg.addColorStop(1, hexA(color, 0));
        ctx.strokeStyle = lg;
        ctx.lineWidth = 1.1 / scale;
        ctx.beginPath();
        ctx.moveTo(x - flare, y);
        ctx.lineTo(x + flare, y);
        ctx.stroke();
        const lgv = ctx.createLinearGradient(x, y - flare, x, y + flare);
        lgv.addColorStop(0, hexA(color, 0));
        lgv.addColorStop(0.5, hexA(color, 0.5));
        lgv.addColorStop(1, hexA(color, 0));
        ctx.strokeStyle = lgv;
        ctx.beginPath();
        ctx.moveTo(x, y - flare);
        ctx.lineTo(x, y + flare);
        ctx.stroke();

        ctx.globalAlpha = dim ? 0.12 : 0.42;
        ctx.strokeStyle = hexA(color, 0.55);
        ctx.lineWidth = 1 / scale;
        ctx.beginPath();
        ctx.arc(x, y, r + 5.5, 0, Math.PI * 2);
        ctx.stroke();
        ctx.globalAlpha = dim ? 0.1 : near || !hover ? 1 : 0.32;
      }

      if (highlight.size && node.type === "doc" && highlight.has(node.docId)) {
        ctx.globalAlpha = 0.9;
        ctx.strokeStyle = "#fbbf24";
        ctx.lineWidth = 1.3 / scale;
        ctx.beginPath();
        ctx.arc(x, y, r + 5, 0, Math.PI * 2);
        ctx.stroke();
      }
    });
    ctx.globalAlpha = 1;

    // 标签（带碰撞剔除，先画分类再画文档）
    const placed = [];
    const tryPlace = (x, y, w, h) => {
      for (let i = 0; i < placed.length; i += 1) {
        const p = placed[i];
        if (x < p.x + p.w && x + w > p.x && y < p.y + p.h && y + h > p.y) return false;
      }
      placed.push({ x, y, w, h });
      return true;
    };

    const ordered = nodes
      .filter((n) => visible(n))
      .sort((a, b) => (rank(a) - rank(b)) || ((b.degree || 0) - (a.degree || 0)));

    ordered.forEach((node) => {
      const isHover = node === hover;
      const isCategory = node.type === "category";
      const isDoc = node.type === "doc";
      let show = false;
      if (isHover) show = true;
      else if (isCategory) show = showLabels;
      else if (isDoc) show = showLabels && (scale > 1.12 || node.degree >= 7);
      else show = showLabels && scale > 1.55;

      if (!show) return;

      const size = isCategory ? 12.5 : 10.5;
      let label = node.label.length > 15 ? node.label.slice(0, 14) + "…" : node.label;
      if (isCategory) label = `${label} · ${node.weight || (node.docs ? node.docs.length : 0)}`;

      ctx.font = `${isCategory || isHover ? 600 : 500} ${size / scale}px -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      // 世界坐标下的包围盒（文字尺寸需除以 scale 才与世界坐标同量纲）
      const boxW = ctx.measureText(label).width + 10 / scale;
      const boxH = (size / scale) * 1.55;
      const gapY = node.r + 3 + boxH / 2;
      const gapX = node.r + 3 + boxW / 2;

      const nx = px(node);
      const ny = py(node);
      const candidates = [
        [nx, ny + gapY],
        [nx, ny - gapY],
        [nx + gapX, ny],
        [nx - gapX, ny],
        [nx + gapX * 0.85, ny + gapY * 0.85],
        [nx - gapX * 0.85, ny + gapY * 0.85],
        [nx + gapX * 0.85, ny - gapY * 0.85],
        [nx - gapX * 0.85, ny - gapY * 0.85],
      ];

      let x = nx;
      let y = ny + gapY;
      let ok = !!isHover;
      if (!ok) {
        for (let i = 0; i < candidates.length; i += 1) {
          const cx = candidates[i][0];
          const cy = candidates[i][1];
          if (tryPlace(cx - boxW / 2, cy - boxH / 2, boxW, boxH)) {
            x = cx;
            y = cy;
            ok = true;
            break;
          }
        }
      }
      if (!ok) return;

      if (isCategory || isHover) {
        ctx.globalAlpha = dimmed(node) ? 0.12 : 0.88;
        ctx.fillStyle = "rgba(6, 9, 16, 0.74)";
        ctx.strokeStyle = hexA(node.color || COLORS[node.type] || "#93a5c0", 0.3);
        ctx.lineWidth = 0.9 / scale;
        roundRect(ctx, x - boxW / 2, y - boxH / 2, boxW, boxH, 5 / scale);
        ctx.fill();
        ctx.stroke();
      }

      ctx.globalAlpha = dimmed(node) ? 0.14 : isHover ? 1 : 0.88;
      ctx.fillStyle = isHover
        ? "#ffffff"
        : isCategory
          ? (node.color || "#e9e3ff")
          : "rgba(216, 228, 245, 0.95)";
      ctx.fillText(label, x, y);
    });

    ctx.restore();
    ctx.globalAlpha = 1;
  }

  function rank(node) {
    if (node === hover) return 0;
    if (node.type === "category") return 1;
    if (node.type === "doc") return 2;
    return 3;
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
    } else {
      panning = true;
      canvas.style.cursor = "grabbing";
    }
    draw();
  }

  function onMove(event) {
    if (dragNode) {
      const world = toWorld(event.clientX, event.clientY);
      const d = drift(dragNode);
      dragNode.x = world.x - d.x;
      dragNode.y = world.y - d.y;
      dragNode.bx = dragNode.x;
      dragNode.by = dragNode.y;
      moved = true;
      draw();
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
      draw();
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
    const pad = padding || 58;
    const list = nodes.filter(visible);
    if (!list.length) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    list.forEach((node) => {
      const x = px(node);
      const y = py(node);
      minX = Math.min(minX, x - node.r);
      minY = Math.min(minY, y - node.r);
      maxX = Math.max(maxX, x + node.r);
      maxY = Math.max(maxY, y + node.r);
    });
    const width = Math.max(maxX - minX, 160);
    const height = Math.max(maxY - minY, 160);
    scale = Math.min((W - pad * 2) / width, (H - pad * 2) / height, 1.75);
    scale = Math.max(0.2, scale);
    tx = W / 2 - ((minX + maxX) / 2) * scale;
    ty = H / 2 - ((minY + maxY) / 2) * scale;
    draw();
  }

  function reheat() {
    startedAt = performance.now();
    nodes.forEach((node) => {
      node.order = Math.floor(Math.random() * 40);
    });
    draw();
  }

  function setFilter(type, on) {
    filters[type] = !!on;
    draw();
  }

  function setLabels(on) {
    showLabels = !!on;
    draw();
  }

  function setHighlight(docIds) {
    highlight = new Set(docIds || []);
    draw();
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
