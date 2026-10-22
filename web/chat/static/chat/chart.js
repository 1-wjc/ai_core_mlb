// 커리어 그래프 (B1) — 시즌별 지표 한 개를 선 그래프로. 지표 버튼으로 전환, 마우스를 올리면 십자선 + 툴팁
//   단일 시리즈라 범례 없음(제목이 이름), 축 하나, 2px 선 · 반지름 4px 점 + 2px 바탕색 테두리, 격자는 1px 옅은 실선
//   표본이 적은 시즌(50타석 · 10이닝 미만)은 비율 지표를 비워 둔다 (선이 끊김)

(function () {
  const root = document.getElementById("career-chart");
  if (!root) return;
  const data = JSON.parse(document.getElementById("chart-data").textContent);
  const svg = root.querySelector("svg");
  const tip = root.querySelector(".chart-tip");
  const NS = "http://www.w3.org/2000/svg";
  let metric = root.querySelector(".chart-metrics button.on").dataset.metric;

  const METRICS = {
    ops_plus: { label: "OPS+", fmt: (v) => v.toFixed(0), ref: 100, refLabel: "리그 평균 100" },
    hr: { label: "홈런", fmt: (v) => v.toFixed(0) },
    avg: { label: "타율", fmt: (v) => v.toFixed(3).replace(/^0/, "") },
    era_plus: { label: "ERA+", fmt: (v) => v.toFixed(0), ref: 100, refLabel: "리그 평균 100" },
    so: { label: "탈삼진", fmt: (v) => v.toFixed(0) },
    era: { label: "평균자책점", fmt: (v) => v.toFixed(2), lowerBetter: true },
  };

  function el(name, attrs, parent) {
    const node = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (parent) parent.appendChild(node);
    return node;
  }

  function niceMax(v) {
    if (v <= 0) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }

  function draw() {
    const m = METRICS[metric];
    const width = root.clientWidth;
    const height = 260;
    const pad = { l: 44, r: 16, t: 18, b: 28 };
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("height", height);
    svg.innerHTML = "";

    const pts = data.map((d) => ({ ...d, v: d[metric] }));
    const vals = pts.filter((p) => p.v !== null && p.v !== undefined).map((p) => p.v);
    if (!vals.length) { el("text", { x: width / 2, y: height / 2, "text-anchor": "middle", class: "chart-axis" }, svg).textContent = "표시할 기록이 없습니다"; return; }
    const years = pts.map((p) => p.season);
    const x0 = Math.min(...years), x1 = Math.max(...years);
    const yMax = niceMax(Math.max(...vals, m.ref || 0) * 1.08);
    const yMin = 0;
    const X = (s) => pad.l + (x1 === x0 ? 0.5 : (s - x0) / (x1 - x0)) * (width - pad.l - pad.r);
    const Y = (v) => pad.t + (1 - (v - yMin) / (yMax - yMin)) * (height - pad.t - pad.b);

    // 격자 · y 눈금 (4칸)
    for (let i = 0; i <= 4; i++) {
      const v = yMin + (yMax - yMin) * i / 4;
      el("line", { x1: pad.l, x2: width - pad.r, y1: Y(v), y2: Y(v), class: "chart-grid" }, svg);
      el("text", { x: pad.l - 8, y: Y(v) + 4, "text-anchor": "end", class: "chart-axis" }, svg).textContent = m.fmt(v);
    }
    // x 눈금 (시즌 수에 맞춰 간격)
    const step = Math.max(1, Math.ceil((x1 - x0 + 1) / Math.max(2, Math.floor((width - 60) / 56))));
    for (let s = x0; s <= x1; s += step) {
      el("text", { x: X(s), y: height - 8, "text-anchor": "middle", class: "chart-axis" }, svg).textContent = s;
    }
    // 기준선 (리그 평균 100)
    if (m.ref) {
      el("line", { x1: pad.l, x2: width - pad.r, y1: Y(m.ref), y2: Y(m.ref), class: "chart-ref" }, svg);
      el("text", { x: width - pad.r, y: Y(m.ref) - 6, "text-anchor": "end", class: "chart-ref-label" }, svg).textContent = m.refLabel;
    }

    // 마일스톤 달성 시즌 — 점선 세로선 + 위쪽 작은 글자 (지표와 관계없이 항상)
    const rowEnds = [];                                  // 글자가 겹치면 아랫줄로 (줄마다 마지막 글자 오른쪽 끝)
    for (const p of pts) {
      if (!p.milestones || !p.milestones.length) continue;
      el("line", { x1: X(p.season), x2: X(p.season), y1: pad.t, y2: height - pad.b, class: "chart-milestone" }, svg);
      const label = el("text", { x: X(p.season) + 4, class: "chart-milestone-label" }, svg);
      label.textContent = p.milestones.join(" · ");
      const w = label.getComputedTextLength();
      let row = rowEnds.findIndex((end) => X(p.season) + 4 > end + 6);
      if (row < 0) { row = rowEnds.length; rowEnds.push(0); }
      rowEnds[row] = X(p.season) + 4 + w;
      label.setAttribute("y", pad.t + 10 + row * 14);
    }

    // 선 · 옅은 면 — 연속된 시즌끼리만 잇는다 (빈 시즌 · 표본 부족이면 끊김)
    const runs = [];
    let run = [];
    pts.forEach((p, i) => {
      const ok = p.v !== null && p.v !== undefined;
      const consecutive = i > 0 && p.season === pts[i - 1].season + 1;
      if (!ok || (run.length && !consecutive)) { if (run.length) runs.push(run); run = []; }
      if (ok) run.push(p);
    });
    if (run.length) runs.push(run);
    for (const r of runs) {
      const line = r.map((p, i) => `${i ? "L" : "M"}${X(p.season)},${Y(p.v)}`).join(" ");
      if (r.length > 1) {
        el("path", { d: `${line} L${X(r[r.length - 1].season)},${Y(yMin)} L${X(r[0].season)},${Y(yMin)} Z`, class: "chart-area" }, svg);
        el("path", { d: line, class: "chart-line" }, svg);
      }
    }
    for (const p of pts) if (p.v !== null && p.v !== undefined) el("circle", { cx: X(p.season), cy: Y(p.v), r: 4, class: "chart-dot" }, svg);

    // 마우스 — 시즌 열마다 넓은 투명 영역, 십자선 + 툴팁
    const cross = el("line", { y1: pad.t, y2: height - pad.b, class: "chart-cross", visibility: "hidden" }, svg);
    const colW = (width - pad.l - pad.r) / Math.max(1, x1 - x0);
    for (const p of pts) {
      const hit = el("rect", { x: X(p.season) - colW / 2, y: pad.t, width: Math.max(colW, 8), height: height - pad.t - pad.b, class: "chart-hit" }, svg);
      const show = () => {
        cross.setAttribute("x1", X(p.season)); cross.setAttribute("x2", X(p.season)); cross.setAttribute("visibility", "visible");
        const value = p.v === null || p.v === undefined ? "표본 부족 · 기록 없음" : m.fmt(p.v);
        tip.innerHTML = `<strong>${p.season}</strong> <span>${p.teams || ""}</span><br>${m.label} <b>${value}</b><br><small>${(["era_plus", "so", "era"].includes(metric) ? p.ip_text : p.pa_text) || ""}</small>` +
          (p.milestones && p.milestones.length ? `<br><small class="tip-ms">달성: ${p.milestones.join(" · ")}</small>` : "");
        tip.hidden = false;
        const left = Math.min(Math.max(X(p.season) - tip.offsetWidth / 2, 0), width - tip.offsetWidth);
        tip.style.left = `${left}px`;
        tip.style.top = `${Math.max(0, (p.v !== null && p.v !== undefined ? Y(p.v) : pad.t) - tip.offsetHeight - 12)}px`;
      };
      hit.addEventListener("mouseenter", show);
      hit.addEventListener("click", show);
      hit.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); tip.hidden = true; });
    }
    root.querySelector(".chart-title").textContent = `시즌별 ${m.label}` + (m.lowerBetter ? " (낮을수록 좋음)" : "");
  }

  root.querySelectorAll(".chart-metrics button").forEach((b) => b.addEventListener("click", () => {
    root.querySelectorAll(".chart-metrics button").forEach((x) => x.classList.toggle("on", x === b));
    metric = b.dataset.metric;
    draw();
  }));
  new ResizeObserver(draw).observe(root);
})();
