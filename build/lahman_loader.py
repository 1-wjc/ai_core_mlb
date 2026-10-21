# Lahman 원본 읽기 · 선수 시즌 합산 · 리그 합계 · 팀 정보
# 01_build_players.py, 02_build_record_docs.py 가 함께 사용한다.
#
# 규칙
#   - 범위: 1990~2025 시즌, 리그 AL · NL 만 (니그로 리그 등 다른 리그 코드 제외)
#   - 한 시즌에 여러 팀(stint)에서 뛴 경우 합산한다.
#     리그 평균 · 파크 팩터는 출전량(타석 또는 아웃카운트)으로 가중해서 정한다.

import csv
import os

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
LAHMAN_DIR = os.path.join(RAW_DIR, "lahman")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

FIRST_SEASON = 1990
LAST_SEASON = 2025
LEAGUES = ("AL", "NL")

BAT_FIELDS = ["G", "AB", "R", "H", "2B", "3B", "HR", "RBI", "SB", "CS", "BB", "SO",
              "IBB", "HBP", "SH", "SF", "GIDP"]
PIT_FIELDS = ["W", "L", "G", "GS", "CG", "SHO", "SV", "IPouts", "H", "ER", "HR", "BB",
              "SO", "IBB", "WP", "HBP", "BK", "BFP", "GF", "R", "SH", "SF", "GIDP"]
FLD_FIELDS = ["G", "GS", "InnOuts", "PO", "A", "E", "DP"]


def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def to_int(value):
    """빈 칸은 0으로 본다 (1990년 이후 범위에서는 주요 열이 모두 채워져 있음)."""
    if value is None or value == "":
        return 0
    return int(float(value))


def in_scope(row):
    year = int(row["yearID"])
    return FIRST_SEASON <= year <= LAST_SEASON and row["lgID"] in LEAGUES


def bat_weight(s):
    """타석 수 (PA)"""
    return s["AB"] + s["BB"] + s["HBP"] + s["SF"] + s["SH"]


# ---------------- 항목 후보 · 선수 정보 ----------------
def load_candidates():
    """한/영 위키 문서가 모두 있는 선수 → {bbrefID: Wikidata 연결 행}"""
    path = os.path.join(RAW_DIR, "wikidata", "players_wikidata.csv")
    candidates = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["ko_title"] and row["en_title"]:
                candidates[row["key_bbref"]] = row
    return candidates


def load_people():
    """Lahman People → {playerID: 행}, {bbrefID: playerID}"""
    people = {}
    bbref_to_lahman = {}
    for row in read_csv(os.path.join(LAHMAN_DIR, "People.csv")):
        people[row["playerID"]] = row
        if row["bbrefID"]:
            bbref_to_lahman[row["bbrefID"]] = row["playerID"]
    return people, bbref_to_lahman


# ---------------- 선수 시즌 합산 ----------------
def sum_by_player_season(file_name, fields, weight_kind, with_round=False):
    """
    선수 · 시즌(· 라운드)별로 기록을 합산한다.
    결과: {(playerID, year[, round]): {"stats": {...}, "stints": [(teamID, lgID, 가중치), ...]}}
    weight_kind: "bat" 이면 타석 수, "pit" 이면 아웃카운트로 stint 가중치를 둔다.
    """
    result = {}
    for row in read_csv(os.path.join(LAHMAN_DIR, file_name)):
        if not in_scope(row):
            continue
        key = (row["playerID"], int(row["yearID"]))
        if with_round:
            key = key + (row["round"],)
        if key not in result:
            stats = {}
            for field in fields:
                stats[field] = 0
            result[key] = {"stats": stats, "stints": []}
        entry = result[key]
        stint_stats = {}
        for field in fields:
            value = to_int(row.get(field))
            entry["stats"][field] += value
            stint_stats[field] = value
        if weight_kind == "bat":
            weight = bat_weight(stint_stats)
        else:
            weight = stint_stats["IPouts"]
        entry["stints"].append((row["teamID"], row["lgID"], weight))
    return result


def sum_fielding_by_position():
    """정규시즌 수비: {(playerID, year): {POS: {G, GS, InnOuts, PO, A, E, DP}}}"""
    result = {}
    for row in read_csv(os.path.join(LAHMAN_DIR, "Fielding.csv")):
        if not in_scope(row):
            continue
        key = (row["playerID"], int(row["yearID"]))
        pos = row["POS"]
        if key not in result:
            result[key] = {}
        if pos not in result[key]:
            stats = {}
            for field in FLD_FIELDS:
                stats[field] = 0
            result[key][pos] = stats
        for field in FLD_FIELDS:
            result[key][pos][field] += to_int(row.get(field))
    return result


# ---------------- 리그 합계 ----------------
def league_totals():
    """시즌 · 리그별 전체 타격 · 투구 합계 → {(year, lgID): {"bat": {...}, "pit": {...}}}"""
    totals = {}
    for file_name, fields, kind in [("Batting.csv", BAT_FIELDS, "bat"), ("Pitching.csv", PIT_FIELDS, "pit")]:
        for row in read_csv(os.path.join(LAHMAN_DIR, file_name)):
            if not in_scope(row):
                continue
            key = (int(row["yearID"]), row["lgID"])
            if key not in totals:
                totals[key] = {"bat": {f: 0 for f in BAT_FIELDS}, "pit": {f: 0 for f in PIT_FIELDS}}
            for field in fields:
                totals[key][kind][field] += to_int(row.get(field))
    return totals


# ---------------- 팀 ----------------
def load_teams():
    """{(year, teamID): Teams 행} — 1990~2025, AL · NL"""
    teams = {}
    for row in read_csv(os.path.join(LAHMAN_DIR, "Teams.csv")):
        if in_scope(row):
            teams[(int(row["yearID"]), row["teamID"])] = row
    return teams


def load_series():
    """포스트시즌 시리즈 결과 목록 — 1990~2025"""
    series = []
    for row in read_csv(os.path.join(LAHMAN_DIR, "SeriesPost.csv")):
        year = int(row["yearID"])
        if FIRST_SEASON <= year <= LAST_SEASON:
            series.append(row)
    return series


def main_league_and_park(stints, year, teams, park_column):
    """
    stint 목록에서 주 리그(출전량 최대)와 가중 평균 파크 팩터를 구한다.
    park_column: 타자는 "BPF", 투수는 "PPF"
    """
    best_league = None
    best_weight = -1
    league_weight = {}
    park_sum = 0
    weight_sum = 0
    for team_id, league, weight in stints:
        league_weight[league] = league_weight.get(league, 0) + weight
        team = teams.get((year, team_id))
        if team and team[park_column]:
            park_sum += int(team[park_column]) * weight
            weight_sum += weight
    for league, weight in league_weight.items():
        if weight > best_weight:
            best_league = league
            best_weight = weight
    park = park_sum / weight_sum if weight_sum else None
    return best_league, park
