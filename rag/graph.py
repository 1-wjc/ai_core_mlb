# LangGraph — retrieve → generate 2노드 (F2004 · F2006 · F2007 · F2008 · F2009 · F2010 · F2014 · F2016)

import json
import re
from functools import lru_cache

import numpy as np
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from rag import config as C
from rag import prompts as P
from rag.collector import collect_for_question
from rag.indexer import get_collections, get_embeddings, index_wiki_files
from rag.team_era import era_evidence, find_franchises

VERDICT = re.compile(r"판정\s*[:：]\s*\**\s*(참|거짓|일부 사실|근거 부족)")
CITE = re.compile(r"\[근거\s*([\d,\s]+)\]")


class State(TypedDict, total=False):
    player_id: str
    compare_id: str        # 비교할 선수 (F2010, 없으면 단일 선수 질문)
    mode: str              # "ask"(기본) | "factcheck"(사실 확인, 입력을 주장으로 보고 판정)
    question: str
    history: list          # 직전 대화 [{role: user|assistant, content}] (F2009)
    player_name: str
    queries: list          # 프롬프트 1 이 만든 검색어
    collection: list       # 질문 시 보충 수집 결과 (F2004) — 선수별 요약
    evidence: list         # [{n, source, title, url, text, distance}]
    answer: str
    verdict: str           # 사실 확인 판정 (참 · 거짓 · 일부 사실 · 근거 부족)
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


def history_text(history):
    """직전 대화를 프롬프트에 넣을 글로 — 답변 속 [근거 N] 은 지금 근거 번호와 섞이지 않게 뺀다"""
    turns = (history or [])[-C.HISTORY_TURNS:]
    if not turns:
        return ""
    lines = []
    for t in turns:
        who = "사용자" if t.get("role") == "user" else "답변"
        lines.append(f"{who}: {CITE.sub('', str(t.get('content', '')))[:600].strip()}")
    return "이전 대화\n" + "\n".join(lines) + "\n\n"


# ---------------- 지표 사전 (F2016 세 번째 출처 종류) ----------------
@lru_cache(maxsize=1)
def metric_aliases():
    """[(별칭, metric_id)] — 긴 별칭부터 (예: "피BABIP" 이 "BABIP" 보다 먼저)"""
    with open(C.METRICS_DICT_PATH, encoding="utf-8") as f:
        metrics = json.load(f)["metrics"]
    pairs = [(alias, m["metric_id"]) for m in metrics for alias in m["aliases"]]
    return sorted(pairs, key=lambda x: -len(x[0]))


def find_metrics(texts):
    """질문 · 검색어에 나온 지표 ID (나온 순서, 최대 TOP_K_METRIC 개). 영문 별칭은 단어 경계로만 인정"""
    found = []
    for text in texts:
        masked = text
        for alias, mid in metric_aliases():
            if re.search(r"[A-Za-z]", alias):
                pattern = r"(?<![A-Za-z])" + re.escape(alias) + r"(?![A-Za-z+\-−%/0-9])"
                flags = re.I if len(alias) > 4 else 0
            else:
                pattern, flags = re.escape(alias), 0
            match = re.search(pattern, masked, flags)
            if match:
                masked = masked[:match.start()] + " " * len(alias) + masked[match.end():]   # 짧은 별칭이 다시 걸리지 않게
                if mid not in found:
                    found.append(mid)
    return found[:C.TOP_K_METRIC]


def metric_evidence(docs_col, metric_ids):
    if not metric_ids:
        return []
    got = docs_col.get(ids=[f"_glossary:metric-{mid}:0" for mid in metric_ids], include=["documents", "metadatas"])
    order = {f"_glossary:metric-{mid}:0": i for i, mid in enumerate(metric_ids)}
    items = sorted(zip(got["ids"], got["documents"], got["metadatas"]), key=lambda x: order[x[0]])
    return [{"id": cid, "source": m["source"], "title": m["title"], "url": m["url"], "text": text, "distance": None}
            for cid, text, m in items]


# ---------------- 프롬프트 2: 문서 후보 선별 ----------------
def select_documents(player_name, question, candidates):
    listing = "\n".join(f"{i}. {c['title']} — {c['summary'][:200]}" for i, c in enumerate(candidates, 1))
    reply = llm().invoke([
        ("system", P.SELECT_SYSTEM.format(max_pick=C.COLLECT_MAX_PICK)),
        ("user", P.SELECT_USER.format(player_name=player_name, question=question, candidates=listing)),
    ])
    return [n for n in parse_json_array(reply.content) if isinstance(n, int)]


# ---------------- retrieve ----------------
def retrieve(state: State) -> State:
    meta_col, docs_col, embeddings = stores()
    pid = state["player_id"]
    question = state["question"]

    # 비교 기능(F2010): compare_id 가 있으면 두 선수 범위를 각각 검색한다
    pids = [pid] + ([state["compare_id"]] if state.get("compare_id") and state["compare_id"] != pid else [])

    # 1) 선택 선수 메타데이터 — 검색하지 않고 항상 근거에 넣는다
    names, names_ko, meta_evidence, roles = {}, {}, {}, {}
    for p in pids:
        got = meta_col.get(ids=[p], include=["documents", "metadatas"])
        if got["ids"]:
            m = got["metadatas"][0]
            names[p] = f"{m['name_ko']} ({m['name_en']})"
            names_ko[p] = m["name_ko"]
            roles[p] = (m.get("role", "타자"), bool(m.get("two_way")))
            meta_evidence[p] ={"id": p, "source": "메타데이터", "title": m["title"], "url": m["url"],
                                "text": got["documents"][0], "distance": None}
    pids = [p for p in pids if p in meta_evidence]
    if not pids:                                   # 색인에 없는 선수 → LLM 을 부르지 않고 끝낸다
        return {"player_name": pid, "queries": [], "collection": [], "evidence": []}
    player_name = " vs ".join(names[p] for p in pids)

    # 2) 프롬프트 1 — 검색어 추출 (직전 대화로 "그 해" 같은 표현을 풀어 씀)
    reply = llm().invoke([
        ("system", P.KEYWORD_SYSTEM),
        ("user", P.KEYWORD_USER.format(player_name=player_name, history=history_text(state.get("history")),
                                       question=question)),
    ])
    queries = [q for q in parse_json_array(reply.content) if isinstance(q, str) and q.strip()][:3]

    # 3) 외부 문서 — 선수 범위(player_id 필터) 안에서 유사도 검색
    #    기록 문서 · 위키 문서를 따로 검색해 몫을 나누고, 연도가 있으면 기록 문서는 그 시즌만
    search_queries = queries + [question]          # 원 질문도 검색어로 사용
    vectors = embeddings.embed_documents(search_queries)
    years = sorted({int(y) for y in re.findall(r"(?:19|20)\d{2}", question)})
    wiki_k = C.TOP_K_WIKI if len(pids) == 1 else max(1, C.TOP_K_WIKI // 2)
    evidence, collection = [], []
    metrics_found = find_metrics([question] + queries)
    franchises_found = find_franchises([question] + queries)
    for p in pids:
        evidence.append(meta_evidence[p])
        record_filter = [{"player_id": p}, {"doc_type": {"$ne": "wiki"}}]
        if years:
            record_filter.append({"season": {"$in": years}})
        evidence += search(docs_col, vectors, {"$and": record_filter}, C.TOP_K_RECORD)
        # 구단 시절 합산 (B3) — 질문에 구단이 나오면 그 구단에서 뛴 시즌을 코드로 합산한 근거
        role, two_way = roles[p]
        for fid in franchises_found:
            era = era_evidence(p, names_ko[p], fid, include_batting=role == "타자" or two_way,
                               include_pitching=role == "투수" or two_way)
            if era:
                evidence.append(era)
        wiki_where = {"$and": [{"player_id": p}, {"doc_type": "wiki"}]}
        wiki = search_wiki(docs_col, vectors, wiki_where, wiki_k)

        # 4) 질문 시 보충 수집 (F2004) — 기존 위키 근거가 부족하면 새 검색어로 위키 검색 → 프롬프트 2 선별
        #    → 수집 → 색인 후 다시 검색. 위키 호출이 막혀도 기존 색인으로 답한다.
        best = wiki[0]["distance"] if wiki else 1.0
        need = C.COLLECT_MODE == "always" or (C.COLLECT_MODE == "auto" and best > C.COLLECT_IF_DISTANCE)
        if need and queries:
            try:
                info = collect_for_question(p, names[p], names_ko[p], question, queries,
                                            select_documents, index_wiki_files)
            except Exception as e:
                info = {"error": type(e).__name__}
            collection.append({"player": names_ko[p], "best_distance": round(best, 3), **info})
            if info.get("chunks"):
                wiki = search_wiki(docs_col, vectors, wiki_where, wiki_k)
        evidence += wiki
    # 5) 지표 사전 — 질문 · 검색어에 나온 지표의 정의 · 계산식 (F2016)
    evidence += metric_evidence(docs_col, metrics_found)

    for n, e in enumerate(evidence, 1):
        e["n"] = n
    return {"player_name": player_name, "queries": search_queries, "collection": collection, "evidence": evidence}


def search_wiki(collection, vectors, where, k, mode=None):
    """위키 청크 선택 — SEARCH_MODE 가 mmr 이면 MMR, 아니면 유사도 순 (F2014)"""
    if (mode or C.SEARCH_MODE) == "mmr":
        return search_mmr(collection, vectors, where, k)
    return search(collection, vectors, where, k)


def search_mmr(collection, vectors, where, k, lam=None, fetch_k=None):
    """MMR — 후보를 MMR_FETCH_K 개 넉넉히 가져와, '질문과의 유사도'와 '이미 고른 근거와의 유사도'를
    λ : (1−λ) 로 저울질해 하나씩 고른다. 같은 내용의 청크가 근거에 몰리지 않게 한다."""
    lam = C.MMR_LAMBDA if lam is None else lam
    result = collection.query(query_embeddings=vectors, n_results=fetch_k or C.MMR_FETCH_K, where=where,
                              include=["documents", "metadatas", "distances", "embeddings"])
    pool = {}
    for ids, texts, metas, dists, embs in zip(result["ids"], result["documents"], result["metadatas"],
                                              result["distances"], result["embeddings"]):
        for chunk_id, text, m, dist, emb in zip(ids, texts, metas, dists, embs):
            if chunk_id not in pool or dist < pool[chunk_id]["distance"]:
                pool[chunk_id] = {"id": chunk_id, "source": m["source"], "title": m["title"], "url": m["url"],
                                  "text": text, "distance": dist, "_emb": np.asarray(emb, dtype=float)}
    candidates = list(pool.values())
    if not candidates:
        return []
    relevance = np.array([1 - c["distance"] for c in candidates])             # 코사인 유사도 (검색어 중 최고)
    mat = np.stack([c["_emb"] / np.linalg.norm(c["_emb"]) for c in candidates])
    pairwise = mat @ mat.T
    chosen = [int(np.argmax(relevance))]
    while len(chosen) < min(k, len(candidates)):
        redundancy = pairwise[:, chosen].max(axis=1)
        score = lam * relevance - (1 - lam) * redundancy
        score[chosen] = -np.inf
        chosen.append(int(np.argmax(score)))
    picked = []
    for i in chosen:
        c = dict(candidates[i])
        c.pop("_emb")
        picked.append(c)
    return picked


def redundancy_of(collection, chunk_ids):
    """근거 청크끼리의 평균 코사인 유사도 (낮을수록 다양) — MMR 비교용"""
    if len(chunk_ids) < 2:
        return None
    got = collection.get(ids=chunk_ids, include=["embeddings"])
    mat = np.stack([np.asarray(e, dtype=float) / np.linalg.norm(e) for e in got["embeddings"]])
    sims = mat @ mat.T
    n = len(chunk_ids)
    return float((sims.sum() - n) / (n * (n - 1)))


def search(collection, vectors, where, k):
    """검색어 여러 개로 검색해 병합 · 중복 제거 (같은 청크는 가장 가까운 거리로), 가까운 순 k개"""
    best = {}
    result = collection.query(query_embeddings=vectors, n_results=C.PER_QUERY_K, where=where,
                              include=["documents", "metadatas", "distances"])
    for ids, texts, metas, dists in zip(result["ids"], result["documents"], result["metadatas"], result["distances"]):
        for chunk_id, text, m, dist in zip(ids, texts, metas, dists):
            if chunk_id not in best or dist < best[chunk_id]["distance"]:
                best[chunk_id] = {"id": chunk_id, "source": m["source"], "title": m["title"], "url": m["url"],
                                  "text": text, "distance": dist}
    return sorted(best.values(), key=lambda e: e["distance"])[:k]


# ---------------- generate ----------------
def drop_cites_on_unconfirmed(answer):
    """"확인되지 않는다" 문장 끝에 붙은 [근거 N] 은 뗀다 (근거가 없다는 문장에 근거를 달지 않음)"""
    return re.sub(r"(확인되지 않[^.\n]*?[.。])\s*((?:\[근거\s*[\d,\s]+\]\s*)+)", r"\1 ", answer).strip()


def generate(state: State) -> State:
    evidence = state.get("evidence", [])
    if not evidence:
        return {"answer": "선택한 선수의 근거 자료가 없어 확인되지 않습니다.", "cited": []}

    blocks = [f"[근거 {e['n']}] (출처 유형: {e['source']} · {e['title']})\n{e['text']}" for e in evidence]
    system = P.ANSWER_SYSTEM + (P.COMPARE_RULES if state.get("compare_id") else "")
    if state.get("mode") == "factcheck":
        system += P.FACTCHECK_RULES
    reply = llm().invoke([
        ("system", system),
        ("user", P.ANSWER_USER.format(player_name=state["player_name"], history=history_text(state.get("history")),
                                      evidence="\n\n".join(blocks), question=state["question"])),
    ])
    answer = drop_cites_on_unconfirmed(reply.content)
    numbers = {int(n) for group in CITE.findall(answer) for n in group.split(",") if n.strip().isdigit()}
    cited = [e for e in evidence if e["n"] in numbers]
    verdict = ""
    if state.get("mode") == "factcheck":
        m = VERDICT.search(answer)
        verdict = m.group(1) if m else "근거 부족"
    return {"answer": answer, "cited": cited, "verdict": verdict}


def build_graph():
    graph = StateGraph(State)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()
