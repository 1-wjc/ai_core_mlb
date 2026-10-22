# RAG 실험실 — 같은 질문을 검색 설정 두 가지로 나란히 실행해 근거 · 답변 차이를 본다 (명세서 1.1 목표: 청크 크기 · Top-k · 검색 다양성)
#   - 검색어(프롬프트 1)는 한 번만 만들어 두 설정에 똑같이 쓴다 (설정 차이만 비교되게)
#   - 청크 크기를 바꾸면 그 선수의 위키 문서만 메모리 임시 컬렉션에 다시 청킹 · 임베딩한다 (본 색인은 그대로)
#   - 보충 수집(F2004)은 하지 않는다

import re
import time

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag import config as C
from rag import prompts as P
from rag.graph import (CITE, drop_cites_on_unconfirmed, find_metrics, llm, metric_evidence, parse_json_array,
                       redundancy_of, search, search_mmr, stores)
from rag.indexer import wiki_chunks

import glob
import os

CHUNK_OPTIONS = {"1000/200": (1000, 200), "500/100": (500, 100), "2000/300": (2000, 300)}
_temp = {"client": None, "collections": {}}


def temp_collection(player_id, chunk):
    """다른 청크 설정의 위키 청크를 메모리 컬렉션에 만든다 (선수 · 설정별로 한 번만). 반환: (컬렉션, 청크 수)"""
    key = (player_id, chunk)
    if key in _temp["collections"]:
        return _temp["collections"][key]
    if _temp["client"] is None:
        _temp["client"] = chromadb.EphemeralClient()
    size, overlap = CHUNK_OPTIONS[chunk]
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", f"lab_{player_id}_{size}_{overlap}")
    col = _temp["client"].get_or_create_collection(name, metadata={"hnsw:space": "cosine"})
    files = sorted(glob.glob(os.path.join(C.WIKI_DOCS_DIR, f"{player_id}_*.json")))
    chunks = wiki_chunks(player_id, files, RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap))
    _, _, embeddings = stores()
    for i in range(0, len(chunks), C.EMBED_BATCH):
        part = chunks[i:i + C.EMBED_BATCH]
        col.upsert(ids=[c["id"] for c in part], documents=[c["text"] for c in part],
                   embeddings=embeddings.embed_documents([c["text"] for c in part]), metadatas=[c["meta"] for c in part])
    _temp["collections"][key] = (col, len(chunks))
    return col, len(chunks)


def run(player_id, question, configs):
    meta_col, docs_col, embeddings = stores()
    got = meta_col.get(ids=[player_id], include=["documents", "metadatas"])
    if not got["ids"]:
        raise ValueError("선수를 찾을 수 없습니다.")
    m = got["metadatas"][0]
    player_name = f"{m['name_ko']} ({m['name_en']})"
    meta_ev = {"id": player_id, "source": "메타데이터", "title": m["title"], "url": m["url"],
               "text": got["documents"][0], "distance": None}

    reply = llm().invoke([("system", P.KEYWORD_SYSTEM),
                          ("user", P.KEYWORD_USER.format(player_name=player_name, history="", question=question))])
    queries = [q for q in parse_json_array(reply.content) if isinstance(q, str) and q.strip()][:3] + [question]
    vectors = embeddings.embed_documents(queries)
    years = sorted({int(y) for y in re.findall(r"(?:19|20)\d{2}", question)})
    metric_ids = find_metrics(queries)

    results = []
    for cfg in configs:
        start = time.time()
        chunk = cfg.get("chunk") if cfg.get("chunk") in CHUNK_OPTIONS else "1000/200"
        k_record = max(0, min(int(cfg.get("top_k_record", C.TOP_K_RECORD)), 6))
        k_wiki = max(1, min(int(cfg.get("top_k_wiki", C.TOP_K_WIKI)), 10))
        mode = "mmr" if cfg.get("search_mode") == "mmr" else "similarity"
        lam = max(0.0, min(float(cfg.get("mmr_lambda", C.MMR_LAMBDA)), 1.0))

        record_filter = [{"player_id": player_id}, {"doc_type": {"$ne": "wiki"}}]
        if years:
            record_filter.append({"season": {"$in": years}})
        records = search(docs_col, vectors, {"$and": record_filter}, k_record) if k_record else []

        if chunk == "1000/200":
            wiki_col = docs_col
            chunk_count = len(wiki_col.get(where={"$and": [{"player_id": player_id}, {"doc_type": "wiki"}]}, include=[])["ids"])
        else:
            wiki_col, chunk_count = temp_collection(player_id, chunk)
        where = {"$and": [{"player_id": player_id}, {"doc_type": "wiki"}]}
        wiki = (search_mmr(wiki_col, vectors, where, k_wiki, lam=lam) if mode == "mmr"
                else search(wiki_col, vectors, where, k_wiki))

        evidence = [dict(meta_ev)] + records + wiki + metric_evidence(docs_col, metric_ids)
        for n, e in enumerate(evidence, 1):
            e["n"] = n
        blocks = [f"[근거 {e['n']}] (출처 유형: {e['source']} · {e['title']})\n{e['text']}" for e in evidence]
        answer = llm().invoke([("system", P.ANSWER_SYSTEM),
                               ("user", P.ANSWER_USER.format(player_name=player_name, history="",
                                                             evidence="\n\n".join(blocks), question=question))]).content
        answer = drop_cites_on_unconfirmed(answer)
        cited = sorted({int(n) for g in CITE.findall(answer) for n in g.split(",") if n.strip().isdigit()})
        results.append({
            "config": {"chunk": chunk, "top_k_record": k_record, "top_k_wiki": k_wiki, "search_mode": mode, "mmr_lambda": lam},
            "wiki_chunks_total": chunk_count,
            "wiki_redundancy": redundancy_of(wiki_col, [e["id"] for e in wiki]),
            "evidence": [{"n": e["n"], "source": e["source"], "title": e["title"], "url": e["url"],
                          "distance": None if e["distance"] is None else round(e["distance"], 3),
                          "snippet": e["text"].split("\n", 1)[-1][:160]} for e in evidence],
            "answer": answer, "cited": cited, "elapsed": round(time.time() - start, 2),
        })
    return {"player_name": player_name, "queries": queries, "results": results}
