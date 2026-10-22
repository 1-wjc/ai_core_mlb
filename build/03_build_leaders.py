# 03. 시즌별 리그 전체 1위 · 주요 수상 → data/processed/season_leaders.json (메인 시즌 타임라인용)
# 실행: python build/03_build_leaders.py   (01_build_players.py 먼저 실행)
#
# 항목(서비스 선수)만이 아니라 Lahman 1901~2025 AL · NL 전체 선수로 계산한다.
#   홈런 · 탈삼진 1위, 타율 1위(규정 타석 = 팀 경기 × 3.1), 평균자책점 1위(규정 이닝 = 팀 경기 × 1)
#   팀 경기 수는 그해 Teams 의 최다 경기 수 (154경기 시대 · 파업 · 단축 시즌을 자동 반영)
#   MVP · 사이영상 (리그별) · 그해 마일스톤 달성자 (500홈런 · 3,000안타 · 300승 등)
# 서비스 항목에 있는 선수는 player_id 와 한국어 이름을, 없는 선수는 영어 이름만 남긴다.

import json
import os

import lahman_loader as L
import milestones as MS

AWARDS = {"Most Valuable Player": "mvp", "Cy Young Award": "cy"}


def main():
    people, _ = L.load_people()
    with open(os.path.join(L.PROCESSED_DIR, "players.json"), encoding="utf-8") as f:
        ours = {p["lahman_id"]: p for p in json.load(f)}

    def person(pid, value=None, league=None):
        p, row = ours.get(pid), people.get(pid, {})
        name_en = f"{row.get('nameFirst', '')} {row.get('nameLast', '')}".strip() or pid
        item = {"player_id": p["player_id"] if p else None, "name": p["name_ko"] if p else name_en, "name_en": name_en}
        if value is not None:
            item["value"] = value
        if league:
            item["league"] = league
        return item

    team_games = {}
    for (year, _), t in L.load_teams().items():
        team_games[year] = max(team_games.get(year, 0), L.to_int(t["G"]))

    years = {y: {"mvp": [], "cy": [], "hr": None, "avg": None, "era": None, "so": None, "milestones": []}
             for y in range(L.FIRST_SEASON, L.LAST_SEASON + 1)}

    # 타격: 홈런 1위 · 타율 1위
    batting = L.sum_by_player_season("Batting.csv", L.BAT_FIELDS, "bat")
    best = {}
    for (pid, year), entry in batting.items():
        s = entry["stats"]
        games = team_games.get(year, 162)
        pa = s["AB"] + s["BB"] + s["HBP"] + s["SF"] + s["SH"]
        hr = best.setdefault((year, "hr"), [None, -1])
        if s["HR"] > hr[1]:
            best[(year, "hr")] = [pid, s["HR"]]
        if pa >= 3.1 * games and s["AB"]:
            avg = s["H"] / s["AB"]
            cur = best.get((year, "avg"), [None, -1])
            if avg > cur[1]:
                best[(year, "avg")] = [pid, avg]

    # 투구: 탈삼진 1위 · 평균자책점 1위
    pitching = L.sum_by_player_season("Pitching.csv", L.PIT_FIELDS, "pit")
    for (pid, year), entry in pitching.items():
        s = entry["stats"]
        games = team_games.get(year, 162)
        cur = best.get((year, "so"), [None, -1])
        if s["SO"] > cur[1]:
            best[(year, "so")] = [pid, s["SO"]]
        if s["IPouts"] >= 3 * games:
            era = 27 * s["ER"] / s["IPouts"]
            cur = best.get((year, "era"), [None, 99])
            if era < cur[1]:
                best[(year, "era")] = [pid, era]

    for (year, key), (pid, value) in best.items():
        if pid is None or year not in years:
            continue
        shown = f"{value:.3f}".lstrip("0") if key == "avg" else f"{value:.2f}" if key == "era" else value
        years[year][key] = person(pid, shown)

    # 수상: MVP · 사이영상 (리그별, 공동 수상 포함)
    for row in L.read_csv(os.path.join(L.LAHMAN_DIR, "AwardsPlayers.csv")):
        key = AWARDS.get(row["awardID"])
        year = L.to_int(row["yearID"])
        if key and year in years and row["lgID"] in L.LEAGUES:
            years[year][key].append(person(row["playerID"], league=row["lgID"]))
    # 마일스톤: 그해 기준을 넘은 선수 (실제 통산 기준, build/milestones.py)
    for pid, items in MS.compute().items():
        for m in items:
            if m["season"] in years:
                years[m["season"]]["milestones"].append({**person(pid), "label": m["label"]})
    for y in years.values():
        for key in ("mvp", "cy"):
            y[key].sort(key=lambda x: x["league"])

    out = os.path.join(L.PROCESSED_DIR, "season_leaders.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({str(y): v for y, v in years.items()}, f, ensure_ascii=False, indent=1)
    linked = sum(1 for v in years.values() for k in ("hr", "avg", "era", "so") if v[k] and v[k]["player_id"])
    print(f"시즌 {len(years)}개 · 부문 1위 {len(years) * 4}칸 중 서비스 선수 연결 {linked}칸")
    print("저장:", out)


if __name__ == "__main__":
    main()
