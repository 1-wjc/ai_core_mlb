// 메인 — 선수 검색 자동 완성 · 질문 예시 회전 · 시즌 타임라인

(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------------- 선수 검색: 입력하면 아래에 후보, 하나를 고르면 선수 페이지로 ----------------
  const input = $("home-q");
  const list = $("home-suggest");
  let players = [];
  fetch("/api/players").then((r) => r.json()).then((d) => { players = d.players; }).catch(() => {});
  function suggest() {
    const q = input.value.normalize("NFC").trim().toLowerCase();
    if (!q || !players.length) { list.hidden = true; return; }
    const hits = players.filter((p) => p.name_ko.toLowerCase().includes(q) || p.name_en.toLowerCase().includes(q)).slice(0, 8);
    list.innerHTML = hits.map((p) =>
      `<li role="option"><a href="/players/${encodeURIComponent(p.player_id)}/"><strong>${esc(p.name_en)}</strong> ` +
      `<span>${esc(p.name_ko)} · ${esc(p.position)} · ${p.first_season}–${p.last_season}</span></a></li>`).join("") ||
      '<li class="none">일치하는 선수가 없습니다</li>';
    list.hidden = false;
  }
  input.addEventListener("input", suggest);
  input.addEventListener("focus", suggest);
  document.addEventListener("click", (e) => { if (!$("home-search").contains(e.target)) list.hidden = true; });

  if (!$("ticker")) return;   // 검색 결과 화면에는 질문 예시 · 타임라인이 없음

  // ---------------- 질문 예시: 4초마다 다음 예시, 점을 누르면 그 예시 ----------------
  const items = [...document.querySelectorAll(".ticker-item")];
  const dots = [...document.querySelectorAll(".ticker-dots button")];
  let current = 0;
  function showExample(i) {
    current = (i + items.length) % items.length;
    items.forEach((el, k) => el.classList.toggle("on", k === current));
    dots.forEach((el, k) => el.classList.toggle("on", k === current));
  }
  let timer = setInterval(() => showExample(current + 1), 4000);
  dots.forEach((d) => d.addEventListener("click", () => { clearInterval(timer); showExample(+d.dataset.i); timer = setInterval(() => showExample(current + 1), 4000); }));
  $("ticker").addEventListener("mouseenter", () => clearInterval(timer));
  $("ticker").addEventListener("mouseleave", () => { clearInterval(timer); timer = setInterval(() => showExample(current + 1), 4000); });

  // ---------------- 시즌 타임라인 ----------------
  const data = JSON.parse($("timeline-data").textContent);
  const byYear = Object.fromEntries(data.map((d) => [d.year, d]));
  const FIRST = data[0].year, LAST = data[data.length - 1].year;   // 타임라인 범위 (데이터 기준)
  // 서비스 선수면 선수 페이지로 연결, 아니면 이름만 (리그 전체 1위 · 수상은 Lahman 전체 선수 기준)
  const link = (p) => (p.id ? `<a href="/players/${encodeURIComponent(p.id)}/">${esc(p.name)}</a>` : `<span class="plain">${esc(p.name)}</span>`)
    + (p.league ? ` <span class="tl-lg">${esc(p.league)}</span>` : "");
  function people(list) { return list.length ? list.map(link).join("<br>") : '<span class="muted-text">–</span>'; }
  function leader(p, unit) { return p ? `${link(p)} <span class="tl-val">${esc(p.value)}${unit}</span>` : '<span class="muted-text">–</span>'; }
  function render(year) {
    const d = byYear[year];
    $("tl-year").textContent = year;                                  // 손잡이 = 연도 글자
    $("tl-range").value = year;
    $("tl-track").style.setProperty("--p", (year - FIRST) / (LAST - FIRST));   // 손잡이 위치 · 채운 구간
    const ws = d.ws
      ? `<div class="tl-big">${esc(d.ws.team)} <span class="tl-abbr">${esc(d.ws.abbr)}</span></div><div class="tl-sub">${esc(d.ws.result)} · 상대 ${esc(d.ws.opponent)}</div>`
      : `<div class="tl-big muted-text">${year === 1994 ? "파업으로 월드시리즈 없음" : "기록 없음"}</div>`;
    $("tl-grid").innerHTML = `
      <div class="tl-card wide"><div class="tl-k">월드시리즈 우승</div>${ws}</div>
      <div class="tl-card"><div class="tl-k">MVP</div><div class="tl-v">${people(d.mvp)}</div></div>
      <div class="tl-card"><div class="tl-k">사이영상</div><div class="tl-v">${people(d.cy)}</div></div>
      <div class="tl-card"><div class="tl-k">홈런 1위</div><div class="tl-v">${leader(d.hr, "개")}</div></div>
      <div class="tl-card"><div class="tl-k">타율 1위 <small>규정 타석</small></div><div class="tl-v">${leader(d.avg, "")}</div></div>
      <div class="tl-card"><div class="tl-k">평균자책점 1위 <small>규정 이닝</small></div><div class="tl-v">${leader(d.era, "")}</div></div>
      <div class="tl-card"><div class="tl-k">탈삼진 1위</div><div class="tl-v">${leader(d.so, "개")}</div></div>`;
  }
  $("tl-range").addEventListener("input", (e) => render(+e.target.value));
  $("tl-prev").addEventListener("click", () => render(Math.max(FIRST, +$("tl-range").value - 1)));
  $("tl-next").addEventListener("click", () => render(Math.min(LAST, +$("tl-range").value + 1)));
  render(LAST);
})();
