# 마일스톤 달성 시즌 (D3) — 500홈런 · 3,000안타 · 300승 · 3,000탈삼진 · 500세이브 등
#   통산 기록이 기준을 넘은 시즌을 찾는다. 서비스 범위(1901~)와 달리 **실제 통산**으로 센다:
#   메이저리그로 인정되는 리그(NL · AL · AA · UA · PL · FL) 전 시즌을 합산 (NA 1871-75 · 니그로 리그는 제외).
#   그래서 1901년 이전에 뛴 선수(사이 영 등)도 달성 시즌이 맞게 나온다.

import os

import lahman_loader as L

MAJOR_LEAGUES = {"NL", "AL", "AA", "UA", "PL", "FL"}

# (파일, 열, 기준, 표기)
MILESTONES = [
    ("Batting.csv", "HR", 500, "500홈런"), ("Batting.csv", "HR", 600, "600홈런"), ("Batting.csv", "HR", 700, "700홈런"),
    ("Batting.csv", "H", 3000, "3,000안타"),
    ("Pitching.csv", "W", 300, "300승"), ("Pitching.csv", "SO", 3000, "3,000탈삼진"), ("Pitching.csv", "SV", 500, "500세이브"),
]


def compute():
    """{playerID: [{"label", "season"}]} — 달성 순서대로"""
    yearly = {}                                            # (파일, 열) → {playerID: {year: 합계}}
    for file_name in {m[0] for m in MILESTONES}:
        cols = {m[1] for m in MILESTONES if m[0] == file_name}
        for row in L.read_csv(os.path.join(L.LAHMAN_DIR, file_name)):
            if row["lgID"] not in MAJOR_LEAGUES:
                continue
            year = L.to_int(row["yearID"])
            for col in cols:
                by_year = yearly.setdefault((file_name, col), {}).setdefault(row["playerID"], {})
                by_year[year] = by_year.get(year, 0) + L.to_int(row.get(col))

    reached = {}
    for file_name, col, threshold, label in MILESTONES:
        for pid, by_year in yearly[(file_name, col)].items():
            total = 0
            for year in sorted(by_year):
                total += by_year[year]
                if total >= threshold:
                    reached.setdefault(pid, []).append({"label": label, "season": year})
                    break
    for items in reached.values():
        items.sort(key=lambda x: x["season"])
    return reached
