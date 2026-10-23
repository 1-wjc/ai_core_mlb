# 조건 기반 항목 탐색 (F2011)
#   자연어 조건 → 메타데이터 컬렉션(player_meta)에서 후보 → 프롬프트 2(조건 선별)로 조건에 맞는 선수만 → 카드
#   - 숫자 조건("홈런 400개 이상", "ERA+ 130 이상" 등)은 규칙으로 읽어 메타데이터 필터로 후보를 먼저 거른다
#     (임베딩은 숫자 크기를 구분하지 못하므로). 나머지 조건은 의미 유사도로 후보를 모은다.
#   - 투타 · 출신 국가 · 수상처럼 글자로 확인되는 조건은 색인 텍스트에 그 글자가 있는 후보만 남긴다 (where_document).
#   - 후보 요약(색인 텍스트)에 통산 기록 · 수상 · 특징이 들어 있어 LLM 이 조건 충족을 확인한다.
#   - 조건 전체가 위 규칙(숫자 · 투타 · 국가 · 수상)만으로 표현되면 LLM 판정 없이 필터를 통과한 선수를 전부 돌려준다
#     (LLM 이 맞는 후보를 빼거나 상한에 잘리던 문제 — 예: 세이브 300개 이상에서 호프먼 누락)

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
    (r"사이영(?:상)?", "사이영상"), (r"신인왕", "신인왕"), (r"골드 ?글러브", "골드글러브"), (r"실버 ?슬러거", "실버슬러거"),
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


# 규칙으로 읽은 부분을 지운 뒤 남는 조사 · 군더더기 (이것만 남으면 규칙만으로 표현된 조건)
FILLER = re.compile(r"통산|커리어|이상|이하|초과|미만|넘는|넘게|기록한|기록|수상한|수상|받은|출신|선수|투수|타자|"
                    r"있는|오른|올라간|든|그리고|및|개|승|회|이닝|인|은|는|이|가|을|를|의|에|과|와|한|자|수|\d+(?:\.\d+)?|[\s,.·]")


def rule_only(condition):
    """조건이 숫자 · 글자 규칙만으로 모두 표현되는지 — '통산 홈런 500개 이상인 우타자' True, '도미니카 출신 파워 히터' False"""
    rest = condition
    for pattern, _ in NUMERIC_FIELDS:
        rest = re.sub(pattern + NUMBER, " ", rest)
    for pattern, _ in TEXT_RULES:
        rest = re.sub(pattern, " ", rest)
    return not FILLER.sub("", rest)


def text_filters(condition):
    """'사이영상을 받은 좌투수' → ["사이영상", "좌투"]"""
    return [needle for pattern, needle in TEXT_RULES if re.search(pattern, condition)]


# 카드 문구 — 규칙으로 읽은 조건은 LLM 문장 대신 코드로 "통산 세이브 310개"처럼 값만 표시 (깨진 글자 · 군더더기 방지)
FIELD_LABELS = {
    "bat_OPS_plus": ("통산 OPS+", "{:.0f}"), "bat_OPS": ("통산 OPS", "{:.3f}"), "bat_AVG": ("통산 타율", "{:.3f}"),
    "bat_HR": ("통산 홈런", "{:,.0f}개"), "bat_SB": ("통산 도루", "{:,.0f}개"), "bat_PA": ("통산", "{:,.0f}타석"),
    "pit_ERA_plus": ("통산 ERA+", "{:.0f}"), "pit_ERA": ("통산 평균자책점", "{:.2f}"), "pit_FIP": ("통산 FIP", "{:.2f}"),
    "pit_SV": ("통산 세이브", "{:,.0f}개"), "pit_SO": ("통산 탈삼진", "{:,.0f}개"), "pit_W": ("통산", "{:,.0f}승"),
}


def card_reason(meta, filters, texts):
    """조건에 쓰인 값만 짧게 — 예: "우타 · 통산 홈런 609개". 규칙 조건이 없으면 빈 문자열"""
    parts = [("출신 " not in t and t) or t.replace("출신 ", "") + " 출신" for t in texts]
    for f in filters:
        field = next(iter(f))
        label, form = FIELD_LABELS[field]
        value = meta.get(field)
        if value is not None:
            text = form.format(value)
            parts.append(f"{label} {text.lstrip('0') if text.startswith('0.') else text}")
    return " · ".join(parts)


# LLM 문구를 쓸 때(규칙 조건이 없을 때) 한글 · 영문 · 숫자 · 기본 문장부호 밖의 글자는 지운다
STRAY = re.compile(r"[^가-힣ㄱ-ㆎA-Za-z0-9\s.,·%+()\-/:]")


# 이유 문장에 불충족을 밝힌 판정은 뺀다 (LLM 이 match 를 잘못 달았을 때의 안전장치)
NEGATIVE = re.compile(r"불충족|충족하지|충족되지|만족하지|않[는아]|아니")


def card_of(pid, m, reason):
    return {"player_id": pid, "name_ko": m.get("name_ko", ""), "name_en": m.get("name_en", ""),
            "role": m.get("role", ""), "position": m.get("primary_position", ""),
            "first_season": m.get("first_season"), "last_season": m.get("last_season"), "reason": reason}


def by_recent(cards):
    """최근 선수부터 (마지막 활약 연도, 같으면 이름순)"""
    return sorted(cards, key=lambda c: (-(c["last_season"] or 0), c["name_en"]))


def explore(condition):
    meta_col, _, embeddings = stores()
    filters = numeric_filters(condition)
    texts = text_filters(condition)
    where = None if not filters else (filters[0] if len(filters) == 1 else {"$and": filters})
    contains = [{"$contains": t} for t in texts]
    where_document = None if not contains else (contains[0] if len(contains) == 1 else {"$and": contains})

    if (filters or texts) and rule_only(condition):
        # 규칙만으로 표현된 조건 → 필터를 통과한 선수 전부 (LLM 판정 없음, 상한 없음). get 은 500건씩 나눠 읽음
        cards, offset = [], 0
        while True:
            got = meta_col.get(where=where, where_document=where_document, include=["metadatas"], limit=500, offset=offset)
            cards += [card_of(pid, m, card_reason(m, filters, texts)) for pid, m in zip(got["ids"], got["metadatas"])]
            if len(got["ids"]) < 500:
                break
            offset += 500
        return {"cards": by_recent(cards), "candidates": len(cards), "filters": filters, "texts": texts, "rule": True}
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
        cards.append(card_of(pid, m, card_reason(m, filters, texts) or STRAY.sub("", str(item.get("reason", ""))).strip()))
    return {"cards": by_recent(cards[:C.EXPLORE_MAX_PICK]), "candidates": len(candidates), "filters": filters, "texts": texts,
            "rule": False}
