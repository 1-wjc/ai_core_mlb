// RAG 실험실 — 두 설정을 /api/lab 으로 실행하고 근거 · 답변을 나란히 표시

(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";

  function idForName(name) {
    for (const o of document.querySelectorAll("#player-options option")) if (o.value === name.normalize("NFC")) return o.dataset.id;
    return "";
  }

  function readConfig(fs) {
    const v = (n) => fs.querySelector(`[name="${n}"]`).value;
    return { chunk: v("chunk"), top_k_record: +v("top_k_record"), top_k_wiki: +v("top_k_wiki"), search_mode: v("search_mode"), mmr_lambda: +v("mmr_lambda") };
  }

  function md(text) {
    return esc(text).split(/\n{2,}/).map((p) => "<p>" + p.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br>") + "</p>").join("");
  }

  function resultHtml(side, r) {
    const c = r.config;
    const label = `청크 ${c.chunk} · 기록 ${c.top_k_record} · 위키 ${c.top_k_wiki} · ${c.search_mode === "mmr" ? `MMR λ ${c.mmr_lambda}` : "유사도 순"}`;
    const rows = r.evidence.map((e) =>
      `<tr class="${r.cited.includes(e.n) ? "cited" : ""}"><td>${e.n}</td><td class="l">${esc(e.source)}</td>` +
      `<td>${e.distance === null ? "항상" : e.distance.toFixed(3)}</td><td class="l snippet">${esc(e.snippet)}</td></tr>`).join("");
    const red = r.wiki_redundancy === null ? "–" : r.wiki_redundancy.toFixed(3);
    return `<div class="card lab-result">
      <div class="lab-result-head"><strong>설정 ${side}</strong><span class="note" style="margin:0">${esc(label)}</span></div>
      <div class="lab-metrics">
        <span>위키 청크 ${r.wiki_chunks_total.toLocaleString()}개</span><span>위키 근거끼리 평균 유사도 <b>${red}</b> (낮을수록 다양)</span>
        <span>근거 ${r.evidence.length}개 · 인용 ${r.cited.length}개</span><span>${r.elapsed}초</span>
      </div>
      <div class="table-wrap"><table class="lab-table"><thead><tr><th>#</th><th class="l">출처</th><th>거리</th><th class="l">근거 첫 부분</th></tr></thead><tbody>${rows}</tbody></table></div>
      <h3 class="detail-kind" style="margin-top:16px">답변</h3><div class="lab-answer">${md(r.answer)}</div>
      <p class="note">초록색 행 = 답변에서 실제로 인용한 근거</p>
    </div>`;
  }

  $("lab-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const playerId = idForName($("lab-player").value.trim());
    if (!playerId) { $("lab-player").classList.add("invalid"); return; }
    $("lab-player").classList.remove("invalid");
    const configs = [...document.querySelectorAll(".lab-config")].map(readConfig);
    $("lab-run").disabled = true;
    $("lab-status").textContent = "두 설정으로 검색하고 답변을 만드는 중입니다…";
    $("lab-results").innerHTML = "";
    try {
      const res = await fetch("/api/lab", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify({ player_id: playerId, question: $("lab-q").value.trim(), configs }),
      });
      const data = await res.json();
      if (!res.ok) { $("lab-status").textContent = data.error || "실행하지 못했습니다."; return; }
      $("lab-status").textContent = `${data.player_name} · 검색어(두 설정 공통): ${data.queries.join(", ")} · 전체 ${data.elapsed}초`;
      $("lab-results").innerHTML = data.results.map((r, i) => resultHtml(i === 0 ? "A" : "B", r)).join("");
    } catch (err) {
      $("lab-status").textContent = "서버에 연결하지 못했습니다.";
    } finally {
      $("lab-run").disabled = false;
    }
  });
})();
