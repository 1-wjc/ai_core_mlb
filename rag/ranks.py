# 시즌 리그 순위 근거 (D4) — "그해 리그 몇 위였어?" 같은 질문에 build/04_build_ranks.py 결과를 근거로 넣는다
#   순위는 1901~2025 AL · NL 전체 선수 시즌 기록으로 코드가 계산한 값 (10위 안만). LLM 은 계산하지 않고 인용만.
#   질문에 연도가 있으면 그 시즌, 없으면 리그 1위를 한 시즌 목록.

import json
import re
from functools import lru_cache

from rag import config as C

SOURCE_URL = "https://sabr.org/lahman-database/"
RANK_WORDS = re.compile(r"순위|몇 ?위|\d+ ?위|리그 ?(?:최고|선두|1위)|타이틀|부문")
LEAGUE_KO = {"AL": "아메리칸리그", "NL": "내셔널리그"}


@lru_cache(maxsize=1)
def _ranks():
    try:
        with open(C.SEASON_RANKS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def wanted(question):
    return bool(RANK_WORDS.search(question))


def _line(year, season):
    parts = []
    for part in ("batting", "pitching"):
        for r in sorted((season.get(part) or {}).values(), key=lambda r: r["rank"]):
            basis = (" · 규정 타석 이상" if part == "batting" else " · 규정 이닝 이상") if r["qualified"] else ""
            parts.append(f"{LEAGUE_KO.get(r['league'], r['league'])} {r['label']} {r['rank']}위 ({r['of']}명 중{basis})")
    return f"{year}: " + ", ".join(parts) if parts else ""


def rank_evidence(player_id, player_name, years):
    """근거 1건 또는 None"""
    seasons = _ranks().get(player_id, {})
    if not seasons:
        return None
    if years:
        lines = [_line(y, seasons[str(y)]) for y in years if str(y) in seasons]
        head = "시즌 리그 순위 (10위 안)"
    else:                                              # 연도가 없으면 리그 1위를 한 시즌만
        lines = []
        for y in sorted(seasons, key=int):
            firsts = {part: {k: r for k, r in (seasons[y].get(part) or {}).items() if r["rank"] == 1} for part in seasons[y]}
            line = _line(y, firsts)
            if line:
                lines.append(line)
        head = "리그 1위를 한 시즌"
    lines = [x for x in lines if x]
    if not lines:
        return None
    text = (f"{player_name} {head} — 1901~2025 AL · NL 전체 선수 시즌 기록으로 계산, 리그 안에서 낸 기록 기준\n"
            + "\n".join(lines))
    return {"id": f"{player_id}:ranks", "source": "기록 데이터(Lahman)", "title": f"{player_name.split(' (')[0]} 시즌 리그 순위",
            "url": SOURCE_URL, "text": text, "distance": None}
