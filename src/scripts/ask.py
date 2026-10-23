# 확인용 CLI — 선수 1명 + 질문 1개 → 답변과 인용 근거
#   python -m scripts.ask ryuhy01 "2019년에 평균자책점이 FIP보다 훨씬 낮았던 이유는?"
#   python -m scripts.ask ryuhy01 "2019 시즌 비교" --compare kershcl01   # 두 선수 비교 (F2010)
#   python -m scripts.ask ryuhy01 "부상 이력" --search-compare   # 위키 근거: 유사도 검색 vs MMR 비교 (F2014)
#   python -m scripts.ask --graph        # 그래프 구조 출력

import sys
import time

from rag import config as C
from rag.graph import build_graph
from rag.indexer import get_collections


def main():
    graph = build_graph()
    if sys.argv[1:] == ["--graph"]:
        print(graph.get_graph().draw_mermaid())
        return
    args = sys.argv[1:]
    compare_id = ""
    if "--compare" in args:
        i = args.index("--compare")
        compare_id = args[i + 1]
        args = args[:i] + args[i + 2:]
    search_compare = "--search-compare" in args
    args = [x for x in args if x != "--search-compare"]
    if len(args) != 2:
        raise SystemExit('사용법: python -m scripts.ask <player_id> "<질문>" [--compare <player_id>]')
    if not C.GMS_KEY:
        raise SystemExit(".env 에 GMS_KEY 가 없습니다.")
    meta_col, docs_col = get_collections()
    print(f"색인 건수 — player_meta {meta_col.count():,} · player_docs {docs_col.count():,}")
    if meta_col.count() == 0:
        raise SystemExit("색인이 비어 있습니다. python -m rag.indexer 를 먼저 실행하세요.")

    if search_compare:
        compare_search(args[0], args[1])
        return

    start = time.time()
    state = graph.invoke({"player_id": args[0], "compare_id": compare_id, "question": args[1]})
    print(f"\n선수: {state['player_name']} · 검색어: {state['queries']}")
    print("\n검색된 근거")
    for e in state["evidence"]:
        dist = "항상 포함" if e["distance"] is None else f"거리 {e['distance']:.3f}"
        print(f"  [근거 {e['n']}] {e['source']} · {e['title']} · {dist}")
    print(f"\n답변 ({time.time() - start:.1f}초)\n{state['answer']}")
    print("\n인용된 근거")
    if not state["cited"]:
        print("  (인용된 근거가 없습니다)")
    for e in state["cited"]:
        print(f"  [근거 {e['n']}] {e['source']} · {e['title']} · {e['url']}")



def compare_search(player_id, question):
    """같은 질문으로 위키 근거를 유사도 검색과 MMR 로 각각 골라 나란히 출력 (F2014)"""
    from rag.graph import llm, parse_json_array, redundancy_of, search_wiki, stores
    from rag import prompts as P
    meta_col, docs_col, embeddings = stores()
    m = meta_col.get(ids=[player_id], include=["metadatas"])["metadatas"][0]
    reply = llm().invoke([("system", P.KEYWORD_SYSTEM),
                          ("user", P.KEYWORD_USER.format(player_name=f"{m['name_ko']} ({m['name_en']})", history="", question=question))])
    queries = [q for q in parse_json_array(reply.content) if isinstance(q, str)][:3] + [question]
    vectors = embeddings.embed_documents(queries)
    where = {"$and": [{"player_id": player_id}, {"doc_type": "wiki"}]}
    print(f"검색어: {queries}\nMMR: 후보 {C.MMR_FETCH_K}개 중 {C.TOP_K_WIKI}개, λ={C.MMR_LAMBDA}")
    for mode in ("similarity", "mmr"):
        picked = search_wiki(docs_col, vectors, where, C.TOP_K_WIKI, mode=mode)
        overlap = redundancy_of(docs_col, [e["id"] for e in picked])
        print(f"\n[{mode}] 근거끼리 평균 유사도 {overlap:.3f} (낮을수록 다양)")
        for e in picked:
            first = e["text"].split("\n", 1)[-1][:70].replace("\n", " ")
            print(f"  거리 {e['distance']:.3f} · {e['id']} · {first}")


if __name__ == "__main__":
    main()
