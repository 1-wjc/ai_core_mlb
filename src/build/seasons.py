# 항목 후보 선수들의 시즌별 기록 + 지표를 한 번에 계산한다.
# 01_build_players.py (선수 요약 · 통산) 와 02_build_record_docs.py (시즌 문서) 가 같은 결과를 쓴다.

import lahman_loader as L
import metrics as M


def compute_all():
    """
    반환 dict
      candidates : {bbrefID: Wikidata 연결 행}
      people     : {playerID: People 행}
      lahman_id  : {bbrefID: playerID}
      teams      : {(year, teamID): Teams 행}
      series     : SeriesPost 행 목록
      rates      : {(year, lgID): 리그 기준값}
      league_totals: {(year, lgID): {"bat": 합계, "pit": 합계}} (리그 대비 지수용)
      seasons    : {playerID: {year: {"bat": {...}|None, "pit": {...}|None, "fld": {...}|None, "teams": [...]}}}
      post       : {playerID: {year: {"bat": {...}|None, "pit": {...}|None, "rounds": [...], "teams": [...]}}}
      appearances: {playerID: {포지션 열: 경기 수}}
    """
    candidates = L.load_candidates()
    people, bbref_to_lahman = L.load_people()

    target = set()
    lahman_id = {}
    for bbref in candidates:
        if bbref in bbref_to_lahman:
            target.add(bbref_to_lahman[bbref])
            lahman_id[bbref] = bbref_to_lahman[bbref]

    teams = L.load_teams()
    series = L.load_series()
    rates = {}
    league_totals = L.league_totals()
    for key, total in league_totals.items():
        rates[key] = M.league_rates(total)

    batting = L.sum_by_player_season("Batting.csv", L.BAT_FIELDS, "bat")
    pitching = L.sum_by_player_season("Pitching.csv", L.PIT_FIELDS, "pit")
    fielding = L.sum_fielding_by_position()

    # ---------------- 정규시즌 ----------------
    seasons = {}
    for (pid, year), entry in batting.items():
        if pid not in target:
            continue
        league, park = L.main_league_and_park(entry["stints"], year, teams, "BPF")
        m = M.batting_metrics(entry["stats"], rates.get((year, league)), park)
        season = seasons.setdefault(pid, {}).setdefault(year, {"bat": None, "pit": None, "fld": None, "teams": []})
        season["bat"] = {"stats": entry["stats"], "metrics": m, "league": league}
        for team_id, _, _ in entry["stints"]:
            if team_id not in season["teams"]:
                season["teams"].append(team_id)

    for (pid, year), entry in pitching.items():
        if pid not in target:
            continue
        league, park = L.main_league_and_park(entry["stints"], year, teams, "PPF")
        m = M.pitching_metrics(entry["stats"], rates.get((year, league)), park)
        season = seasons.setdefault(pid, {}).setdefault(year, {"bat": None, "pit": None, "fld": None, "teams": []})
        season["pit"] = {"stats": entry["stats"], "metrics": m, "league": league}
        for team_id, _, _ in entry["stints"]:
            if team_id not in season["teams"]:
                season["teams"].append(team_id)

    # 수비: 그 시즌 가장 많이 나선 포지션 하나
    for (pid, year), by_pos in fielding.items():
        if pid not in target or year not in seasons.get(pid, {}):
            continue
        best_pos = None
        best_games = -1
        for pos, f in by_pos.items():
            if f["G"] > best_games:
                best_pos = pos
                best_games = f["G"]
        f = by_pos[best_pos]
        seasons[pid][year]["fld"] = {"pos": best_pos, "stats": f, "metrics": M.fielding_metrics(f)}

    # ---------------- 포스트시즌 (라운드별 → 시즌 합계) ----------------
    post = {}
    for file_name, fields, kind in [("BattingPost.csv", L.BAT_FIELDS, "bat"), ("PitchingPost.csv", L.PIT_FIELDS, "pit")]:
        by_round = L.sum_by_player_season(file_name, fields, kind, with_round=True)
        for (pid, year, round_code), entry in by_round.items():
            if pid not in target:
                continue
            p = post.setdefault(pid, {}).setdefault(year, {"bat": None, "pit": None, "rounds": [], "teams": [],
                                                           "_bat_sum": None, "_pit_sum": None})
            if round_code not in p["rounds"]:
                p["rounds"].append(round_code)
            for team_id, _, _ in entry["stints"]:
                if team_id not in p["teams"]:
                    p["teams"].append(team_id)
            sum_key = "_bat_sum" if kind == "bat" else "_pit_sum"
            if p[sum_key] is None:
                p[sum_key] = {f: 0 for f in fields}
            for f in fields:
                p[sum_key][f] += entry["stats"][f]
    for pid, years in post.items():
        for year, p in years.items():
            if p["_bat_sum"] is not None:
                p["bat"] = {"stats": p["_bat_sum"], "metrics": M.batting_metrics(p["_bat_sum"])}
            if p["_pit_sum"] is not None:
                p["pit"] = {"stats": p["_pit_sum"], "metrics": M.pitching_metrics(p["_pit_sum"])}
            del p["_bat_sum"]
            del p["_pit_sum"]

    # ---------------- 포지션별 출장 (주 포지션 판정용) ----------------
    appearances = {}
    for row in L.read_csv(L.LAHMAN_DIR + "/Appearances.csv"):
        if not L.in_scope(row) or row["playerID"] not in target:
            continue
        counts = appearances.setdefault(row["playerID"], {})
        for column in ["G_p", "G_c", "G_1b", "G_2b", "G_3b", "G_ss", "G_lf", "G_cf", "G_rf", "G_dh"]:
            counts[column] = counts.get(column, 0) + L.to_int(row[column])

    # ---------------- 역할: 투수 / 타자 / 투타겸업 ----------------
    # 가장 많이 나선 포지션이 투수면 "투수". 투수이면서 투수 외 포지션(지명타자 포함) 출장이
    # 100경기 이상이거나, 타자이면서 투구 이닝이 100이닝(300아웃) 이상이면 투타겸업으로 본다.
    roles = {}
    for pid in target:
        counts = appearances.get(pid, {})
        if not counts:
            continue
        main_column = max(counts, key=lambda c: counts[c])
        role = "투수" if main_column == "G_p" else "타자"
        non_pitcher_games = sum(v for c, v in counts.items() if c != "G_p")
        ipouts = sum(s["pit"]["stats"]["IPouts"] for s in seasons.get(pid, {}).values() if s["pit"])
        two_way = (role == "투수" and non_pitcher_games >= 100) or (role == "타자" and ipouts >= 300)
        roles[pid] = {"role": role, "main_column": main_column, "two_way": two_way}

    return {
        "candidates": candidates, "people": people, "lahman_id": lahman_id,
        "teams": teams, "series": series, "rates": rates, "league_totals": league_totals,
        "seasons": seasons, "post": post, "appearances": appearances, "roles": roles,
    }
