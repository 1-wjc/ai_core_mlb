# 01. players.json 만들기 — 선수 1명 = 레코드 1개 (메타데이터 컬렉션 원본, F2001)
# 실행: python build/01_build_players.py   (collect/ 01~03 먼저 실행)
#
# 입력 : data/raw/lahman/*.csv, data/raw/wikidata/players_wikidata.csv
# 출력 : data/processed/players.json
#
# index_text: 선수 1명을 검색용 텍스트 1개로 만든 것 (영화 팩의 줄거리 역할).
#             숫자 · 이름은 원본에서, 문장은 정해진 틀로 만든다 (LLM 미사용).
# 통산은 "1901~2025 범위 안" 통산이다 (1900년 이전 시즌은 포함하지 않음).

import json
import os
import re
import unicodedata
import urllib.parse

import lahman_loader as L
import milestones as MS
import metrics as M
import names_ko as K
from seasons import compute_all

# 특징 문구 판정 기준 (통산 기준, 표본이 충분한 선수만)
MIN_PA_FOR_TRAITS = 1000
MIN_IPOUTS_FOR_TRAITS = 600          # 200이닝


def fmt3(value):
    """0.312 → '.312' (야구 표기)"""
    if value is None:
        return "계산 불가"
    text = f"{value:.3f}"
    return text[1:] if text.startswith("0") else text


def fmt(value, digits=2):
    if value is None:
        return "계산 불가"
    if digits == 0:
        return str(int(value))
    return f"{value:.{digits}f}"


def wiki_url(lang, title):
    return f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


def search_aliases(link, person, name_ko, name_en):
    """검색 별칭 — 화면 이름과 표기가 다른 이름 (한국어 문서 제목 · Wikidata 이름표 · Lahman 영문 이름).
    예: 클레이튼 커쇼 → "클레이턴 커쇼", 타이 코브 → "타이 콥". 영어 이름표는 Lahman 성(last name)이 들어 있을 때만
    (잘못 편집된 이름표 — Mordecai Brown 의 "Cristiano Ronaldo" — 를 거른다)"""
    strip = lambda t: re.sub(r"\s*\(.*\)$", "", t or "").strip()
    fold = lambda t: unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    last = fold(person.get("nameLast", ""))
    candidates = [strip(link["ko_title"]), strip(link.get("label_ko")), f"{person.get('nameFirst', '')} {person.get('nameLast', '')}".strip()]
    if last and last in fold(link.get("label_en") or ""):
        candidates.append(strip(link["label_en"]))
    seen = {name_ko.lower(), name_en.lower()}
    out = []
    for c in candidates:
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def team_name_ko(teams, year, team_id):
    team = teams.get((year, team_id))
    if team is None:
        return team_id
    return K.team_ko(team)


# ---- 리그 대비 지수 (D1 시대 보정 비교) — 100 = 그 시즌 리그 평균 ----
# (키, 분자, 분모) : 시즌마다 "리그 비율 × 선수 분모"를 기대값으로 더해 100 × 실제 합 ÷ 기대 합.
# 리그 값이 0인 시즌(초기 시즌의 삼진 · 상대 타자 등 빈 열)은 실제 · 기대 양쪽에서 뺀다.
def _pa(s):
    return s["AB"] + s["BB"] + s["HBP"] + s["SF"] + s["SH"]


BAT_RELATIVE = [
    ("AVG_idx", lambda s: s["H"], lambda s: s["AB"]),
    ("OBP_idx", lambda s: s["H"] + s["BB"] + s["HBP"], lambda s: s["AB"] + s["BB"] + s["HBP"] + s["SF"]),
    ("SLG_idx", lambda s: s["H"] + s["2B"] + 2 * s["3B"] + 3 * s["HR"], lambda s: s["AB"]),
    ("HR_idx", lambda s: s["HR"], _pa),
    ("BB_idx", lambda s: s["BB"], _pa),
    ("K_idx", lambda s: s["SO"], _pa),
]
PIT_RELATIVE = [
    ("K_idx", lambda s: s["SO"], lambda s: s["BFP"]),
    ("BB_idx", lambda s: s["BB"], lambda s: s["BFP"]),
    ("HR9_idx", lambda s: s["HR"], lambda s: s["IPouts"]),
    ("WHIP_idx", lambda s: s["H"] + s["BB"], lambda s: s["IPouts"]),
]


def relative_indexes(seasons, totals, part):
    """선수 통산 리그 대비 지수 {키: 정수} — part 는 bat | pit"""
    items = BAT_RELATIVE if part == "bat" else PIT_RELATIVE
    actual = {k: 0 for k, _, _ in items}
    expected = {k: 0.0 for k, _, _ in items}
    for year, season in seasons.items():
        block = season.get(part)
        league = (totals.get((year, block["league"])) or {}).get(part) if block else None
        if not league:
            continue
        for key, num, den in items:
            lg_den = den(league)
            if not lg_den or not num(league) or not den(block["stats"]):
                continue
            expected[key] += num(league) / lg_den * den(block["stats"])
            actual[key] += num(block["stats"])
    return {k: round(100 * actual[k] / expected[k]) for k, _, _ in items if expected[k]}


def weighted_average(seasons, part, metric, weight_field):
    """시즌 값을 출전량(타석 · 아웃카운트)으로 가중 평균한다 (OPS+ · ERA+ · FIP 통산용)."""
    total = 0
    weight_sum = 0
    for season in seasons.values():
        block = season.get(part)
        if not block or block["metrics"].get(metric) is None:
            continue
        if weight_field == "PA":
            weight = block["metrics"]["PA"]
        else:
            weight = block["stats"]["IPouts"]
        total += block["metrics"][metric] * weight
        weight_sum += weight
    return total / weight_sum if weight_sum else None


def main():
    data = compute_all()
    reached = MS.compute()                                 # 마일스톤 달성 시즌 (실제 통산 기준)
    teams = data["teams"]
    series = data["series"]

    # 수상 · 올스타 · 명예의 전당
    awards = {}
    for row in L.read_csv(os.path.join(L.LAHMAN_DIR, "AwardsPlayers.csv")):
        year = int(row["yearID"])
        if L.FIRST_SEASON <= year <= L.LAST_SEASON:
            awards.setdefault(row["playerID"], []).append((year, row["awardID"]))
    allstar = {}
    for row in L.read_csv(os.path.join(L.LAHMAN_DIR, "AllstarFull.csv")):
        year = int(row["yearID"])
        if L.FIRST_SEASON <= year <= L.LAST_SEASON:
            allstar.setdefault(row["playerID"], set()).add(year)
    hall = set()
    for row in L.read_csv(os.path.join(L.LAHMAN_DIR, "HallOfFame.csv")):
        if row["inducted"] == "Y" and row["category"] == "Player":
            hall.add(row["playerID"])

    # 월드시리즈 우승팀: {year: teamID}
    ws_winner = {}
    for s in series:
        if s["round"] == "WS":
            ws_winner[int(s["yearID"])] = s["teamIDwinner"]

    players = []
    for bbref, link in data["candidates"].items():
        pid = data["lahman_id"].get(bbref)
        seasons = data["seasons"].get(pid)
        if not seasons:
            continue
        person = data["people"][pid]
        years = sorted(seasons)

        # ---- 주 포지션 · 역할 ----
        role_info = data["roles"].get(pid, {"role": "타자", "main_column": None, "two_way": False})
        main_column = role_info["main_column"]
        primary_position = K.POSITION_KO.get(main_column, "")
        role = role_info["role"]
        two_way = role_info["two_way"]
        if role == "투수":
            g_sum = gs_sum = 0
            for season in seasons.values():
                if season["pit"]:
                    g_sum += season["pit"]["stats"]["G"]
                    gs_sum += season["pit"]["stats"]["GS"]
            primary_position = "선발투수" if gs_sum >= g_sum / 2 else "구원투수"

        # ---- 소속 팀 (처음 뛴 순서) — 그 시대 구단 이름 · 구단 필터용 현재 프랜차이즈 이름 ----
        team_names, franchises = [], []
        for year in years:
            for team_id in seasons[year]["teams"]:
                name = team_name_ko(teams, year, team_id)
                if name not in team_names:
                    team_names.append(name)
                team = teams.get((year, team_id))
                franchise = K.FRANCHISE_KO.get(team["franchID"], name) if team else name
                if franchise not in franchises:
                    franchises.append(franchise)

        # ---- 통산 (범위 안) ----
        bat_sum = {f: 0 for f in L.BAT_FIELDS}
        pit_sum = {f: 0 for f in L.PIT_FIELDS}
        for season in seasons.values():
            if season["bat"]:
                for f in L.BAT_FIELDS:
                    bat_sum[f] += season["bat"]["stats"][f]
            if season["pit"]:
                for f in L.PIT_FIELDS:
                    pit_sum[f] += season["pit"]["stats"][f]
        career = {}
        bat_m = M.batting_metrics(bat_sum)
        # 투수의 타석(내셔널리그 투수 타격 등)은 투타겸업이 아니면 요약에 넣지 않는다
        is_hitter_block = role == "타자" or two_way
        is_pitcher_block = pit_sum["IPouts"] > 0 and (role == "투수" or two_way)
        if is_hitter_block:
            bat_m["OPS_plus"] = M.rnd(weighted_average(seasons, "bat", "OPS_plus", "PA"), 0)
            career["batting"] = {"stats": bat_sum, "metrics": bat_m,
                                 "relative": relative_indexes(seasons, data["league_totals"], "bat")}
        if is_pitcher_block:
            pit_m = M.pitching_metrics(pit_sum)
            pit_m["ERA_plus"] = M.rnd(weighted_average(seasons, "pit", "ERA_plus", "IP"), 0)
            pit_m["FIP"] = M.rnd(weighted_average(seasons, "pit", "FIP", "IP"), 2)
            career["pitching"] = {"stats": pit_sum, "metrics": pit_m,
                                  "relative": relative_indexes(seasons, data["league_totals"], "pit")}

        # ---- 최고 시즌 ----
        best_season = None
        best_value = None
        for year in years:
            season = seasons[year]
            if role == "투수" and season["pit"]:
                value = season["pit"]["metrics"]["ERA_plus"]
                enough = season["pit"]["stats"]["IPouts"] >= (300 if primary_position == "선발투수" else 120)
            elif role == "타자" and season["bat"]:
                value = season["bat"]["metrics"]["OPS_plus"]
                enough = season["bat"]["metrics"]["PA"] >= 300
            else:
                continue
            if enough and value is not None and (best_value is None or value > best_value):
                best_season = year
                best_value = value

        # ---- 수상 ----
        award_list = sorted(awards.get(pid, []))
        major_awards = []
        for year, award_id in award_list:
            if award_id in K.AWARD_KO:
                major_awards.append(f"{year} {K.AWARD_KO[award_id]}")
        allstar_years = sorted(allstar.get(pid, set()))

        # ---- 포스트시즌 ----
        post_summary = []
        for year, p in sorted(data["post"].get(pid, {}).items()):
            deepest = max(p["rounds"], key=K.round_depth)
            won_ws = any(ws_winner.get(year) == team_id for team_id in p["teams"])
            text = f"{year} {K.round_ko(deepest)}" + (" 우승" if won_ws else " 진출")
            post_summary.append(text)

        # ---- 특징 문구 (통산 지표 구간으로 판정) ----
        traits = []
        if "batting" in career and bat_m["PA"] >= MIN_PA_FOR_TRAITS:
            if bat_m["ISO"] is not None and bat_m["ISO"] >= 0.200:
                traits.append("장타력이 뛰어난 파워형 타자 (ISO .200 이상)")
            if bat_m["K_pct"] is not None and bat_m["K_pct"] <= 15:
                traits.append("삼진이 적은 컨택형 타자 (삼진 비율 15% 이하)")
            if bat_m["BB_pct"] is not None and bat_m["BB_pct"] >= 11:
                traits.append("볼넷을 잘 얻는 선구안형 타자 (볼넷 비율 11% 이상)")
            if bat_m["PA"] and bat_sum["SB"] * 600 / bat_m["PA"] >= 20:
                traits.append("도루 능력이 뛰어남 (600타석당 도루 20개 이상)")
            if bat_m["OPS_plus"] is not None and bat_m["OPS_plus"] >= 130:
                traits.append("리그 평균보다 크게 뛰어난 공격력 (통산 OPS+ 130 이상)")
        if "pitching" in career and pit_sum["IPouts"] >= MIN_IPOUTS_FOR_TRAITS:
            pm = career["pitching"]["metrics"]
            if pm["K_pct"] is not None and pm["K_pct"] >= 25:
                traits.append("탈삼진 능력이 뛰어난 투수 (탈삼진 비율 25% 이상)")
            if pm["BB_pct"] is not None and pm["BB_pct"] <= 6:
                traits.append("볼넷이 적은 제구형 투수 (볼넷 비율 6% 이하)")
            if pm["ERA_plus"] is not None and pm["ERA_plus"] >= 120:
                traits.append("리그 평균보다 크게 뛰어난 실점 억제 (통산 ERA+ 120 이상)")
            if pit_sum["SV"] >= 100:
                traits.append("마무리 투수 경력 (통산 세이브 100 이상)")

        # ---- index_text ----
        bats = K.BATS_KO.get(person["bats"], "")
        throws = K.THROWS_KO.get(person["throws"], "")
        country = K.COUNTRY_KO.get(person["birthCountry"], person["birthCountry"])
        position_text = primary_position + (" · 투타겸업" if two_way else "")
        lines = [
            f"{link['name_ko']} ({link['name_en'] or person['nameFirst'] + ' ' + person['nameLast']}) · "
            f"{throws}{bats} {position_text} · {person['birthYear']}년생 · 출신 {country}",
            f"MLB {years[0]}~{years[-1]} 시즌 · 소속: {', '.join(team_names)}",
        ]
        career_lines = []
        if "batting" in career:
            m = career["batting"]["metrics"]
            career_lines.append(
                f"통산 타격({L.FIRST_SEASON}~{L.LAST_SEASON} 범위): 타율 {fmt3(m['AVG'])} · 출루율 {fmt3(m['OBP'])} · "
                f"장타율 {fmt3(m['SLG'])} · OPS {fmt3(m['OPS'])} · OPS+ {fmt(m['OPS_plus'], 0)} · "
                f"홈런 {bat_sum['HR']} · 타점 {bat_sum['RBI']} · 도루 {bat_sum['SB']}")
        if "pitching" in career:
            m = career["pitching"]["metrics"]
            pitching_line = (
                f"통산 투구({L.FIRST_SEASON}~{L.LAST_SEASON} 범위): {pit_sum['W']}승 {pit_sum['L']}패 {pit_sum['SV']}세이브 · "
                f"{m['IP']}이닝 · 평균자책점 {fmt(m['ERA'])} · ERA+ {fmt(m['ERA_plus'], 0)} · "
                f"FIP {fmt(m['FIP'])} · WHIP {fmt(m['WHIP'])} · 탈삼진 {pit_sum['SO']}")
            if role == "투수":
                career_lines.insert(0, pitching_line)      # 투수는 투구를 먼저
            else:
                career_lines.append(pitching_line)
        lines += career_lines
        if best_season:
            s = seasons[best_season]
            if role == "투수":
                pm = s["pit"]["metrics"]
                ps = s["pit"]["stats"]
                lines.append(f"최고 시즌: {best_season} ({ps['W']}승 {ps['L']}패, 평균자책점 {fmt(pm['ERA'])}, "
                             f"ERA+ {fmt(pm['ERA_plus'], 0)})")
            else:
                bm = s["bat"]["metrics"]
                bs = s["bat"]["stats"]
                lines.append(f"최고 시즌: {best_season} (타율 {fmt3(bm['AVG'])}, 홈런 {bs['HR']}, "
                             f"OPS {fmt3(bm['OPS'])}, OPS+ {fmt(bm['OPS_plus'], 0)})")
        if major_awards:
            lines.append("수상: " + ", ".join(major_awards))
        if allstar_years:
            lines.append(f"올스타 선정 {len(allstar_years)}회 ({', '.join(str(y) for y in allstar_years)})")
        if pid in hall:
            lines.append("명예의 전당 헌액")
        milestones = reached.get(pid, [])
        if milestones:
            lines.append("기록 달성: " + ", ".join(f"{m['label']} ({m['season']})" for m in milestones))
        if post_summary:
            lines.append("포스트시즌: " + ", ".join(post_summary))
        if traits:
            lines.append("특징: " + ", ".join(traits))

        players.append({
            "player_id": bbref,
            "lahman_id": pid,
            "name_ko": link["name_ko"],
            "name_en": link["name_en"] or f"{person['nameFirst']} {person['nameLast']}",
            "aliases": search_aliases(link, person, link["name_ko"], link["name_en"] or f"{person['nameFirst']} {person['nameLast']}"),
            "birth_year": person["birthYear"],
            "birth_country": country,
            "bats": bats,
            "throws": throws,
            "role": role,
            "two_way": two_way,
            "primary_position": primary_position,
            "first_season": years[0],
            "last_season": years[-1],
            "teams": team_names,
            "franchises": franchises,
            "awards": major_awards,
            "awards_all": [f"{y} {a}" for y, a in award_list],
            "allstar_years": allstar_years,
            "hall_of_fame": pid in hall,
            "milestones": milestones,
            "career": career,
            "best_season": best_season,
            "postseason_summary": post_summary,
            "traits": traits,
            "ko_wiki": {"title": link["ko_title"], "url": wiki_url("ko", link["ko_title"])},
            "en_wiki": {"title": link["en_title"], "url": wiki_url("en", link["en_title"])},
            "ids": {"mlbam": link["key_mlbam"], "wikidata": link["key_wikidata"], "retro": person["retroID"]},
            "index_text": "\n".join(lines),
        })

    players.sort(key=lambda p: p["player_id"])
    os.makedirs(L.PROCESSED_DIR, exist_ok=True)
    out_path = os.path.join(L.PROCESSED_DIR, "players.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=1)

    # ---- 요약 ----
    pitchers = sum(1 for p in players if p["role"] == "투수")
    print(f"선수 {len(players):,}명 (투수 {pitchers:,} · 타자 {len(players) - pitchers:,})")
    print(f"특징 문구 있음 {sum(1 for p in players if p['traits']):,}명 · "
          f"포스트시즌 출전 {sum(1 for p in players if p['postseason_summary']):,}명 · "
          f"주요 수상 {sum(1 for p in players if p['awards']):,}명")
    print("저장:", os.path.abspath(out_path))


if __name__ == "__main__":
    main()
