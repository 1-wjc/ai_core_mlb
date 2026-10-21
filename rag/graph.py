# LangGraph — retrieve → generate 2노드 (F2006 · F2007 · F2008)

import json
import re
from functools import lru_cache
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from rag import config as C
from rag import prompts as P
from rag.indexer import get_collections, get_embeddings


class State(TypedDict, total=False):
    player_id: str
    question: str
    player_name: str
    queries: list          # 프롬프트 1 이 만든 검색어
    evidence: list         # [{n, source, title, url, text, distance}]
    answer: str
    cited: list            # 답변에서 실제로 인용한 근거


@lru_cache(maxsize=1)
def llm():
    return ChatOpenAI(model=C.CHAT_MODEL, api_key=C.GMS_KEY, base_url=C.GMS_BASE_URL)


@lru_cache(maxsize=1)
def stores():
    meta, docs = get_collections()
    return meta, docs, get_embeddings()


def parse_json_array(text):
    """LLM 출력에서 JSON 배열만 꺼낸다. 실패하면 빈 목록"""
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        return []
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


# ---------------- retrieve ----------------
def retrieve(state: State) -> State:
    meta_col, docs_col, embeddings = stores()
    pid = state["player_id"]
    question = state["question"]

    # 1) 선택 선수 메타데이터 — 검색하지 않고 항상 근거에 넣는다
    got = meta_col.get(ids=[pid], include=["documents", "metadatas"])
    evidence = []
    player_name = pid
    if got["ids"]:
        m = got["metadatas"][0]
        player_name = f"{m['name_ko']} ({m['name_en']})"
        evidence.append({"id": pid, "source": "메타데이터", "title": m["title"], "url": m["url"],
                         "text": got["documents"][0], "distance": None})

    # 2) 프롬프트 1 — 검색어 추출
    reply = llm().invoke([
        ("system", P.KEYWORD_SYSTEM),
        ("user", P.KEYWORD_USER.format(player_name=player_name, question=question)),
    ])
    queries = [q for q in parse_json_array(reply.content) if isinstance(q, str) and q.strip()][:3]
    queries.append(question)                       # 원 질문도 검색어로 사용

    # 3) 외부 문서 — 그 선수 범위(player_id 필터) 안에서 유사도 검색, 병합 · 중복 제거
    best = {}
    vectors = embeddings.embed_documents(queries)
    result = docs_col.query(query_embeddings=vectors, n_results=C.PER_QUERY_K, where={"player_id": pid},
                            include=["documents", "metadatas", "distances"])
    for ids, texts, metas, dists in zip(result["ids"], result["documents"], result["metadatas"], result["distances"]):
        for chunk_id, text, m, dist in zip(ids, texts, metas, dists):
            if chunk_id not in best or dist < best[chunk_id]["distance"]:
                best[chunk_id] = {"id": chunk_id, "source": m["source"], "title": m["title"], "url": m["url"],
                                  "text": text, "distance": dist}
    evidence += sorted(best.values(), key=lambda e: e["distance"])[:C.TOP_K]

    for n, e in enumerate(evidence, 1):
        e["n"] = n
    return {"player_name": player_name, "queries": queries, "evidence": evidence}


# ---------------- generate ----------------
def generate(state: State) -> State:
    evidence = state.get("evidence", [])
    if not evidence:
        return {"answer": "근거 자료가 없어 확인되지 않습니다.", "cited": []}

    blocks = [f"[근거 {e['n']}] (출처 유형: {e['source']} · {e['title']})\n{e['text']}" for e in evidence]
    reply = llm().invoke([
        ("system", P.ANSWER_SYSTEM),
        ("user", P.ANSWER_USER.format(player_name=state["player_name"], evidence="\n\n".join(blocks),
                                      question=state["question"])),
    ])
    answer = reply.content
    numbers = {int(n) for n in re.findall(r"\[근거\s*(\d+)\]", answer)}
    cited = [e for e in evidence if e["n"] in numbers]
    return {"answer": answer, "cited": cited}


def build_graph():
    graph = StateGraph(State)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()
