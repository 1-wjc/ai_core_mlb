# 기록 검색 (초기 버전 — LLM · 벡터 검색 없음)
# 질문에서 연도 · 키워드를 뽑아 players.json · record_docs.json 에서 해당 문서를 찾아 그대로 보여 준다.
# 나중에 rag.graph 로 바꿔도 ask() 의 반환 형식(answer · sources · steps)은 그대로 쓴다.

import json
import re
from functools import lru_cache

from django.conf import settings

POST_WORDS = ["포스트시즌", "가을야구", "월드시리즈", "플레이오프", "디비전시리즈", "챔피언십", "와일드카드",
              "postseason", "world series", "playoff"]
TEAM_WORDS = ["팀 성적", "팀 기록", "팀은", "팀이", "구단 성적", "승률", "몇 승"]
CAREER_WORDS = ["통산", "커리어", "경력", "전체", "career"]


@lru_cache(maxsize=1)
def load_data():
    with open(settings.PLAYERS_PATH, encoding="utf-8") as f:
        players = {p["player_id"]: p for p in json.load(f)}
    with open(settings.RECORD_DOCS_PATH, encoding="utf-8") as f:
        docs = {d["doc_id"]: d for d in json.load(f)}
    return players, docs


def player_list():
    players, _ = load_data()
    rows = [{
        "player_id": p["player_id"], "name_ko": p["name_ko"], "name_en": p["name_en"],
        "role": p["role"], "position": p["primary_position"],
        "first_season": p["first_season"], "last_season": p["last_season"],
    } for p in players.values()]
    return sorted(rows, key=lambda r: r["name_ko"])


def source_of(doc_like):
    return {"title": doc_like["title"], "url": doc_like["url"], "source": doc_like["source"]}


def ask(player_id, question):
    players, docs = load_data()
    p = players.get(player_id)
    if p is None:
        return {"answer": "선택한 선수를 찾을 수 없습니다.", "sources": [], "steps": []}

    q = question.lower()
    years = sorted({int(y) for y in re.findall(r"(?:19|20)\d{2}", question)})
    want_post = any(w in q for w in POST_WORDS)
    want_team = any(w in question for w in TEAM_WORDS)
    want_career = any(w in q for w in CAREER_WORDS) or not years

    sources = []          # [{n, title, url, source, text}]
    parts = []            # 답변 문단
    steps = []

    def add(doc_like, text):
        n = len(sources) + 1
        sources.append({"n": n, **source_of(doc_like), "text": text})
        return n

    # 1) 선수 요약 (항상 근거 1)
    summary = {"title": f"{p['name_ko']} 선수 정보", "url": p["ko_wiki"]["url"], "source": "메타데이터"}
    n = add(summary, p["index_text"])
    if want_career:
        parts.append(f"**{p['name_ko']} ({p['name_en']}) 요약** [근거 {n}]\n{p['index_text']}")
    steps.append("선수 요약 1건")

    # 2) 시즌 기록
    for year in years:
        regular = docs.get(f"rec:{player_id}:{year}:regular")
        post = docs.get(f"rec:{player_id}:{year}:post")
        if regular is None and post is None:
            parts.append(f"**{year} 시즌**: MLB 출장 기록이 확인되지 않습니다. "
                         f"(기록 범위 {p['first_season']}~{p['last_season']} 시즌)")
            continue
        if regular and not (want_post and not want_team and post):
            n = add(regular, regular["text"])
            parts.append(f"**{regular['title']}** [근거 {n}]\n{regular['text']}")
        if post and (want_post or regular is None):
            n = add(post, post["text"])
            parts.append(f"**{post['title']}** [근거 {n}]\n{post['text']}")
        elif want_post and post is None:
            parts.append(f"**{year} 포스트시즌**: 출전 기록이 확인되지 않습니다.")
        if want_team and regular:
            for team_id in regular["teams"]:
                team = docs.get(f"rec:team:{team_id}:{year}")
                if team:
                    n = add(team, team["text"])
                    parts.append(f"**{team['title']}** [근거 {n}]\n{team['text']}")
    if years:
        steps.append(f"시즌 {', '.join(map(str, years))} 기록 검색")

    # 3) 연도 없이 포스트시즌을 물으면 전체 포스트시즌 기록
    if want_post and not years:
        post_docs = sorted((d for d in docs.values() if d["player_id"] == player_id and d["doc_type"] == "season_post"),
                           key=lambda d: d["season"])
        if not post_docs:
            parts.append("포스트시즌 출전 기록이 확인되지 않습니다.")
        for d in post_docs:
            n = add(d, d["text"])
            parts.append(f"**{d['title']}** [근거 {n}]\n{d['text']}")
        steps.append(f"포스트시즌 기록 {len(post_docs)}건")

    if not parts:
        parts.append("질문에서 찾을 기록을 알아내지 못했습니다. 연도(예: 2019)나 '통산', '포스트시즌'을 넣어 물어보세요.")

    return {"answer": "\n\n".join(parts), "sources": sources, "steps": steps}


def ask_compare(player_id, compare_id, question):
    """기록 검색 모드의 두 선수 비교 — 각 선수 결과를 이어 붙인다 (근거 번호는 뒤 선수만큼 밀어 줌)"""
    first = ask(player_id, question)
    second = ask(compare_id, question)
    offset = len(first["sources"])
    shifted = re.sub(r"\[근거 (\d+)\]", lambda m: f"[근거 {int(m.group(1)) + offset}]", second["answer"])
    for s in second["sources"]:
        s["n"] += offset
    return {"answer": first["answer"] + "\n\n---\n\n" + shifted,
            "sources": first["sources"] + second["sources"],
            "steps": first["steps"] + second["steps"]}
