# 02. record_docs.json 만들기 — 기록 문서 (외부 문서 컬렉션, source = 기록 데이터)
# 실행: python build/02_build_record_docs.py   (collect/ 01~03 먼저 실행)
#
# 입력 : data/raw/lahman/*.csv, data/raw/wikidata/players_wikidata.csv
# 출력 : data/processed/record_docs.json
#
# 문서 종류 (doc_type)
#   season_regular : 선수 × 정규시즌 1시즌
#   season_post    : 선수 × 포스트시즌 1시즌 (출전 라운드 포함)
#   team_season    : 팀 × 시즌 (성적 · 피타고리안 · 포스트시즌 결과)
#
# 위키 문서와 같은 스키마(page_id 대신 doc_id)로 만들어 한 컬렉션에서 함께 검색한다.
# 기록 문서는 청킹하지 않는다: 문서 1개 = 청크 1개.
# text 에는 선수명 · 시즌 · 지표 이름을 모두 넣어 숫자만 다른 문서끼리 헷갈리지 않게 한다.

import json
import os
import time

import lahman_loader as L
import metrics as MET
import names_ko as K
from seasons import compute_all

SOURCE = "기록 데이터(Lahman)"
SOURCE_URL = "https://sabr.org/lahman-database/"
TODAY = time.strftime("%Y-%m-%d")


def fmt3(value):
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


def team_label(teams, year, team_id):
    team = teams.get((year, team_id))
    if team is None:
        return team_id
    return K.FRANCHISE_KO.get(team["franchID"], team["name"])


def batting_line(stats, m):
    return (f"타격: {stats['G']}경기 {m['PA']}타석 · 타율 {fmt3(m['AVG'])} · 출루율 {fmt3(m['OBP'])} · "
            f"장타율 {fmt3(m['SLG'])} · OPS {fmt3(m['OPS'])} · 홈런 {stats['HR']} · 타점 {stats['RBI']} · "
            f"득점 {stats['R']} · 안타 {stats['H']} · 2루타 {stats['2B']} · 3루타 {stats['3B']} · "
            f"볼넷 {stats['BB']} · 삼진 {stats['SO']} · 도루 {stats['SB']} (도루 실패 {stats['CS']})")


def batting_sabr_line(m):
    return (f"세이버 지표(타격): OPS+ {fmt(m['OPS_plus'], 0)} · ISO {fmt3(m['ISO'])} · BABIP {fmt3(m['BABIP'])} · "
            f"볼넷 비율 {fmt(m['BB_pct'], 1)}% · 삼진 비율 {fmt(m['K_pct'], 1)}% · BB/K {fmt(m['BB_K'])} · "
            f"RC {fmt(m['RC'], 1)} · RC/27 {fmt(m['RC27'])} · BsR {fmt(m['BsR'], 1)} · "
            f"SecA {fmt3(m['SecA'])} · GPA {fmt3(m['GPA'])} · 파워-스피드 지수 {fmt(m['PSN'], 1)}")


def pitching_line(stats, m):
    return (f"투구: {stats['W']}승 {stats['L']}패 {stats['SV']}세이브 · {stats['G']}경기 {stats['GS']}선발 · "
            f"{m['IP']}이닝 · 평균자책점 {fmt(m['ERA'])} · WHIP {fmt(m['WHIP'])} · 탈삼진 {stats['SO']} · "
            f"볼넷 {stats['BB']} · 피안타 {stats['H']} · 피홈런 {stats['HR']} · 상대 타자 {stats['BFP']}명")


def pitching_sabr_line(m):
    return (f"세이버 지표(투구): FIP {fmt(m['FIP'])} · ERA+ {fmt(m['ERA_plus'], 0)} · ERA- {fmt(m['ERA_minus'], 0)} · "
            f"FIP- {fmt(m['FIP_minus'], 0)} · 9이닝당 탈삼진 {fmt(m['K9'])} · 9이닝당 볼넷 {fmt(m['BB9'])} · "
            f"9이닝당 피홈런 {fmt(m['HR9'])} · 탈삼진 비율 {fmt(m['K_pct'], 1)}% · 볼넷 비율 {fmt(m['BB_pct'], 1)}% · "
            f"K-BB% {fmt(m['K_BB_pct'], 1)}% · K/BB {fmt(m['K_BB'])} · 피BABIP {fmt3(m['BABIP'])}")


def main():
    data = compute_all()
    teams = data["teams"]
    docs = []

    # 선수 이름 · ID
    name_of = {}
    for bbref, link in data["candidates"].items():
        pid = data["lahman_id"].get(bbref)
        if pid:
            name_of[pid] = (bbref, link["name_ko"], link["name_en"])

    # ---------------- 1. 정규시즌 ----------------
    for pid, seasons in data["seasons"].items():
        bbref, name_ko, name_en = name_of[pid]
        role_info = data["roles"].get(pid, {"role": "타자", "two_way": False})
        for year, season in sorted(seasons.items()):
            team_names = [team_label(teams, year, t) for t in season["teams"]]
            lines = [f"{name_ko} ({name_en}) · {year} 정규시즌 · {', '.join(team_names)}"]
            stats = {}
            metrics = {}
            bat = season["bat"]
            pit = season["pit"]
            # 투수의 타석 · 야수의 짧은 등판은 문서 text 에서 뺀다 (값은 stats 에 남김)
            # 투타겸업 선수는 둘 다 표시
            is_pitcher = role_info["role"] == "투수"
            two_way = role_info["two_way"]
            show_bat = bat and bat["metrics"]["PA"] >= 20 and (not is_pitcher or two_way)
            show_pit = pit and pit["stats"]["IPouts"] >= 3 and (is_pitcher or two_way)
            if show_pit and not show_bat:
                pass
            elif not show_bat and not show_pit:
                # 역할과 다른 기록만 있는 시즌 (예: 야수의 짧은 등판만) → 있는 쪽을 그대로 표시
                show_bat = bat and bat["metrics"]["PA"] >= 20
                show_pit = pit and pit["stats"]["IPouts"] >= 3
            parts = []
            if show_bat:
                parts.append([batting_line(bat["stats"], bat["metrics"]), batting_sabr_line(bat["metrics"])])
            if show_pit:
                pitch = [pitching_line(pit["stats"], pit["metrics"]), pitching_sabr_line(pit["metrics"])]
                if is_pitcher:
                    parts.insert(0, pitch)                 # 투수는 투구를 먼저
                else:
                    parts.append(pitch)
            for part in parts:
                lines += part
            if season["fld"]:
                f = season["fld"]
                pos = K.FIELD_POS_KO.get(f["pos"], f["pos"])
                lines.append(f"수비({pos}): {f['stats']['G']}경기 · 수비율 {fmt3(f['metrics']['FPCT'])} · "
                             f"9이닝당 레인지 팩터 {fmt(f['metrics']['RF9'])} · 실책 {f['stats']['E']}")
            if not show_bat and not show_pit:
                continue
            if bat:
                stats["batting"] = bat["stats"]
                metrics["batting"] = bat["metrics"]
            if pit:
                stats["pitching"] = pit["stats"]
                metrics["pitching"] = pit["metrics"]
            if season["fld"]:
                f = season["fld"]
                metrics["fielding"] = {"pos": f["pos"], **f["stats"], "IP": MET.ip_text(f["stats"]["InnOuts"]),
                                       "TC": f["stats"]["PO"] + f["stats"]["A"] + f["stats"]["E"], **f["metrics"]}
            docs.append({
                "doc_id": f"rec:{bbref}:{year}:regular",
                "title": f"{name_ko} {year} 정규시즌 기록",
                "url": SOURCE_URL,
                "source": SOURCE,
                "doc_type": "season_regular",
                "player_id": bbref,
                "related_player": name_ko,
                "season": year,
                "teams": season["teams"],
                "stats": stats,
                "metrics": metrics,
                "text": "\n".join(lines),
                "collected_at": TODAY,
            })

    # ---------------- 2. 포스트시즌 ----------------
    for pid, years in data["post"].items():
        bbref, name_ko, name_en = name_of[pid]
        for year, p in sorted(years.items()):
            rounds = sorted(p["rounds"], key=K.round_depth)
            team_names = [team_label(teams, year, t) for t in p["teams"]]
            lines = [f"{name_ko} ({name_en}) · {year} 포스트시즌 · {', '.join(team_names)}",
                     "출전 라운드: " + ", ".join(K.round_ko(r) for r in rounds)]
            stats = {}
            metrics = {}
            role_info = data["roles"].get(pid, {"role": "타자", "two_way": False})
            is_pitcher = role_info["role"] == "투수"
            if p["bat"] and p["bat"]["metrics"]["PA"] > 0 and (not is_pitcher or role_info["two_way"]):
                lines.append("포스트시즌 " + batting_line(p["bat"]["stats"], p["bat"]["metrics"]))
                stats["batting"] = p["bat"]["stats"]
                metrics["batting"] = p["bat"]["metrics"]
            if p["pit"] and p["pit"]["stats"]["IPouts"] > 0:
                lines.append("포스트시즌 " + pitching_line(p["pit"]["stats"], p["pit"]["metrics"]))
                stats["pitching"] = p["pit"]["stats"]
                metrics["pitching"] = p["pit"]["metrics"]
            if len(lines) == 2:
                continue
            docs.append({
                "doc_id": f"rec:{bbref}:{year}:post",
                "title": f"{name_ko} {year} 포스트시즌 기록",
                "url": SOURCE_URL,
                "source": SOURCE,
                "doc_type": "season_post",
                "player_id": bbref,
                "related_player": name_ko,
                "season": year,
                "teams": p["teams"],
                "rounds": rounds,
                "stats": stats,
                "metrics": metrics,
                "text": "\n".join(lines),
                "collected_at": TODAY,
            })

    # ---------------- 3. 팀-시즌 ----------------
    series_by_team = {}
    for s in data["series"]:
        year = int(s["yearID"])
        for team_id, result in [(s["teamIDwinner"], "승리"), (s["teamIDloser"], "패배")]:
            other = s["teamIDloser"] if result == "승리" else s["teamIDwinner"]
            wins, losses = (s["wins"], s["losses"]) if result == "승리" else (s["losses"], s["wins"])
            series_by_team.setdefault((year, team_id), []).append(
                (K.round_depth(s["round"]), f"{K.round_ko(s['round'])} {result} ({wins}승 {losses}패, 상대 {team_label(teams, year, other)})"))

    import metrics as M
    for (year, team_id), t in sorted(teams.items()):
        m = M.team_metrics(t)
        name = team_label(teams, year, team_id)
        honors = []
        if t["WSWin"] == "Y":
            honors.append("월드시리즈 우승")
        if t["LgWin"] == "Y":
            honors.append(f"{K.LEAGUE_KO[t['lgID']]} 우승")
        if t["DivWin"] == "Y":
            honors.append("지구 우승")
        if t["WCWin"] == "Y":
            honors.append("와일드카드 진출")
        results = [text for _, text in sorted(series_by_team.get((year, team_id), []))]
        lines = [
            f"{name} ({t['name']}) · {year} 시즌 · {K.LEAGUE_KO[t['lgID']]}" + (f" {t['divID']}지구" if t["divID"] else ""),
            f"정규시즌: {t['W']}승 {t['L']}패 (승률 {fmt3(m['W_pct'])}) · 지구 {t['Rank']}위 · "
            f"득점 {t['R']} · 실점 {t['RA']} · 득실차 {m['RD']:+d}",
            f"피타고리안 기대 승률 {fmt3(m['Pythagenpat_pct'])} (기대 승수 {fmt(m['Expected_W'], 1)}승, "
            f"실제와 차이 {fmt(m['Luck'], 1)}승) · 팀 평균자책점 {t['ERA']} · 팀 홈런 {t['HR']}",
            f"홈구장 {t['park']} · 관중 {int(t['attendance']):,}명" if t["attendance"] else f"홈구장 {t['park']}",
        ]
        if honors:
            lines.append("성과: " + ", ".join(honors))
        if results:
            lines.append("포스트시즌: " + " → ".join(results))
        elif year == 1994:
            lines.append("포스트시즌: 1994년은 선수 파업으로 포스트시즌이 열리지 않음")
        docs.append({
            "doc_id": f"rec:team:{team_id}:{year}",
            "title": f"{name} {year} 시즌 팀 기록",
            "url": SOURCE_URL,
            "source": SOURCE,
            "doc_type": "team_season",
            "player_id": "",
            "team_id": team_id,
            "team_abbr": t["teamIDBR"],           # 그해 팀 약자 (Baseball-Reference 기준, 예: LAD · MON · FLA)
            "franch_id": t["franchID"],
            "related_player": "",
            "season": year,
            "metrics": m,
            "text": "\n".join(lines),
            "collected_at": TODAY,
        })

    os.makedirs(L.PROCESSED_DIR, exist_ok=True)
    out_path = os.path.join(L.PROCESSED_DIR, "record_docs.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=1)

    counts = {}
    for d in docs:
        counts[d["doc_type"]] = counts.get(d["doc_type"], 0) + 1
    print("기록 문서:", f"{len(docs):,}건", counts)
    print("저장:", os.path.abspath(out_path))


if __name__ == "__main__":
    main()
