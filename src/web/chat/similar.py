# 비슷한 선수 찾기 (B2) — 통산 지표 6개를 표준화(z-점수)해 거리가 가까운 선수를 고른다. LLM 미사용, 코드 계산만
#   타자: 통산 1,000타석 이상 · 투수: 통산 200이닝(600아웃) 이상인 같은 역할 선수끼리 비교
#   투수: 기준 선수의 경기당 세이브가 0.1 이하(마무리가 아님)면 경기당 세이브를,
#         선발 비율이 0.9 초과(거의 선발만)면 선발 비율을 거리 계산 · 표시에서 빼고, 비교 대상은 선발 비율 0.5 이상 투수로 한정

import math
from functools import lru_cache

from chat import search

# (지표 이름, 값 꺼내는 함수, 표시 형식)
BAT_FEATURES = [
    ("OPS+", lambda b: b["metrics"].get("OPS_plus"), "{:.0f}"),
    ("ISO", lambda b: b["metrics"].get("ISO"), "{:.3f}"),
    ("타율", lambda b: b["metrics"].get("AVG"), "{:.3f}"),
    ("볼넷%", lambda b: b["metrics"].get("BB_pct"), "{:.1f}"),
    ("삼진%", lambda b: b["metrics"].get("K_pct"), "{:.1f}"),
    ("600타석당 도루", lambda b: b["stats"]["SB"] * 600 / b["metrics"]["PA"] if b["metrics"].get("PA") else None, "{:.1f}"),
]
PIT_FEATURES = [
    ("ERA+", lambda p: p["metrics"].get("ERA_plus"), "{:.0f}"),
    ("탈삼진%", lambda p: p["metrics"].get("K_pct"), "{:.1f}"),
    ("볼넷%", lambda p: p["metrics"].get("BB_pct"), "{:.1f}"),
    ("HR/9", lambda p: p["metrics"].get("HR9"), "{:.2f}"),
    ("선발 비율", lambda p: p["stats"]["GS"] / p["stats"]["G"] if p["stats"].get("G") else None, "{:.2f}"),
    ("경기당 세이브", lambda p: p["stats"]["SV"] / p["stats"]["G"] if p["stats"].get("G") else None, "{:.2f}"),
]
START_INDEX = len(PIT_FEATURES) - 2
START_CUTOFF = 0.9                 # 선발 비율이 이 값을 넘는 투수는 선발 비율을 비교하지 않음
STARTER_POOL = 0.5                 # 그때 비교 대상은 선발 비율이 이 값 이상인 투수만 (구원 투수가 섞이지 않게)
SAVE_INDEX = len(PIT_FEATURES) - 1
SAVE_CUTOFF = 0.1                  # 경기당 세이브가 이 값 이하인 투수는 세이브 지표를 비교하지 않음


def _eligible(p, kind):
    block = p["career"].get(kind)
    if not block:
        return None
    if kind == "batting":
        return block if (p["role"] == "타자" or p["two_way"]) and block["metrics"].get("PA", 0) >= 1000 else None
    return block if (p["role"] == "투수" or p["two_way"]) and block["stats"].get("IPouts", 0) >= 600 else None


@lru_cache(maxsize=2)
def _table(kind):
    """{player_id: [z-점수 벡터]}, {player_id: [원래 값]}"""
    players, _ = search.load_data()
    feats = BAT_FEATURES if kind == "batting" else PIT_FEATURES
    raw = {}
    for pid, p in players.items():
        block = _eligible(p, kind)
        if block:
            values = [f(block) for _, f, _ in feats]
            if all(v is not None for v in values):
                raw[pid] = values
    cols = list(zip(*raw.values()))
    means = [sum(c) / len(c) for c in cols]
    sds = [math.sqrt(sum((x - m) ** 2 for x in c) / len(c)) or 1 for c, m in zip(cols, means)]
    z = {pid: [(v - m) / s for v, m, s in zip(vals, means, sds)] for pid, vals in raw.items()}
    return z, raw


def similar_players(player_id, top=5):
    """[(종류 표기, [{player_id, name_ko, name_en, position, years, score, values, closest}])] — 대상이 아니면 빈 목록"""
    players, _ = search.load_data()
    p = players[player_id]
    kinds = ["pitching", "batting"] if p["role"] == "투수" else ["batting", "pitching"]
    out = []
    for kind in kinds:
        z, raw = _table(kind)
        if player_id not in z:
            continue
        feats = BAT_FEATURES if kind == "batting" else PIT_FEATURES
        me = z[player_id]
        use = list(range(len(feats)))                       # 비교에 쓰는 지표 위치
        starters_only = kind == "pitching" and raw[player_id][START_INDEX] > START_CUTOFF
        if starters_only:
            use.remove(START_INDEX)
        if kind == "pitching" and raw[player_id][SAVE_INDEX] <= SAVE_CUTOFF:
            use.remove(SAVE_INDEX)
        scored = []
        for other, vec in z.items():
            if other == player_id or (starters_only and raw[other][START_INDEX] < STARTER_POOL):
                continue
            dist = math.sqrt(sum((me[i] - vec[i]) ** 2 for i in use))
            scored.append((dist, other))
        scored.sort()
        rows = []
        for dist, other in scored[:top]:
            o = players[other]
            gaps = sorted(use, key=lambda i: abs(me[i] - z[other][i]))
            rows.append({
                "player_id": other, "name_ko": o["name_ko"], "name_en": o["name_en"], "position": o["primary_position"],
                "years": f"{o['first_season']}–{o['last_season']}",
                "score": round(100 / (1 + dist)),                       # 0~100, 거리 0 이면 100
                "values": [(feats[i][0], feats[i][2].format(raw[other][i]).lstrip("0") if feats[i][2] == "{:.3f}" else feats[i][2].format(raw[other][i])) for i in use],
                "closest": [feats[i][0] for i in gaps[:2]],
            })
        mine = [(feats[i][0], feats[i][2].format(raw[player_id][i]).lstrip("0") if feats[i][2] == "{:.3f}" else feats[i][2].format(raw[player_id][i])) for i in use]
        out.append({"kind": "타격" if kind == "batting" else "투구", "mine": mine, "rows": rows,
                    "pool": len(scored), "n_feats": len(use), "starters_only": starters_only})
    return out
