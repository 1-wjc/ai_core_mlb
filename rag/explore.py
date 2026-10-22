# 조건 기반 항목 탐색 (F2011)
#   자연어 조건 → 메타데이터 컬렉션(player_meta)에서 후보 → 프롬프트 2(조건 선별)로 조건에 맞는 선수만 → 카드
#   - 숫자 조건("홈런 400개 이상", "ERA+ 130 이상" 등)은 규칙으로 읽어 메타데이터 필터로 후보를 먼저 거른다
#     (임베딩은 숫자 크기를 구분하지 못하므로). 나머지 조건은 의미 유사도로 후보를 모은다.
#   - 투타 · 출신 국가 · 수상처럼 글자로 확인되는 조건은 색인 텍스트에 그 글자가 있는 후보만 남긴다 (where_document).
#   - 후보 요약(색인 텍스트)에 통산 기록 · 수상 · 특징이 들어 있어 LLM 이 조건 충족을 확인한다.

import re

from rag import config as C
from rag import prompts as P
from rag.graph import llm, parse_json_array, stores

# 조건 표현 → 메타데이터 필드 (색인 시 player_meta 에 저장한 통산 값)
NUMERIC_FIELDS = [
    (r"OPS\+", "bat_OPS_plus"), (r"OPS", "bat_OPS"), (r"타율", "bat_AVG"), (r"홈런", "bat_HR"), (r"도루", "bat_SB"),
    (r"타석", "bat_PA"), (r"ERA\+", "pit_ERA_plus"), (r"평균자책점|ERA", "pit_ERA"), (r"FIP", "pit_FIP"),
    (r"세이브", "pit_SV"), (r"탈삼진", "pit_SO"), (r"(?<![가-힣])승", "pit_W"),
]
# 조건 표현 → 색인 텍스트에 반드시 들어 있어야 하는 글자
TEXT_RULES = [
    (r"좌타", "좌타"), (r"우타", "우타"), (r"양타|스위치 ?히터", "양타"), (r"좌투|좌완", "좌투"), (r"우투|우완", "우투"),
    (r"한국|대한민국", "출신 대한민국"), (r"일본", "출신 일본"), (r"도미니카", "출신 도미니카 공화국"),
    (r"베네수엘라", "출신 베네수엘라"), (r"쿠바", "출신 쿠바"), (r"푸에르토리코", "출신 푸에르토리코"),
    (r"멕시코", "출신 멕시코"), (r"캐나다", "출신 캐나다"), (r"대만", "출신 대만"), (r"미국 (?:출신|선수)", "출신 미국"),
    (r"사이영", "사이영상"), (r"신인왕", "신인왕"), (r"골드 ?글러브", "골드글러브"), (r"실버 ?슬러거", "실버슬러거"),
    (r"명예의 ?전당", "명예의 전당"), (r"투타 ?겸업", "투타겸업"), (r"월드시리즈 우승", "월드시리즈 우승"),
]
NUMBER = r"\s*(?:은|는|이|가)?\s*(\d+(?:\.\d+)?)\s*(?:개|승|회|이닝)?\s*(이상|이하|초과|미만|넘는|넘게|넘|보다 많|보다 적)?"


def numeric_filters(condition):
    """'통산 홈런 400개 이상' → [{"bat_HR": {"$gte": 400}}]"""
    filters = []
    taken = set()
    for pattern, field in NUMERIC_FIELDS:
        for m in re.finditer(pattern + NUMBER, condition):
            if m.start() in taken:
                continue
            taken.update(range(m.start(), m.end()))
            value = float(m.group(1))
            word = m.group(2) or "이상"
            op = {"이상": "$gte", "초과": "$gt", "넘는": "$gt", "넘게": "$gt", "넘": "$gt", "보다 많": "$gt",
                  "이하": "$lte", "미만": "$lt", "보다 적": "$lt"}[word]
            if field in ("bat_AVG", "bat_OPS") and value >= 1 and "." not in m.group(1):
                value = value / 1000                       # "타율 300 이상" → .300
            filters.append({field: {op: value}})
    return filters


def text_filters(condition):
    """'사이영상을 받은 좌투수' → ["사이영상", "좌투"]"""
    return [needle for pattern, needle in TEXT_RULES if re.search(pattern, condition)]


# 이유 문장에 불충족을 밝힌 판정은 뺀다 (LLM 이 match 를 잘못 달았을 때의 안전장치)
NEGATIVE = re.compile(r"불충족|충족하지|충족되지|만족하지|않[는아]|아니")


def explore(condition):
    meta_col, _, embeddings = stores()
    filters = numeric_filters(condition)
    texts = text_filters(condition)
    where = None if not filters else (filters[0] if len(filters) == 1 else {"$and": filters})
    contains = [{"$contains": t} for t in texts]
    where_document = None if not contains else (contains[0] if len(contains) == 1 else {"$and": contains})
    result = meta_col.query(query_embeddings=[embeddings.embed_query(condition)], n_results=C.EXPLORE_CANDIDATES,
                            where=where, where_document=where_document, include=["documents", "metadatas"])
    candidates = list(zip(result["ids"][0], result["documents"][0], result["metadatas"][0]))
    if not candidates:
        return {"cards": [], "candidates": 0, "filters": filters, "texts": texts}

    listing = "\n".join(f"{i}. {doc}" for i, (_, doc, _) in enumerate(candidates, 1))
    reply = llm().invoke([
        ("system", P.EXPLORE_SYSTEM.format(max_pick=C.EXPLORE_MAX_PICK)),
        ("user", P.EXPLORE_USER.format(condition=condition, candidates=listing)),
    ])
    cards, seen = [], set()
    for item in parse_json_array(reply.content):
        if not isinstance(item, dict) or item.get("match") is not True or not isinstance(item.get("n"), int):
            continue                                       # 조건 충족으로 판정한 후보만
        if NEGATIVE.search(str(item.get("reason", ""))):
            continue
        n = item["n"]
        if not 1 <= n <= len(candidates) or n in seen:
            continue
        seen.add(n)
        pid, _, m = candidates[n - 1]
        cards.append({
            "player_id": pid, "name_ko": m.get("name_ko", ""), "name_en": m.get("name_en", ""),
            "role": m.get("role", ""), "position": m.get("primary_position", ""),
            "first_season": m.get("first_season"), "last_season": m.get("last_season"),
            "reason": str(item.get("reason", "")),
        })
    return {"cards": cards[:C.EXPLORE_MAX_PICK], "candidates": len(candidates), "filters": filters, "texts": texts}
