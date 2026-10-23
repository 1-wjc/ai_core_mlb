# 마일스톤 달성 시즌 (D3) — 통산 기록이 단계 기준을 넘은 시즌
#   - 실제 통산으로 센다: 메이저리그로 인정되는 리그(NL · AL · AA · UA · PL · FL) 전 시즌 합산
#     (NA 1871-75 · 니그로 리그 제외). 그래서 1901년 이전에 뛴 선수(사이 영 등)도 달성 시즌이 맞게 나온다.
#   - 종류마다 "가장 높은 단계"만 선수 마일스톤으로 쓴다 (500홈런이면 200 · 300 · 400홈런은 표시하지 않음)
#   - 메인 타임라인에는 큰 기록(MAJOR)을 넘은 시즌만 — 기준이 낮은 단계까지 넣으면 해마다 수십 명이 됨
#   - 정규시즌만 (포스트시즌 제외)

import os

import lahman_loader as L

MAJOR_LEAGUES = {"NL", "AL", "AA", "UA", "PL", "FL"}

# (파일, 열, 시작 단계, 단계 간격, 표기 단위, 타임라인 기준) — 시작부터 간격마다 단계
MILESTONES = [
    ("Batting.csv", "HR", 200, 100, "홈런", 500),
    ("Batting.csv", "H", 1000, 1000, "안타", 3000),
    ("Batting.csv", "RBI", 1000, 500, "타점", 2000),
    ("Batting.csv", "R", 1000, 500, "득점", 2000),
    ("Batting.csv", "2B", 400, 100, "2루타", 600),
    ("Batting.csv", "BB", 1000, 500, "볼넷", 2000),
    ("Batting.csv", "SB", 300, 100, "도루", 800),
    ("Appearances.csv", "G_all", 2000, 500, "경기 출장", 3000),
    ("Pitching.csv", "W", 100, 100, "승", 300),
    ("Pitching.csv", "SO", 1000, 1000, "탈삼진", 3000),
    ("Pitching.csv", "SV", 200, 100, "세이브", 500),
    ("Pitching.csv", "IPouts", 1500, 500, "이닝", 5000),     # 이닝 단계 — 아웃카운트 ÷ 3 으로 비교
]


def _yearly():
    """{(파일, 열): {playerID: {year: 합계}}}"""
    out = {}
    for file_name in {m[0] for m in MILESTONES}:
        cols = [m[1] for m in MILESTONES if m[0] == file_name]
        for row in L.read_csv(os.path.join(L.LAHMAN_DIR, file_name)):
            if row["lgID"] not in MAJOR_LEAGUES:
                continue
            year = L.to_int(row["yearID"])
            for col in cols:
                by_year = out.setdefault((file_name, col), {}).setdefault(row["playerID"], {})
                by_year[year] = by_year.get(year, 0) + L.to_int(row.get(col))
    return out


def _crossings():
    """{playerID: [{"label", "season", "value", "kind", "major"}]} — 넘은 단계 전부 (시즌 순)"""
    yearly = _yearly()
    out = {}
    for file_name, col, start, step, unit, major in MILESTONES:
        for pid, by_year in yearly[(file_name, col)].items():
            total, level = 0, start
            for year in sorted(by_year):
                total += by_year[year]
                value = total / 3 if col == "IPouts" else total
                while value >= level:
                    out.setdefault(pid, []).append({"label": f"{level:,}{' ' if unit[0].isdigit() else ''}{unit}", "season": year, "value": level,
                                                    "kind": unit, "major": level >= major})
                    level += step
    for items in out.values():
        items.sort(key=lambda x: (x["season"], x["value"]))
    return out


def compute():
    """선수 마일스톤 {playerID: [{"label", "season"}]} — 종류마다 가장 높은 단계만, 달성 시즌 순"""
    best = {}
    for pid, items in _crossings().items():
        top = {}
        for m in items:
            top[m["kind"]] = m                             # 시즌 순이라 마지막이 가장 높은 단계
        best[pid] = sorted(({"label": m["label"], "season": m["season"]} for m in top.values()),
                           key=lambda x: x["season"])
    return best


def timeline_events():
    """타임라인용 {playerID: [{"label", "season"}]} — 큰 기록(MAJOR 이상) 단계를 넘은 시즌 전부"""
    return {pid: [{"label": m["label"], "season": m["season"]} for m in items if m["major"]]
            for pid, items in _crossings().items() if any(m["major"] for m in items)}
