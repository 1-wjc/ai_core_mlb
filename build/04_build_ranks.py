# 04. 시즌 리그 순위 (D4) → data/processed/season_ranks.json (선수 페이지 시즌표 배지 · 순위 질문 근거)
# 실행: python build/04_build_ranks.py   (01_build_players.py 먼저 실행)
#
# 1901~2025 AL · NL 전체 선수의 시즌 기록으로 시즌 · 리그별 순위를 매긴다 (서비스 항목 선수만 저장).
#   - 순위는 그 리그 안에서 낸 기록으로 계산 (시즌 중 리그를 옮기면 리그마다 따로)
#   - 비율 지표는 규정 기준 이상만: 타율 · 출루율 · 장타율 · OPS = 타석 ≥ 팀 경기 × 3.1, 평균자책점 · WHIP = 이닝 ≥ 팀 경기 × 1
#     (팀 경기 수는 그해 Teams 최다 경기 수 — 154경기 시대 · 파업 · 단축 시즌 자동 반영, build/03 과 같은 기준)
#   - 같은 값은 같은 순위 (1 + 더 좋은 선수 수)
#   - 10위 안만 저장한다 (화면 배지 · 근거에 쓰는 범위)

import json
import os

import lahman_loader as L

TOP = 10
# (키, 표기, 좋은 방향, 규정 기준 적용)
BAT = [("HR", "홈런", "high", False), ("H", "안타", "high", False), ("RBI", "타점", "high", False),
       ("R", "득점", "high", False), ("SB", "도루", "high", False), ("BB", "볼넷", "high", False),
       ("AVG", "타율", "high", True), ("OBP", "출루율", "high", True), ("SLG", "장타율", "high", True),
       ("OPS", "OPS", "high", True)]
PIT = [("W", "승", "high", False), ("SV", "세이브", "high", False), ("SO", "탈삼진", "high", False),
       ("IPouts", "이닝", "high", False), ("ERA", "평균자책점", "low", True), ("WHIP", "WHIP", "low", True)]


def by_league(file_name, fields):
    """{(playerID, year, lgID): 합계} — 같은 리그 안의 여러 팀 기록은 합친다"""
    out = {}
    for row in L.read_csv(os.path.join(L.LAHMAN_DIR, file_name)):
        if not L.in_scope(row):
            continue
        key = (row["playerID"], int(row["yearID"]), row["lgID"])
        total = out.setdefault(key, {f: 0 for f in fields})
        for f in fields:
            total[f] += L.to_int(row.get(f))
    return out


def bat_values(s):
    pa = s["AB"] + s["BB"] + s["HBP"] + s["SF"] + s["SH"]
    tb = s["H"] + s["2B"] + 2 * s["3B"] + 3 * s["HR"]
    obp_den = s["AB"] + s["BB"] + s["HBP"] + s["SF"]
    avg = s["H"] / s["AB"] if s["AB"] else None
    obp = (s["H"] + s["BB"] + s["HBP"]) / obp_den if obp_den else None
    slg = tb / s["AB"] if s["AB"] else None
    return pa, {"HR": s["HR"], "H": s["H"], "RBI": s["RBI"], "R": s["R"], "SB": s["SB"], "BB": s["BB"],
                "AVG": avg, "OBP": obp, "SLG": slg, "OPS": obp + slg if obp is not None and slg is not None else None}


def pit_values(s):
    outs = s["IPouts"]
    return outs, {"W": s["W"], "SV": s["SV"], "SO": s["SO"], "IPouts": outs,
                  "ERA": 27 * s["ER"] / outs if outs else None, "WHIP": 3 * (s["H"] + s["BB"]) / outs if outs else None}


def rank_all(rows, items, qualified):
    """rows {(pid, year, lg): 값 dict} → {(pid, year, lg): {키: (순위, 대상 수)}} (10위 안만)"""
    groups = {}
    for (pid, year, lg), vals in rows.items():
        groups.setdefault((year, lg), []).append((pid, vals))
    ranks = {}
    for (year, lg), members in groups.items():
        for key, _, better, needs_q in items:
            pool = [(pid, v[key]) for pid, v in members
                    if v[key] is not None and (not needs_q or qualified[(pid, year, lg)]) and (needs_q or v[key] > 0)]
            values = sorted((x for _, x in pool), reverse=better == "high")
            for pid, x in pool:
                better_count = sum(1 for y in values if (y > x if better == "high" else y < x))
                if better_count < TOP:
                    ranks.setdefault((pid, year, lg), {})[key] = (better_count + 1, len(pool))
    return ranks


def main():
    with open(os.path.join(L.PROCESSED_DIR, "players.json"), encoding="utf-8") as f:
        ours = {p["lahman_id"]: p["player_id"] for p in json.load(f)}
    team_games = {}
    for (year, _), t in L.load_teams().items():
        team_games[year] = max(team_games.get(year, 0), L.to_int(t["G"]))

    bat_rows, bat_q = {}, {}
    for key, s in by_league("Batting.csv", L.BAT_FIELDS).items():
        pa, vals = bat_values(s)
        bat_rows[key], bat_q[key] = vals, pa >= 3.1 * team_games.get(key[1], 162)
    pit_rows, pit_q = {}, {}
    for key, s in by_league("Pitching.csv", L.PIT_FIELDS).items():
        outs, vals = pit_values(s)
        pit_rows[key], pit_q[key] = vals, outs >= 3 * team_games.get(key[1], 162)

    out, count = {}, 0
    for part, rows, q, items in (("batting", bat_rows, bat_q, BAT), ("pitching", pit_rows, pit_q, PIT)):
        labels = {k: (name, better, needs_q) for k, name, better, needs_q in items}
        for (lahman_id, year, lg), ranks in rank_all(rows, items, q).items():
            pid = ours.get(lahman_id)
            if not pid:
                continue
            season = out.setdefault(pid, {}).setdefault(str(year), {})
            for key, (rank, total) in ranks.items():
                name, better, needs_q = labels[key]
                season.setdefault(part, {})[key] = {"rank": rank, "of": total, "league": lg, "label": name,
                                                    "qualified": needs_q}
                count += 1

    path = os.path.join(L.PROCESSED_DIR, "season_ranks.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    firsts = sum(1 for p in out.values() for s in p.values() for part in s.values() for r in part.values() if r["rank"] == 1)
    print(f"선수 {len(out):,}명 · 10위 안 기록 {count:,}개 (리그 1위 {firsts:,}개)")
    print("저장:", path)


if __name__ == "__main__":
    main()
