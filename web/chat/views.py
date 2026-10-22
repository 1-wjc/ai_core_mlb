# JSON API (화면은 chat/pages.py)
#   GET  /api/status   → {"mode": "RAG"|"기록 검색", "players", "record_docs", "index_meta", "index_docs", "key_ready", "notice"}
#   GET  /api/players  → {"players": [{player_id, name_ko, name_en, role, position, first_season, last_season}]}
#   POST /api/ask      ← {"player_id": "ryuhy01", "question": "...", "compare_id": "kershcl01"(선택, F2010),
#                         "history": [{"role": "user"|"assistant", "content": "..."}](선택, F2009 직전 대화)}
#                      → {"answer", "sources": [{n, title, url, source}], "cited": [n, ...], "steps": [...],
#                         "collected": [질문 시 새로 수집한 문서 제목], "mode", "elapsed"}
#   POST /api/explore  ← {"condition": "통산 홈런 400개 이상인 좌타자"}   (F2011 조건 탐색, RAG 모드 전용)
#                      → {"cards": [{player_id, name_ko, name_en, role, position, first_season, last_season, reason}],
#                         "candidates": 후보 수, "elapsed"}
#
# 모드: GMS 키와 색인이 있으면 RAG(rag/graph.py), 없으면 기록 검색(chat/search.py, LLM 미사용)으로 대신 답한다.

import json
import re
import time

from django.http import JsonResponse
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
        history = [{"role": str(t.get("role", "")), "content": str(t.get("content", ""))[:2000]}
                   for t in (body.get("history") or [])[-10:] if isinstance(t, dict)]
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "요청 형식이 올바르지 않습니다."}, status=400)
    if not player_id or not question:
        return JsonResponse({"error": "선수와 질문을 모두 입력하세요."}, status=400)

    start = time.time()
    mode, _ = current_mode()
    try:
        if mode == "RAG":
            result = rag_service.ask(player_id, question, compare_id, history)
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
        "sources": [{k: s[k] for k in ("n", "title", "url", "source")} for s in result["sources"]],
        "cited": sorted(numbers),
        "steps": result["steps"],
        "collected": result.get("collected", []),
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
    return JsonResponse({"cards": result["cards"], "candidates": result["candidates"],
                         "elapsed": round(time.time() - start, 2)})
