# 확인용 CLI — 선수 1명 + 질문 1개 → 답변과 인용 근거
#   python -m scripts.ask ryuhy01 "2019년에 평균자책점이 FIP보다 훨씬 낮았던 이유는?"
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
    if len(sys.argv) != 3:
        raise SystemExit('사용법: python -m scripts.ask <player_id> "<질문>"')
    if not C.GMS_KEY:
        raise SystemExit(".env 에 GMS_KEY 가 없습니다.")
    meta_col, docs_col = get_collections()
    print(f"색인 건수 — player_meta {meta_col.count():,} · player_docs {docs_col.count():,}")
    if meta_col.count() == 0:
        raise SystemExit("색인이 비어 있습니다. python -m rag.indexer 를 먼저 실행하세요.")

    start = time.time()
    state = graph.invoke({"player_id": sys.argv[1], "question": sys.argv[2]})
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


if __name__ == "__main__":
    main()
