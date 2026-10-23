# 화면 페이지 (서버 렌더링, 질문 · 조건 탐색은 JSON API 사용 — chat/views.py)
#   /                        메인 (선수 검색 · 질문 예시 · 시즌 타임라인 · 전체 선수)
#   /players/<id>/           선수 페이지 (프로필 · 통산/시즌별 기록 탭 · 질문 패널)
#   /compare/?a=&b=          두 선수 비교 (통산 지표 · 질문 패널, F2010)
#   /explore/                조건 탐색 (F2011)
#   /lab/                    RAG 실험실 (검색 설정 비교)

import json
import re
from functools import lru_cache

from urllib.parse import urlencode

from django.conf import settings
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from chat import search
from chat.similar import similar_players

# 지표 표기 · 좋은 방향 (비교 페이지 강조용)
BAT_ROWS = [("PA", "타석", "high", 0), ("AVG", "타율", "high", 3), ("OBP", "출루율", "high", 3), ("SLG", "장타율", "high", 3),
            ("OPS", "OPS", "high", 3), ("OPS_plus", "OPS+", "high", 0), ("ISO", "ISO", "high", 3),
            ("BB_pct", "볼넷 비율 %", "high", 1), ("K_pct", "삼진 비율 %", "low", 1)]
BAT_STAT_ROWS = [("HR", "홈런", "high"), ("RBI", "타점", "high"), ("SB", "도루", "high")]
PIT_ROWS = [("IP", "이닝", None, None), ("ERA", "평균자책점", "low", 2), ("ERA_plus", "ERA+", "high", 0),
            ("FIP", "FIP", "low", 2), ("WHIP", "WHIP", "low", 2), ("K9", "9이닝당 탈삼진", "high", 2),
            ("BB9", "9이닝당 볼넷", "low", 2), ("K_pct", "탈삼진 비율 %", "high", 1)]
PIT_STAT_ROWS = [("W", "승", "high"), ("L", "패", "low"), ("SV", "세이브", "high"), ("SO", "탈삼진", "high")]


def fmt(value, digits):
    if value is None or value == "":
        return "–"
    if digits is None:
        return str(value)
    if digits == 3 and isinstance(value, float) and value < 1:
        return f"{value:.3f}".lstrip("0")
    return f"{value:,.{digits}f}"


@lru_cache(maxsize=1)
def team_names():
    """(teamID, 연도) → 구단 한국어 이름 (팀 시즌 문서 제목에서)"""
    _, docs = search.load_data()
    names = {}
    for d in docs.values():
        if d["doc_type"] == "team_season":
            names[(d["team_id"], d["season"])] = d["title"].split(f" {d['season']}")[0]
    return names


@lru_cache(maxsize=1)
def team_abbrs():
    """(teamID, 연도) → 그해 팀 약자 (팀 시즌 문서의 team_abbr, 예: LAD · ATL · MON)"""
    _, docs = search.load_data()
    return {(d["team_id"], d["season"]): d.get("team_abbr") or d["team_id"]
            for d in docs.values() if d["doc_type"] == "team_season"}


@lru_cache(maxsize=1)
def seasons_by_player():
    _, docs = search.load_data()
    by = {}
    for d in docs.values():
        if d["player_id"]:
            by.setdefault(d["player_id"], []).append(d)
    return by


@lru_cache(maxsize=1)
def season_ranks():
    """{player_id: {연도: {batting|pitching: {키: {rank, of, league, label, qualified}}}}} — build/04 (10위 안)"""
    try:
        with open(settings.SEASON_RANKS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


RANK_KEY = {"IP": "IPouts"}                            # 시즌표 열 키 → 순위 키


def player_or_404(player_id):
    players, _ = search.load_data()
    p = players.get(player_id)
    if p is None:
        raise Http404("선수를 찾을 수 없습니다.")
    return p


# ---------------- 기록 항목 정의 (통산 · 시즌별 공통) ----------------
# 탭: 기본 · 세이버 · 상세 (+ 시즌별만 수비). 항목: (부분 stats|metrics, 키, 표기, 소수 자리 None=문자 그대로, 포스트시즌 표시)
# 포스트시즌은 리그 기준값이 없어 OPS+ · ERA+ · FIP · ERA− · FIP− 를 계산하지 않으므로 숨긴다.
def _s(key, label, post=True):
    return ("stats", key, label, 0, post)


def _m(key, label, digits, post=True):
    return ("metrics", key, label, digits, post)


TABS = [("basic", "기본"), ("sabr", "세이버"), ("detail", "상세")]
STAT_SETS = {
    "batting": {
        "label": "타격",
        "basic": [_s("G", "경기"), _m("PA", "타석", 0), _s("AB", "타수"), _s("RBI", "타점"), _s("R", "득점"),
                  _s("HR", "홈런"), _s("H", "안타"), _s("SB", "도루"), _s("BB", "볼넷"), _s("SO", "삼진"),
                  _m("AVG", "타율", 3), _m("OBP", "출루율", 3), _m("SLG", "장타율", 3), _m("OPS", "OPS", 3)],
        "sabr": [_m("OPS_plus", "OPS+", 0, post=False), _m("ISO", "ISO", 3), _m("BABIP", "BABIP", 3),
                 _m("BB_pct", "볼넷%", 1), _m("K_pct", "삼진%", 1), _m("BB_K", "BB/K", 2), _m("XBH", "장타(XBH)", 0),
                 _m("SecA", "2차 타율", 3), _m("PSN", "파워-스피드", 1), _m("GPA", "GPA", 3), _m("RC", "RC", 1),
                 _m("RC27", "RC/27", 2), _m("BsR", "BsR", 1)],
        "detail": [_s("2B", "2루타"), _s("3B", "3루타"), _m("TB", "루타", 0), _s("SB", "도루"), _s("CS", "도루 실패"),
                   _m("SB_pct", "도루 성공%", 1), _s("IBB", "고의사구"), _s("HBP", "사구"), _s("GIDP", "병살타"),
                   _s("SH", "희생번트"), _s("SF", "희생플라이")],
    },
    "pitching": {
        "label": "투구",
        "basic": [_s("G", "경기"), _s("W", "승"), _s("L", "패"), _s("SV", "세이브"), _m("IP", "이닝", None),
                  _s("H", "피안타"), _s("HR", "피홈런"), _s("BB", "볼넷"), _s("SO", "탈삼진"), _s("R", "실점"),
                  _s("ER", "자책점"), _m("BAA", "피안타율", 3), _m("OBP_against", "피출루율", 3),
                  _m("ERA", "평균자책점", 2), _m("WHIP", "WHIP", 2)],
        "sabr": [_m("ERA_plus", "ERA+", 0, post=False), _m("ERA_minus", "ERA−", 0, post=False),
                 _m("FIP", "FIP", 2, post=False), _m("FIP_minus", "FIP−", 0, post=False), _m("K9", "K/9", 2),
                 _m("BB9", "BB/9", 2), _m("HR9", "HR/9", 2), _m("H9", "H/9", 2), _m("K_BB", "K/BB", 2),
                 _m("K_pct", "탈삼진%", 1), _m("BB_pct", "볼넷%", 1), _m("K_BB_pct", "K-BB%", 1),
                 _m("BABIP", "피BABIP", 3)],
        "detail": [_s("GS", "선발"), _s("GF", "경기 마무리"), _s("CG", "완투"), _s("SHO", "완봉"), _s("BFP", "상대 타자"),
                   _s("IBB", "고의사구"), _s("HBP", "사구"), _s("WP", "폭투"), _s("BK", "보크"),
                   _s("SH", "희생번트 허용"), _s("SF", "희생플라이 허용"), _s("GIDP", "병살 유도")],
    },
}
# 수비 탭 — 시즌별 정규시즌만 (Lahman 은 시즌 · 포지션 단위 합계만 있음. OAA · DRS · UZR 은 추적 데이터가 없어 계산 불가)
FIELDING = [("fielding", "pos", "주 포지션", None, False), ("fielding", "G", "경기", 0, False),
            ("fielding", "GS", "선발", 0, False), ("fielding", "IP", "수비 이닝", None, False),
            ("fielding", "TC", "수비 기회", 0, False), ("fielding", "PO", "자살", 0, False),
            ("fielding", "A", "보살", 0, False), ("fielding", "E", "실책", 0, False), ("fielding", "DP", "병살", 0, False),
            ("fielding", "FPCT", "수비율", 3, False), ("fielding", "RF9", "RF/9", 2, False)]
FIELD_POS_KO = {"P": "투수", "C": "포수", "1B": "1루수", "2B": "2루수", "3B": "3루수", "SS": "유격수",
                "LF": "좌익수", "CF": "중견수", "RF": "우익수", "OF": "외야수"}


def kinds_for(p):
    """표시할 기록 종류 — 투수는 투구, 타자는 타격, 투타겸업은 둘 다 (주 역할을 앞에)"""
    if p["two_way"]:
        return ["pitching", "batting"] if p["role"] == "투수" else ["batting", "pitching"]
    return ["pitching"] if p["role"] == "투수" else ["batting"]


def cell(block, part, key, digits):
    if not block:
        return "–"
    value = (block.get(part) or {}).get(key)
    if part == "fielding" and key == "pos":
        return FIELD_POS_KO.get(value, value or "–")
    return fmt(value, digits)


def career_blocks(p):
    """통산 값 — {kind: {"stats", "metrics"}}. 통산 ERA− · FIP− 는 정규시즌 값을 이닝으로 가중 평균"""
    blocks = {k: {"stats": v["stats"], "metrics": dict(v["metrics"])} for k, v in p["career"].items()}
    pit = blocks.get("pitching")
    if pit:
        for key in ("ERA_minus", "FIP_minus"):
            total = weight = 0
            for d in seasons_by_player().get(p["player_id"], []):
                m = (d.get("metrics") or {}).get("pitching") or {}
                outs = ((d.get("stats") or {}).get("pitching") or {}).get("IPouts", 0)
                if d["doc_type"] == "season_regular" and m.get(key) is not None and outs:
                    total += m[key] * outs
                    weight += outs
            pit["metrics"][key] = round(total / weight) if weight else None
    return blocks


def career_tables(p):
    """통산 — {탭: [(종류 표기, [(항목, 값)])]}"""
    blocks = career_blocks(p)
    out = {tab: [] for tab, _ in TABS}
    for kind in kinds_for(p):
        block = blocks.get(kind)
        if not block:
            continue
        for tab, _ in TABS:
            out[tab].append((STAT_SETS[kind]["label"],
                             [(label, cell(block, part, key, d)) for part, key, label, d, _ in STAT_SETS[kind][tab]]))
    return out


def season_table(p, post, tab):
    """시즌별 표 — {"groups": [(머리줄, 칸 수)], "headers": [...], "rows": [{season, teams, rounds, cells}]}"""
    abbrs = team_abbrs()
    doc_type = "season_post" if post else "season_regular"
    docs = sorted((d for d in seasons_by_player().get(p["player_id"], []) if d["doc_type"] == doc_type),
                  key=lambda d: d["season"])
    columns, groups = [], []
    if tab == "fielding":
        if not post:
            groups.append(("수비", len(FIELDING)))
            columns = [("fielding", i) for i in FIELDING]
    else:
        for kind in kinds_for(p):
            items = [i for i in STAT_SETS[kind][tab] if i[4] or not post]
            if items:
                groups.append((STAT_SETS[kind]["label"], len(items)))
                columns += [(kind, i) for i in items]
    rows = []
    ranks_by_year = season_ranks().get(p["player_id"], {}) if not post else {}
    for d in docs:
        metrics, stats = d.get("metrics") or {}, d.get("stats") or {}
        year_ranks = ranks_by_year.get(str(d["season"]), {})
        cells = []
        for kind, (part, key, _, digits, _) in columns:
            if kind == "fielding":
                block = {"fielding": metrics["fielding"]} if metrics.get("fielding") else None
            else:
                block = {"stats": stats.get(kind), "metrics": metrics.get(kind)} if stats.get(kind) else None
            r = (year_ranks.get(kind) or {}).get(RANK_KEY.get(key, key)) if block and kind != "fielding" else None
            tip = ""
            if r:
                basis = (" · 규정 타석 이상" if kind == "batting" else " · 규정 이닝 이상") if r["qualified"] else ""
                tip = f"{r['league']} {r['label']} {r['rank']}위 ({r['of']}명 중{basis})"
            cells.append({"v": cell(block, part, key, digits), "rank": r["rank"] if r else None, "tip": tip})
        rows.append({"season": d["season"],
                     "teams": "/".join(abbrs.get((t, d["season"]), t) for t in d.get("teams", [])),   # 시즌 중 이적: NYY/LAD
                     "rounds": " → ".join(dict.fromkeys(round_label(r) for r in d.get("rounds", []))),
                     "cells": cells})
    if tab == "fielding" and post:
        rows = []
    return {"groups": groups, "headers": [i[2] for _, i in columns], "rows": rows}


def career_rows(p, metric_rows, stat_rows, kind):
    block = p["career"].get(kind)
    if not block:
        return []
    rows = [(label, fmt(block["stats"].get(key), 0)) for key, label, _ in stat_rows]
    rows += [(label, fmt(block["metrics"].get(key), digits)) for key, label, _, digits in metric_rows]
    return rows


def round_label(code):
    """포스트시즌 라운드 코드(WS, NLCS, ALDS1 …) → 약어 WC · DS · CS · WS (리그 · 번호 제외)"""
    return "WS" if code == "WS" else code[2:4]


def season_rows(p):
    names = team_names()
    rows = []
    for d in sorted(seasons_by_player().get(p["player_id"], []), key=lambda d: (d["season"], d["doc_type"])):
        bat = d["metrics"].get("batting") or {}
        pit = d["metrics"].get("pitching") or {}
        bs = d["stats"].get("batting") or {}
        ps = d["stats"].get("pitching") or {}
        rows.append({
            "season": d["season"],
            "post": d["doc_type"] == "season_post",
            "teams": ", ".join(names.get((t, d["season"]), t) for t in d.get("teams", [])),
            "bat": bool(bat) and bat.get("PA", 0) >= 1,
            "pit": bool(pit) and ps.get("IPouts", 0) >= 1,
            "PA": bat.get("PA"), "AVG": fmt(bat.get("AVG"), 3), "OPS": fmt(bat.get("OPS"), 3),
            "OPS_plus": fmt(bat.get("OPS_plus"), 0), "HR": bs.get("HR"), "SB": bs.get("SB"),
            "IP": pit.get("IP"), "W": ps.get("W"), "L": ps.get("L"), "SV": ps.get("SV"),
            "ERA": fmt(pit.get("ERA"), 2), "ERA_plus": fmt(pit.get("ERA_plus"), 0), "FIP": fmt(pit.get("FIP"), 2),
            "SO": ps.get("SO"),
            "rounds": " → ".join(dict.fromkeys(round_label(r) for r in d.get("rounds", []))),
        })
    return rows


def team_abbr_list(p):
    """소속 구단 약자 — 처음 뛴 순서, 그 시즌 약자 (예: CLE · MIL · NYY, 몬트리올 시절은 MON)"""
    abbrs = team_abbrs()
    out = []
    for d in sorted((d for d in seasons_by_player().get(p["player_id"], []) if d["doc_type"] == "season_regular"),
                    key=lambda d: d["season"]):
        for t in d.get("teams", []):
            a = abbrs.get((t, d["season"]), t)
            if a not in out:
                out.append(a)
    return out


def highlight_tiles(p):
    """상세 페이지 상단 큰 숫자 타일 (통산 대표 기록)"""
    tiles = []
    pit, bat = p["career"].get("pitching"), p["career"].get("batting")
    if pit and (p["role"] == "투수" or p["two_way"]):
        m, s = pit["metrics"], pit["stats"]
        tiles += [("평균자책점", fmt(m.get("ERA"), 2)), ("ERA+", fmt(m.get("ERA_plus"), 0)),
                  ("탈삼진", fmt(s.get("SO"), 0)), (f"승 · 패", f"{s.get('W', 0)}–{s.get('L', 0)}")]
    if bat and (p["role"] == "타자" or p["two_way"]):
        m, s = bat["metrics"], bat["stats"]
        tiles += [(f"OPS · {fmt(m.get('AVG'), 3)} / {fmt(m.get('OBP'), 3)} / {fmt(m.get('SLG'), 3)}", fmt(m.get("OPS"), 3)),
                  ("OPS+", fmt(m.get("OPS_plus"), 0)), ("홈런", fmt(s.get("HR"), 0)), ("도루", fmt(s.get("SB"), 0))]
    return tiles[:6]


# ---------------- 메인: 질문 예시 · 시즌 타임라인 ----------------
# 질문 예시 (누르면 선수 페이지에서 바로 질문) — (선수 ID, 표시 이름, 질문, 비교 선수 ID)
EXAMPLES = [
    ("ohtansh01", "오타니 쇼헤이", "2023 시즌 투타 성적은?", ""),
    ("ryuhy01", "류현진", "2019 시즌은 어땠어?", ""),
    ("kershcl01", "클레이튼 커쇼", "2020 월드시리즈 우승 때 활약은?", ""),
    ("ryuhy01", "류현진 vs 클레이튼 커쇼", "2019 시즌 투구 비교", "kershcl01"),
    ("jeterde01", "데릭 지터", "1996 신인왕 시즌 성적은?", ""),
    ("pujolal01", "앨버트 푸홀스", "2011 월드시리즈 3차전 3홈런 경기는?", ""),
    ("troutmi01", "마이크 트라웃", "통산 OPS+는 얼마야?", ""),
    ("kimha01", "김하성", "골드글러브를 받은 해의 수비 기록은?", ""),
]
# 규정 기준 팀 경기 수 (1994 · 1995 파업, 2020 단축 시즌)
TEAM_GAMES = {1994: 115, 1995: 144, 2020: 60}
WS_RESULT = re.compile(r"월드시리즈 승리 \((\d+)승 (\d+)패, 상대 ([^)]+)\)")


@lru_cache(maxsize=1)
def timeline():
    """연도별 { year, ws, mvp, cy, hr, avg, era, so }
    - 월드시리즈: 팀 시즌 기록 문서
    - 수상 · 부문 1위: data/processed/season_leaders.json (build/03 — Lahman AL · NL 전체 선수 기준, 리그 구분)
      서비스 선수는 id 가 있어 선수 페이지로 연결, 아닌 선수는 이름만"""
    _, docs = search.load_data()
    with open(settings.SEASON_LEADERS_PATH, encoding="utf-8") as f:
        leaders = json.load(f)
    years = {}
    for y in sorted(int(k) for k in leaders):
        row = leaders.get(str(y), {})
        conv = lambda x: {"id": x.get("player_id"), "name": x["name"], "value": x.get("value"), "league": x.get("league")}
        years[y] = {"year": y, "ws": None,
                    "mvp": [conv(x) for x in row.get("mvp", [])], "cy": [conv(x) for x in row.get("cy", [])],
                    "milestones": [{**conv(x), "label": x["label"]} for x in row.get("milestones", [])],
                    **{k: conv(row[k]) if row.get(k) else None for k in ("hr", "avg", "era", "so")}}
    for d in docs.values():
        y = d.get("season")
        if y in years and d["doc_type"] == "team_season" and "월드시리즈 우승" in d["text"]:
            m = WS_RESULT.search(d["text"])
            years[y]["ws"] = {"team": d["title"].split(f" {y}")[0], "abbr": d.get("team_abbr", ""),
                              "result": f"{m.group(1)}승 {m.group(2)}패" if m else "", "opponent": m.group(3) if m else ""}
    return [years[y] for y in sorted(years)]


def chart_series(p):
    """커리어 그래프용 정규시즌 값 — 표본이 적은 시즌(50타석 · 10이닝 미만)은 비율 지표를 비운다"""
    abbrs = team_abbrs()
    rows = []
    for d in sorted((d for d in seasons_by_player().get(p["player_id"], []) if d["doc_type"] == "season_regular"),
                    key=lambda d: d["season"]):
        bs, bm = d["stats"].get("batting") or {}, d["metrics"].get("batting") or {}
        ps, pm = d["stats"].get("pitching") or {}, d["metrics"].get("pitching") or {}
        pa, outs = bm.get("PA", 0), ps.get("IPouts", 0)
        volume = []
        if pa:
            volume.append(f"{pa}타석")
        if outs:
            volume.append(f"{pm.get('IP')}이닝")
        rows.append({
            "season": d["season"], "teams": "/".join(abbrs.get((t, d["season"]), t) for t in d.get("teams", [])),
            "pa_text": f"{pa}타석" if pa else "", "ip_text": f"{pm.get('IP')}이닝" if outs else "",
            "ops_plus": bm.get("OPS_plus") if pa >= 50 else None, "avg": bm.get("AVG") if pa >= 50 else None,
            "hr": bs.get("HR") if bs else None,
            "era_plus": pm.get("ERA_plus") if outs >= 30 else None, "era": pm.get("ERA") if outs >= 30 else None,
            "so": ps.get("SO") if ps else None,
        })
    return rows


def chart_metrics(p):
    """역할에 맞는 지표 버튼 [(키, 표기)] — 주 역할을 앞에"""
    bat = [("ops_plus", "OPS+"), ("hr", "홈런"), ("avg", "타율")]
    pit = [("era_plus", "ERA+"), ("so", "탈삼진"), ("era", "평균자책점")]
    if p["two_way"]:
        return pit + bat if p["role"] == "투수" else bat + pit
    return pit if p["role"] == "투수" else bat


# ---------------- 페이지 ----------------
@lru_cache(maxsize=1)
def team_options():
    """구단 선택창 — [(현재 약자, 한국어 구단 이름)] (2025 시즌 팀 기록 기준, 이름순)"""
    _, docs = search.load_data()
    teams = {}
    for d in docs.values():
        if d["doc_type"] == "team_season" and d["season"] == 2025:
            teams[d["title"].split(" 2025")[0]] = d.get("team_abbr", "")
    return sorted(((abbr, name) for name, abbr in teams.items()), key=lambda x: x[1])


def home(request):
    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    sort = request.GET.get("sort", "name")
    team = request.GET.get("team", "")
    rows = search.player_list()
    players, _ = search.load_data()
    options = team_options()
    team_name = dict(options).get(team, "")
    if q:
        ql = q.lower()
        rows = [r for r in rows if any(ql in n.lower() for n in [r["name_ko"], r["name_en"], *r["aliases"]])]   # 별칭 포함
    if role in ("투수", "타자"):
        rows = [r for r in rows if r["role"] == role]
    if team_name:                                          # 그 구단(현재 프랜차이즈, 옛 이름 시절 포함)에서 한 번이라도 뛴 선수
        rows = [r for r in rows if team_name in players[r["player_id"]].get("franchises", players[r["player_id"]]["teams"])]
    if sort == "recent":                                   # 최근: 활약 마지막 시즌이 늦은 순 (같으면 이름순)
        rows.sort(key=lambda r: (-r["last_season"], r["name_ko"]))
    else:                                                  # 이름순: 한국어 이름
        rows.sort(key=lambda r: r["name_ko"])
    for r in rows:
        p = players[r["player_id"]]
        r["awards"] = len(p["awards"])
        r["teams"] = p["teams"][-1] if p["teams"] else ""
    page = Paginator(rows, 24).get_page(request.GET.get("page"))

    params = {"q": q, "role": role, "sort": sort, "team": team}

    def link(**change):
        """현재 조건에서 일부만 바꾼 주소 (빈 값은 뺌) — 버튼 · 페이지 이동용"""
        merged = {k: v for k, v in {**params, **change}.items() if v}
        return "?" + urlencode(merged) + "#players"

    roles = [("", "전체"), ("투수", "투수"), ("타자", "타자")]
    sorts = [("name", "이름순"), ("recent", "최근")]
    return render(request, "chat/home.html", {
        "page": page, "q": q, "role": role, "sort": sort, "team": team, "team_name": team_name,
        "total": len(rows), "player_total": len(players),
        "role_tabs": [(label, link(role=value, page=""), value == role) for value, label in roles],
        "role_pos": [v for v, _ in roles].index(role) if role in ("투수", "타자") else 0,
        "sort_tabs": [(label, link(sort=value, page=""), value == sort) for value, label in sorts],
        "sort_pos": 1 if sort == "recent" else 0,
        "team_options": options,
        "clear_q": link(q="", page=""),
        "prev_link": link(page=page.previous_page_number()) if page.has_previous() else "",
        "next_link": link(page=page.next_page_number()) if page.has_next() else "",
        "examples": [{"id": e[0], "name": e[1], "q": e[2], "compare": e[3]} for e in EXAMPLES if e[0] in players],
        "timeline": timeline(),
        "tl_first": timeline()[0]["year"], "tl_last": timeline()[-1]["year"],
    })


@ensure_csrf_cookie
def player_detail(request, player_id):
    p = player_or_404(player_id)
    return render(request, "chat/player.html", {
        "p": p,
        "tiles": highlight_tiles(p),
        "team_abbrs": team_abbr_list(p),
        "bat_rows": career_rows(p, BAT_ROWS, BAT_STAT_ROWS, "batting"),
        "pit_rows": career_rows(p, PIT_ROWS, PIT_STAT_ROWS, "pitching"),
        "career": career_tables(p),
        "similar": similar_players(p["player_id"]),
        "chart": chart_series(p),
        "chart_metrics": chart_metrics(p),
        "career_tabs": TABS,
        "season_tabs": TABS + [("fielding", "수비")],
        "season_tables": [(kind, tab, season_table(p, kind == "post", tab))
                          for kind in ("regular", "post") for tab in ("basic", "sabr", "detail", "fielding")],
        "seasons": season_rows(p),
        "regular_count": sum(1 for s in season_rows(p) if not s["post"]),
        "post_count": sum(1 for s in season_rows(p) if s["post"]),
        "players_json": search.player_list(),
        "suggestions": [f"{p['best_season']} 시즌 성적은?" if p.get("best_season") else "최고 시즌은?",
                        "플레이 스타일은?", "수상 경력은?", "포스트시즌 성적은?"],
    })


# 리그 대비 지수 (D1) — (키, 표기, 좋은 방향, 출처 relative | metrics)
BAT_REL_ROWS = [("OPS_plus", "OPS+", "high", "metrics"), ("AVG_idx", "타율", "high", "relative"),
                ("OBP_idx", "출루율", "high", "relative"), ("SLG_idx", "장타율", "high", "relative"),
                ("HR_idx", "홈런 비율", "high", "relative"), ("BB_idx", "볼넷 비율", "high", "relative"),
                ("K_idx", "삼진 비율", "low", "relative")]
PIT_REL_ROWS = [("ERA_plus", "ERA+", "high", "metrics"), ("K_idx", "탈삼진 비율", "high", "relative"),
                ("BB_idx", "볼넷 비율", "low", "relative"), ("HR9_idx", "9이닝당 피홈런", "low", "relative"),
                ("WHIP_idx", "WHIP", "low", "relative")]


def relative_rows(a, b, rows, kind):
    """리그 대비 지수 비교 줄 — 100 = 그 시즌 리그 평균"""
    ba, bb = a["career"].get(kind), b["career"].get(kind)
    if not ba or not bb:
        return []
    out = []
    for key, label, better, part in rows:
        va, vb = (ba.get(part) or {}).get(key), (bb.get(part) or {}).get(key)
        win = ""
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and va != vb:
            win = "a" if (va > vb) == (better == "high") else "b"
        out.append({"label": label + (" (낮을수록 좋음)" if better == "low" else ""),
                    "a": fmt(va, 0), "b": fmt(vb, 0), "win": win})
    return out


def compare_rows(a, b, metric_rows, stat_rows, kind):
    ba, bb = a["career"].get(kind), b["career"].get(kind)
    if not ba or not bb:
        return []
    rows = []
    items = [(k, label, better, 0, "stats") for k, label, better in stat_rows]
    items += [(k, label, better, digits, "metrics") for k, label, better, digits in metric_rows]
    for key, label, better, digits, part in items:
        va, vb = ba[part].get(key), bb[part].get(key)
        win = ""
        if better and isinstance(va, (int, float)) and isinstance(vb, (int, float)) and va != vb:
            win = "a" if (va > vb) == (better == "high") else "b"
        rows.append({"label": label, "a": fmt(va, digits), "b": fmt(vb, digits), "win": win})
    return rows


@ensure_csrf_cookie
def compare(request):
    a_id, b_id = request.GET.get("a", ""), request.GET.get("b", "")
    players, _ = search.load_data()
    context = {"players_json": search.player_list(), "a_pre": players.get(a_id)}   # 첫 선수만 정해진 경우 미리 채움
    if a_id and b_id:
        a, b = player_or_404(a_id), player_or_404(b_id)
        context.update({
            "a": a, "b": b,
            "bat_rows": compare_rows(a, b, BAT_ROWS, BAT_STAT_ROWS, "batting"),
            "pit_rows": compare_rows(a, b, PIT_ROWS, PIT_STAT_ROWS, "pitching"),
            "rel_tables": [("투구", relative_rows(a, b, PIT_REL_ROWS, "pitching")),
                           ("타격", relative_rows(a, b, BAT_REL_ROWS, "batting"))],
            "suggestions": ["통산 성적 비교", "포스트시즌 비교", "수상 경력 비교"],
        })
    return render(request, "chat/compare.html", context)


@ensure_csrf_cookie
def explore_page(request):
    """조건 탐색 (F2011) — 화면만, 탐색은 /api/explore"""
    return render(request, "chat/explore.html")


@ensure_csrf_cookie
def lab_page(request):
    """RAG 실험실 — 검색 설정 2가지 비교 화면 (실행은 /api/lab)"""
    return render(request, "chat/lab.html", {
        "players_json": search.player_list(),
        "chunk_options": ["1000/200", "500/100", "2000/300"],
        "lab_defaults": [("A", "1000/200", 3, 4, "similarity", 0.7), ("B", "1000/200", 3, 4, "mmr", 0.7)],
    })
