# 구단 시절 합산 (B3) — "카디널스 시절 통산"처럼 구단을 지정한 질문에, 그 구단에서 뛴 시즌 기록을 코드로 합산해 근거로 만든다
#   - 기록 문서는 선수 × 시즌 단위라 시즌 중 이적한 해는 구단별로 나눌 수 없다 → 합산에서 빼고 근거에 밝힌다
#   - 지표는 합산한 원기록으로 다시 계산한다 (LLM 은 계산하지 않고 인용만)

import json
import re
from functools import lru_cache

from rag import config as C

SOURCE_URL = "https://sabr.org/lahman-database/"


@lru_cache(maxsize=1)
def _data():
    """(구단 정보 {franch_id: {name, abbr, team_ids, words}}, 선수별 정규시즌 문서 {player_id: [doc]})"""
    with open(C.RECORD_DOCS_PATH, encoding="utf-8") as f:
        docs = json.load(f)
    franchises, by_player = {}, {}
    for d in docs:
        if d["doc_type"] == "team_season":
            name = d["title"].split(f" {d['season']}")[0]
            f = franchises.setdefault(d["franch_id"], {"name": name, "abbr": set(), "team_ids": set(), "words": set()})
            f["team_ids"].add(d["team_id"])
            if d.get("team_abbr"):
                f["abbr"].add(d["team_abbr"])
            en = re.search(r"\(([^)]+)\)", d["text"].split("\n", 1)[0])
            if d["season"] >= f.get("latest", 0):                   # 이름은 가장 최근 시즌 기준
                f["latest"], f["name"] = d["season"], name
                f["en_nick"] = en.group(1).split()[-1] if en else ""
            # 옛 이름도 인식 (예: 브루클린 다저스 · 엑스포스). 짧은 옛 별칭은 다른 낱말에 섞여 빼고(예: 비스 → 서비스) 4글자 이상만
            f["words"].add(name)
            if len(name.split()[-1]) >= 4:
                f["words"].add(name.split()[-1])
            if en:
                f["words"].add(en.group(1))                         # 영어 전체 이름 (예: Brooklyn Dodgers)
        elif d["doc_type"] == "season_regular":
            by_player.setdefault(d["player_id"], []).append(d)
    for f in franchises.values():
        # 현재 이름의 한국어 · 영어 별칭 (예: 다저스 · Dodgers) · 약자
        f["words"] |= {f["name"], f["name"].split()[-1], f.pop("en_nick")} | f["abbr"]
        f["words"].discard("")
    return franchises, by_player


def find_franchises(texts):
    """질문 · 검색어에 나온 구단 franch_id (긴 이름부터 확인)"""
    franchises, _ = _data()
    found = []
    joined = " ".join(texts)
    pairs = sorted(((w, fid) for fid, f in franchises.items() for w in f["words"] if len(w) >= 2), key=lambda x: -len(x[0]))
    for word, fid in pairs:
        pattern = re.escape(word) if re.search(r"[가-힣]", word) else r"(?<![A-Za-z])" + re.escape(word) + r"(?![A-Za-z])"
        if re.search(pattern, joined) and fid not in found:
            found.append(fid)
    return found[:2]


def _ip(outs):
    return f"{outs // 3}" + {0: "", 1: "⅓", 2: "⅔"}[outs % 3]


def _rate(a, b, digits=3):
    if not b:
        return "–"
    v = a / b
    return f"{v:.{digits}f}".lstrip("0") if digits == 3 and v < 1 else f"{v:.{digits}f}"


def era_evidence(player_id, player_name, franch_id, include_batting, include_pitching):
    """그 선수의 해당 구단 시절 합산 근거 하나 (뛴 적이 없으면 None)"""
    franchises, by_player = _data()
    f = franchises[franch_id]
    only, mixed = [], []
    for d in sorted(by_player.get(player_id, []), key=lambda d: d["season"]):
        teams = set(d.get("teams", []))
        if teams & f["team_ids"]:
            (only if teams <= f["team_ids"] else mixed).append(d)
    if not only and not mixed:
        return None

    lines = [f"[구단 시절 합산] {player_name} · {f['name']} ({'/'.join(sorted(f['abbr']))})",
             f"합산 시즌: {', '.join(str(d['season']) for d in only) or '없음'} (정규시즌, {len(only)}시즌)"]
    bat = {}
    pit = {}
    for d in only:
        for k, v in (d["stats"].get("batting") or {}).items():
            bat[k] = bat.get(k, 0) + v
        for k, v in (d["stats"].get("pitching") or {}).items():
            pit[k] = pit.get(k, 0) + v
    if include_batting and bat.get("AB"):
        pa = bat["AB"] + bat["BB"] + bat["HBP"] + bat["SF"] + bat["SH"]
        tb = bat["H"] + bat["2B"] + 2 * bat["3B"] + 3 * bat["HR"]
        obp_den = bat["AB"] + bat["BB"] + bat["HBP"] + bat["SF"]
        obp = (bat["H"] + bat["BB"] + bat["HBP"]) / obp_den if obp_den else 0
        slg = tb / bat["AB"]
        lines.append(f"타격 합산: {bat['G']}경기 {pa}타석 · 타율 {_rate(bat['H'], bat['AB'])} · 출루율 {_rate(obp, 1)} · "
                     f"장타율 {_rate(slg, 1)} · OPS {_rate(obp + slg, 1)} · 안타 {bat['H']} · 홈런 {bat['HR']} · "
                     f"타점 {bat['RBI']} · 득점 {bat['R']} · 도루 {bat['SB']} · 볼넷 {bat['BB']} · 삼진 {bat['SO']}")
    if include_pitching and pit.get("IPouts"):
        ip = pit["IPouts"] / 3
        lines.append(f"투구 합산: {pit['W']}승 {pit['L']}패 {pit['SV']}세이브 · {pit['G']}경기 {pit['GS']}선발 · "
                     f"{_ip(pit['IPouts'])}이닝 · 평균자책점 {_rate(9 * pit['ER'], ip, 2)} · "
                     f"WHIP {_rate(pit['BB'] + pit['H'], ip, 2)} · 탈삼진 {pit['SO']} · 볼넷 {pit['BB']} · 피홈런 {pit['HR']}")
    if mixed:
        lines.append(f"합산에서 뺀 시즌: {', '.join(str(d['season']) for d in mixed)} "
                     "(시즌 중 이적해 구단별로 나뉜 기록이 없음)")
    lines.append("계산: 이 서비스가 시즌별 기록(Lahman)을 코드로 합산한 값 (OPS+ · ERA+ 같은 리그 보정 지표는 제외)")
    if len(lines) <= 3 and not mixed:
        return None
    return {"id": f"{player_id}:era-{franch_id}", "source": "기록 데이터(Lahman)",
            "title": f"{player_name} {f['name']} 시절 합산", "url": SOURCE_URL, "text": "\n".join(lines), "distance": None}
