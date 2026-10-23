# RAG 그래프 연결 (rag/ 패키지) — 화면 API 형식(answer · sources · steps)으로 바꿔 돌려준다
# rag 패키지는 처음 쓸 때 불러온다 (키가 없을 때도 화면은 기록 검색 모드로 뜨게)

from functools import lru_cache


def key_ready():
    from rag import config as C
    return bool(C.GMS_KEY)


def index_counts():
    """(player_meta 건수, player_docs 건수). 색인 폴더가 없거나 열 수 없으면 (0, 0)"""
    try:
        from rag.indexer import get_collections
        meta, docs = get_collections()
        return meta.count(), docs.count()
    except Exception:
        return 0, 0


@lru_cache(maxsize=1)
def graph():
    from rag.graph import build_graph
    return build_graph()


def collection_steps(collection):
    """질문 시 보충 수집 결과 → 진행 상태 문구 (F2012: 수집된 문서 제목을 함께 보여 줌)"""
    steps = []
    for c in collection:
        if c.get("error"):
            steps.append(f"문서 수집({c['player']}): 위키 호출 실패, 기존 색인으로 답함")
        elif c.get("searched"):
            line = (f"문서 수집({c['player']}): 새 검색어 {len(c['searched'])} · 후보 {len(c['candidates'])} · "
                    f"선별 {len(c['selected'])}건")
            if c["selected"]:
                line += " — " + ", ".join(c["selected"])
            steps.append(line)
        elif c.get("skipped"):
            steps.append(f"문서 수집({c['player']}): 이미 수집한 검색어라 건너뜀")
    return steps


def steps_of(state):
    evidence = state.get("evidence", [])
    kinds = {}
    for e in evidence:
        kinds[e["source"]] = kinds.get(e["source"], 0) + 1
    steps = ["검색어: " + ", ".join(state.get("queries", [])[:-1] or ["(원 질문만)"])]
    steps += collection_steps(state.get("collection", []))
    steps.append("근거 " + " · ".join(f"{k} {v}" for k, v in kinds.items()))
    return steps


def result_of(state):
    evidence = state.get("evidence", [])
    return {
        "answer": state.get("answer", ""),
        "sources": [{"n": e["n"], "title": e["title"], "url": e["url"], "source": e["source"], "text": e["text"]} for e in evidence],
        "steps": steps_of(state),
        "collected": [t for c in state.get("collection", []) for t in c.get("selected", [])],
        "verdict": state.get("verdict", ""),
        "check": state.get("check") or {},
    }


def stream(player_id, question, compare_id="", history=None, mode="ask"):
    """답변 스트리밍 (B4) — LangGraph stream 으로 retrieve 결과(근거 · 진행 상태)를 먼저, generate 노드의 글자를 생성되는 대로 낸다.
    ("evidence", {steps, sources}) → ("token", "글자") … → ("final", 결과)"""
    state = {}
    inputs = {"player_id": player_id, "compare_id": compare_id, "question": question, "history": history or [], "mode": mode}
    for kind, chunk in graph().stream(inputs, stream_mode=["updates", "messages"]):
        if kind == "updates":
            for node, update in chunk.items():
                state.update(update or {})
                if node == "retrieve":
                    yield "evidence", {"steps": steps_of(state),
                                       "sources": [{"n": e["n"], "title": e["title"], "url": e["url"], "source": e["source"]}
                                                   for e in state.get("evidence", [])]}
        elif kind == "messages":
            message, meta = chunk
            if meta.get("langgraph_node") == "generate" and getattr(message, "content", ""):
                yield "token", message.content
    yield "final", result_of(state)


def ask(player_id, question, compare_id="", history=None, mode="ask"):
    state = graph().invoke({"player_id": player_id, "compare_id": compare_id, "question": question,
                            "history": history or [], "mode": mode})
    steps = steps_of(state)
    evidence = state.get("evidence", [])
    return {
        "answer": state.get("answer", ""),
        "sources": [{"n": e["n"], "title": e["title"], "url": e["url"], "source": e["source"], "text": e["text"]} for e in evidence],
        "steps": steps,
        "collected": [t for c in state.get("collection", []) for t in c.get("selected", [])],
        "verdict": state.get("verdict", ""),
        "check": state.get("check") or {},
    }


def explore(condition):
    from rag.explore import explore as run
    return run(condition)
