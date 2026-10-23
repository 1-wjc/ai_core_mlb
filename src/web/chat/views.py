# JSON API (화면은 chat/pages.py)
#   GET  /api/status   → {"mode": "RAG"|"기록 검색", "players", "record_docs", "index_meta", "index_docs", "key_ready", "notice"}
#   GET  /api/players  → {"players": [{player_id, name_ko, name_en, aliases(검색 별칭), role, position, first_season, last_season}]}
#   POST /api/ask      ← {"player_id": "ryuhy01", "question": "...", "compare_id": "kershcl01"(선택, F2010),
#                         "history": [{"role": "user"|"assistant", "content": "..."}](선택, F2009 직전 대화),
#                         "mode": "ask"|"factcheck"(선택, 사실 확인 — 입력을 주장으로 보고 판정)}
#                      → {"answer", "sources": [{n, title, url, source, text(인용 근거만 본문)}], "cited": [n, ...], "steps": [...],
#                         "collected": [질문 시 새로 수집한 문서 제목], "verdict", "check"(문장별 근거 점검), "mode", "elapsed"}
#   POST /api/lab      ← {"player_id", "question", "configs": [{chunk, top_k_record, top_k_wiki, search_mode, mmr_lambda} × 2]}
#                      → {"player_name", "queries", "results": [{config, wiki_chunks_total, wiki_redundancy, evidence, answer, cited, elapsed}], "elapsed"}
#   POST /api/ask_stream  ← /api/ask 와 같은 요청 → NDJSON 스트림 (evidence → token … → final, B4 답변 스트리밍)
#   POST /api/explore  ← {"condition": "통산 홈런 400개 이상인 좌타자"}   (F2011 조건 탐색, RAG 모드 전용)
#                      → {"cards": [{player_id, name_ko, name_en, role, position, first_season, last_season, reason}],
#                         "candidates": 후보 수, "rule": 규칙만으로 판정(LLM 미사용) 여부, "elapsed"}
#
# 모드: GMS 키와 색인이 있으면 RAG(rag/graph.py), 없으면 기록 검색(chat/search.py, LLM 미사용)으로 대신 답한다.

import json
import re
import time

from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_GET, require_POST

from chat import rag_service, search

CITE_PATTERN = re.compile(r"\[근거\s*([\d,\s]+)\]")


def current_mode():
    """(모드, 안내 문구)"""
    if not rag_service.key_ready():
        return "기록 검색", "GMS 키가 없어 기록 검색 모드(LLM 미사용)로 답합니다. .env 에 GMS_KEY 를 넣어 주세요."
    meta_count, _ = rag_service.index_counts()
    if meta_count == 0:
        return "기록 검색", "색인이 비어 있어 기록 검색 모드로 답합니다. python -m rag.indexer --all 을 실행하세요."
    return "RAG", ""


@require_GET
def status(request):
    try:
        players, docs = search.load_data()
    except FileNotFoundError:
        return JsonResponse({"players": 0, "record_docs": 0, "mode": "없음",
                             "notice": "데이터가 없습니다. collect → build 스크립트를 먼저 실행하세요."})
    mode, notice = current_mode()
    meta_count, docs_count = rag_service.index_counts()
    return JsonResponse({
        "mode": mode, "notice": notice, "key_ready": rag_service.key_ready(),
        "players": len(players), "record_docs": len(docs),
        "index_meta": meta_count, "index_docs": docs_count,
    })


@require_GET
def players(request):
    return JsonResponse({"players": search.player_list()})


@require_POST
def ask(request):
    try:
        body = json.loads(request.body)
        player_id = str(body.get("player_id", "")).strip()
        question = str(body.get("question", "")).strip()
        compare_id = str(body.get("compare_id", "") or "").strip()
        mode = "factcheck" if body.get("mode") == "factcheck" else "ask"
        history = [{"role": str(t.get("role", "")), "content": str(t.get("content", ""))[:2000]}
                   for t in (body.get("history") or [])[-10:] if isinstance(t, dict)]
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "요청 형식이 올바르지 않습니다."}, status=400)
    if not player_id or not question:
        return JsonResponse({"error": "선수와 질문을 모두 입력하세요."}, status=400)

    start = time.time()
    ask_mode = mode
    mode, _ = current_mode()
    if ask_mode == "factcheck" and mode != "RAG":
        return JsonResponse({"error": "사실 확인은 RAG 모드(GMS 키 · 색인 필요)에서만 동작합니다."}, status=503)
    try:
        if mode == "RAG":
            result = rag_service.ask(player_id, question, compare_id, history, ask_mode)
        elif compare_id:
            result = search.ask_compare(player_id, compare_id, question)
        else:
            result = search.ask(player_id, question)
    except Exception:
        # 키 · 프롬프트 · 오류 추적 정보는 화면에 보내지 않는다 (NF2004)
        return JsonResponse({"error": "답변을 만들지 못했습니다. 잠시 후 다시 시도하세요."}, status=500)

    numbers = {int(n) for group in CITE_PATTERN.findall(result["answer"]) for n in group.split(",") if n.strip().isdigit()}
    return JsonResponse({
        "answer": result["answer"],
        # 근거 원문 미리보기(A3): 실제 인용한 근거만 본문을 함께 보낸다 (최대 1,500자)
        "sources": [{**{k: s[k] for k in ("n", "title", "url", "source")},
                     **({"text": s.get("text", "")[:1500]} if s["n"] in numbers else {})} for s in result["sources"]],
        "cited": sorted(numbers),
        "steps": result["steps"],
        "collected": result.get("collected", []),
        "verdict": result.get("verdict", ""),
        "check": result.get("check", {}),          # 문장별 근거 점검 (C1)
        "mode": mode,
        "elapsed": round(time.time() - start, 2),
    })


@require_POST
def explore(request):
    try:
        condition = str(json.loads(request.body).get("condition", "")).strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "요청 형식이 올바르지 않습니다."}, status=400)
    if not condition:
        return JsonResponse({"error": "찾을 조건을 입력하세요."}, status=400)
    mode, notice = current_mode()
    if mode != "RAG":
        return JsonResponse({"error": notice + " (조건 탐색은 RAG 모드에서만 동작합니다)"}, status=503)
    start = time.time()
    try:
        result = rag_service.explore(condition)
    except Exception:
        return JsonResponse({"error": "조건 탐색에 실패했습니다. 잠시 후 다시 시도하세요."}, status=500)
    return JsonResponse({"cards": result["cards"], "candidates": result["candidates"], "rule": result.get("rule", False),
                         "elapsed": round(time.time() - start, 2)})


@require_POST
def lab(request):
    """RAG 실험실 — 같은 질문을 검색 설정 2가지로 실행 (청크 크기 · Top-k · 유사도/MMR · λ)"""
    try:
        body = json.loads(request.body)
        player_id = str(body.get("player_id", "")).strip()
        question = str(body.get("question", "")).strip()
        configs = [c for c in (body.get("configs") or []) if isinstance(c, dict)][:2]
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "요청 형식이 올바르지 않습니다."}, status=400)
    if not player_id or not question or len(configs) != 2:
        return JsonResponse({"error": "선수 · 질문 · 설정 2개가 필요합니다."}, status=400)
    mode, notice = current_mode()
    if mode != "RAG":
        return JsonResponse({"error": notice + " (실험실은 RAG 모드에서만 동작합니다)"}, status=503)
    start = time.time()
    try:
        from rag.lab import run
        result = run(player_id, question, configs)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=404)
    except Exception:
        return JsonResponse({"error": "실험을 실행하지 못했습니다. 잠시 후 다시 시도하세요."}, status=500)
    return JsonResponse({**result, "elapsed": round(time.time() - start, 2)})


@require_POST
def ask_stream(request):
    """답변 스트리밍 (B4) — 한 줄에 JSON 하나(NDJSON): {"type": "evidence"|"token"|"final"|"error", ...}
    RAG 모드에서만. 응답 형식의 final 은 /api/ask 응답과 같다."""
    try:
        body = json.loads(request.body)
        player_id = str(body.get("player_id", "")).strip()
        question = str(body.get("question", "")).strip()
        compare_id = str(body.get("compare_id", "") or "").strip()
        ask_mode = "factcheck" if body.get("mode") == "factcheck" else "ask"
        history = [{"role": str(t.get("role", "")), "content": str(t.get("content", ""))[:2000]}
                   for t in (body.get("history") or [])[-10:] if isinstance(t, dict)]
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "요청 형식이 올바르지 않습니다."}, status=400)
    if not player_id or not question:
        return JsonResponse({"error": "선수와 질문을 모두 입력하세요."}, status=400)
    mode, notice = current_mode()
    if mode != "RAG":
        return JsonResponse({"error": notice}, status=503)

    def events():
        start = time.time()
        line = lambda obj: json.dumps(obj, ensure_ascii=False) + "\n"
        try:
            for kind, payload in rag_service.stream(player_id, question, compare_id, history, ask_mode):
                if kind == "evidence":
                    yield line({"type": "evidence", **payload})
                elif kind == "token":
                    yield line({"type": "token", "text": payload})
                else:
                    numbers = {int(n) for g in CITE_PATTERN.findall(payload["answer"]) for n in g.split(",") if n.strip().isdigit()}
                    yield line({"type": "final", "answer": payload["answer"],
                                "sources": [{**{k: x[k] for k in ("n", "title", "url", "source")},
                                             **({"text": x.get("text", "")[:1500]} if x["n"] in numbers else {})} for x in payload["sources"]],
                                "cited": sorted(numbers), "steps": payload["steps"], "collected": payload.get("collected", []),
                                "verdict": payload.get("verdict", ""), "check": payload.get("check", {}), "mode": mode, "elapsed": round(time.time() - start, 2)})
        except Exception:
            # 오류 추적 정보는 보내지 않는다 (NF2004)
            yield line({"type": "error", "error": "답변을 만들지 못했습니다. 잠시 후 다시 시도하세요."})

    response = StreamingHttpResponse(events(), content_type="application/x-ndjson; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response
