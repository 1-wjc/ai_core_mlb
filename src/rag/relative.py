# 시대 보정 비교 (D1) — 통산 기록을 "그 시즌 리그 평균 대비" 지수로 바꾼 근거 (100 = 리그 평균)
#   값은 build/01_build_players.py 가 시즌마다 리그 기준과 비교해 출전량(타석 · 상대 타자 · 이닝)으로 가중해 계산한다.
#   루스(1920년대) vs 저지(2020년대)처럼 시대가 다른 선수를 비교할 때 원래 수치 대신 쓴다. LLM 은 계산하지 않고 인용만.

import json
import re
from functools import lru_cache

from rag import config as C

SOURCE_URL = "https://sabr.org/lahman-database/"
# 질문에 이런 말이 있으면 단일 선수 질문에도 근거로 넣는다 (비교 질문에는 항상)
ERA_WORDS = re.compile(r"시대|리그 ?대비|리그 ?평균|보정|다른 시대|era[- ]?adjusted", re.I)

# (키, 표기, 좋은 방향)
BAT = [("OPS_plus", "OPS+", "높을수록 좋음"), ("AVG_idx", "타율", "높을수록 좋음"), ("OBP_idx", "출루율", "높을수록 좋음"),
       ("SLG_idx", "장타율", "높을수록 좋음"), ("HR_idx", "홈런 비율(타석당)", "높을수록 좋음"),
       ("BB_idx", "볼넷 비율", "높을수록 좋음"), ("K_idx", "삼진 비율", "낮을수록 좋음")]
PIT = [("ERA_plus", "ERA+", "높을수록 좋음"), ("K_idx", "탈삼진 비율", "높을수록 좋음"), ("BB_idx", "볼넷 비율", "낮을수록 좋음"),
       ("HR9_idx", "9이닝당 피홈런", "낮을수록 좋음"), ("WHIP_idx", "WHIP", "낮을수록 좋음")]


@lru_cache(maxsize=1)
def _players():
    with open(C.PLAYERS_PATH, encoding="utf-8") as f:
        return {p["player_id"]: p for p in json.load(f)}


def wanted(question, compare):
    return compare or bool(ERA_WORDS.search(question))


def relative_evidence(player_id):
    """근거 1건 또는 None — 리그 대비 지수 줄 (원래 값과 함께)"""
    p = _players().get(player_id)
    if not p:
        return None
    lines = []
    for kind, items, label in (("batting", BAT, "타격"), ("pitching", PIT, "투구")):
        block = p["career"].get(kind)
        if not block:
            continue
        rel = dict(block.get("relative") or {})
        rel.setdefault("OPS_plus", block["metrics"].get("OPS_plus"))
        rel.setdefault("ERA_plus", block["metrics"].get("ERA_plus"))
        parts = [f"{name} {rel[key]:.0f} ({better})" for key, name, better in items if rel.get(key) is not None]
        if parts:
            lines.append(f"{label} 리그 대비 지수: " + " · ".join(parts))
    if not lines:
        return None
    text = (f"{p['name_ko']} ({p['name_en']}) 통산 리그 대비 지수 — {p['first_season']}~{p['last_season']} 시즌\n"
            "100 = 그 시즌 리그 평균, 시즌마다 리그 기준과 비교해 출전량으로 가중 (OPS+ · ERA+ 는 구장 보정 포함)\n"
            + "\n".join(lines))
    return {"id": f"{player_id}:relative", "source": "기록 데이터(Lahman)", "title": f"{p['name_ko']} 리그 대비 통산 지수",
            "url": SOURCE_URL, "text": text, "distance": None}
