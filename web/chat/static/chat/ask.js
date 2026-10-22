// 질문 패널 — 이름 → player_id 변환(datalist), /api/ask 질문 · 인용 근거만 표시(F2008),
//      대화 기록은 선수(비교 시 조합)별로 브라우저에 저장하고 직전 대화를 서버로 보낸다 (F2009)

(function () {
  const $ = (id) => document.getElementById(id);

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function renderMarkdown(text) {
    return escapeHtml(text)
      .split(/\n{2,}/)
      .map((p) => "<p>" + p.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br>") + "</p>")
      .join("");
  }

  // ---------- 비교 선수 고르기 ----------
  function idForName(name) {
    for (const o of document.querySelectorAll("#player-options option")) {
      if (o.value === name.normalize("NFC")) return o.dataset.id;
    }
    return "";
  }

  const pick = $("pick-form");
  if (pick) {
    pick.addEventListener("submit", (e) => {
      for (const [nameId, hiddenId] of [["a-name", "a-id"], ["b-name", "b-id"]]) {
        const field = $(nameId);
        const id = idForName(field.value.trim());
        if (!id) { e.preventDefault(); field.classList.add("invalid"); field.focus(); return; }
        field.classList.remove("invalid");
        $(hiddenId).value = id;
      }
    });
  }

  // ---------- 질문 패널 ----------
  const panel = $("ask-panel");
  if (!panel) return;
  const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
  const box = $("ask-messages");
  let first = true;
  const storeKey = `mlb-lab:${panel.dataset.player}|${panel.dataset.compare || ""}`;
  function loadLog() { try { return JSON.parse(localStorage.getItem(storeKey) || "[]"); } catch (e) { return []; } }
  function saveLog(log) { try { localStorage.setItem(storeKey, JSON.stringify(log.slice(-40))); } catch (e) { /* 저장 불가 */ } }
  const log = loadLog();
  let streaming = false;    // RAG 모드면 /api/ask_stream 으로 글자를 받는 대로 표시 (B4)

  fetch("/api/status").then((r) => r.json()).then((s) => {
    const mode = $("ask-mode");
    mode.textContent = s.mode === "RAG" ? "RAG" : "기록 검색";
    streaming = s.mode === "RAG";
    if (s.mode === "RAG") mode.classList.add("rag");
    const count = $("ask-count");
    if (count) count.textContent = `색인: 선수 ${(s.index_meta || 0).toLocaleString()} · 문서 청크 ${(s.index_docs || 0).toLocaleString()}`;
    if (s.notice) box.insertAdjacentHTML("afterbegin", `<p class="notice">${escapeHtml(s.notice)}</p>`);
  }).catch(() => { $("ask-mode").textContent = "연결 안 됨"; });

  function bubble(html, who) {
    if (first) { box.querySelectorAll(".ask-hint").forEach((el) => el.remove()); first = false; }
    const div = document.createElement("div");
    div.className = `bubble ${who}`;
    div.innerHTML = html;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
  }

  function sourcesHtml(data) {
    const used = data.sources.filter((s) => data.cited.includes(s.n));
    if (!used.length) return '<div class="steps" style="margin-top:8px">답변에 인용된 근거가 없습니다.</div>';
    // 근거마다 인용한 본문을 펼쳐 볼 수 있게 (A3 근거 원문 미리보기)
    const items = used.map((s) =>
      `<li><span class="src-tag">[${s.n}] ${escapeHtml(s.source)}</span>` +
      `<a href="${encodeURI(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.title)}</a>` +
      (s.text ? `<details class="src-text"><summary>인용한 본문 보기</summary><p>${escapeHtml(s.text).replace(/\n/g, "<br>")}</p></details>` : "") +
      `</li>`).join("");
    return `<details><summary>근거 ${used.length}건</summary><ol>${items}</ol></details>`;
  }

  // 사실 확인 판정 배지 (A1)
  const VERDICT_CLASS = { "참": "v-true", "거짓": "v-false", "일부 사실": "v-partial", "근거 부족": "v-unknown" };
  function verdictHtml(data) {
    return data.verdict ? `<div class="verdict ${VERDICT_CLASS[data.verdict] || "v-unknown"}">판정 · ${escapeHtml(data.verdict)}</div>` : "";
  }

  function answerHtml(data) {
    return verdictHtml(data) + `<div class="steps">${escapeHtml(data.steps.join(" · "))} · ${data.elapsed}초</div>${renderMarkdown(data.answer)}${sourcesHtml(data)}`;
  }

  // 저장된 대화 다시 그리기
  for (const m of log) {
    if (m.role === "user") bubble((m.mode === "factcheck" ? '<span class="me-tag">사실 확인</span> ' : "") + escapeHtml(m.content), "me");
    else if (m.data) bubble(answerHtml(m.data), "bot");
  }

  // 질문 / 사실 확인 전환 (A1)
  let askMode = "ask";
  document.querySelectorAll(".ask-modes button").forEach((b) => b.addEventListener("click", () => {
    askMode = b.dataset.mode;
    document.querySelectorAll(".ask-modes button").forEach((x) => x.classList.toggle("on", x === b));
    $("ask-input").placeholder = askMode === "factcheck"
      ? "확인할 주장을 입력하세요 (예: 2019년 평균자책점은 2점대 초반이었다)"
      : "질문을 입력하세요";
    $("ask-input").focus();
  }));

  async function ask(question) {
    const previous = log.slice(-6).map((m) => ({ role: m.role, content: m.content }));
    const mode = askMode;
    bubble((mode === "factcheck" ? '<span class="me-tag">사실 확인</span> ' : "") + escapeHtml(question), "me");
    const pending = bubble('<span class="typing"><i></i><i></i><i></i></span>', "bot");
    const payload = JSON.stringify({ player_id: panel.dataset.player, compare_id: panel.dataset.compare, question, history: previous, mode });
    const headers = { "Content-Type": "application/json", "X-CSRFToken": csrf };
    try {
      let data = null, errorText = "";
      if (streaming) {
        // 스트리밍: 근거 목록 → 답변 글자 → 최종 결과 (한 줄에 JSON 하나)
        const res = await fetch("/api/ask_stream", { method: "POST", headers, body: payload });
        if (!res.ok) { errorText = (await res.json()).error || "답변을 만들지 못했습니다."; }
        else {
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "", text = "", steps = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let nl;
            while ((nl = buffer.indexOf("\n")) >= 0) {
              const ev = JSON.parse(buffer.slice(0, nl));
              buffer = buffer.slice(nl + 1);
              if (ev.type === "evidence") {
                steps = `<div class="steps">${escapeHtml(ev.steps.join(" · "))} · 답변 작성 중…</div>`;
                pending.innerHTML = steps;
              } else if (ev.type === "token") {
                text += ev.text;
                pending.innerHTML = steps + renderMarkdown(text);
                box.scrollTop = box.scrollHeight;
              } else if (ev.type === "final") {
                data = ev;
              } else if (ev.type === "error") {
                errorText = ev.error;
              }
            }
          }
        }
      } else {
        const res = await fetch("/api/ask", { method: "POST", headers, body: payload });
        const json = await res.json();
        if (res.ok) data = json; else errorText = json.error || "답변을 만들지 못했습니다.";
      }
      if (data) {
        pending.innerHTML = answerHtml(data);
        log.push({ role: "user", content: question, mode }, { role: "assistant", content: data.answer, data });
        saveLog(log);
      } else {
        pending.innerHTML = `<p style="color:var(--red)">${escapeHtml(errorText || "답변을 만들지 못했습니다.")}</p>`;
      }
    } catch (e) {
      pending.innerHTML = '<p style="color:var(--red)">서버에 연결하지 못했습니다.</p>';
    }
    box.scrollTop = box.scrollHeight;
  }

  const clear = $("ask-clear");
  if (clear) clear.addEventListener("click", () => {
    log.length = 0;
    saveLog(log);
    box.querySelectorAll(".bubble").forEach((b) => b.remove());
  });

  $("ask-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("ask-input").value.trim();
    if (!q) return;
    $("ask-input").value = "";
    ask(q);
  });
  document.querySelectorAll(".ask-suggest").forEach((b) => b.addEventListener("click", () => ask(b.textContent)));

  // 메인의 질문 예시로 들어온 경우 (?ask=질문) — 한 번만 질문하고 주소에서는 지운다
  const params = new URLSearchParams(location.search);
  const auto = params.get("ask");
  if (auto) {
    params.delete("ask");
    history.replaceState(null, "", location.pathname + (params.toString() ? "?" + params : ""));
    ask(auto);
  }
})();
