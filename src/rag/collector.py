# 질문 시 보충 수집 (F2004 · NF2002 · NF2006)
#   프롬프트 1 검색어 → 위키백과 검색(후보) → 프롬프트 2가 제목 · 요약만 보고 선별 → 본문 수집 · 저장 → 청킹 · 색인
#
# - 선수 본인 문서는 사전 배치(collect/04)로 이미 수집 · 색인되어 있다 (선별 없이 항상 색인).
# - 이미 검색한 검색어는 다시 검색하지 않는다 (manifest 의 keywords 에 "q:언어:검색어" 로 기록).
# - 이미 수집한 문서(page_id)는 후보에서 뺀다.
# - 선별에서 버려진 문서도 manifest 의 rejected 에 남긴다 (명세서 4.2 검증용).
# - 위키 호출이 실패해도 답변은 계속한다 (호출 측에서 예외 처리).

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from rag import config as C

SLEEP = 0.4
MAX_RETRY = 3
CUT_SECTIONS = {
    "en": ["References", "External links", "See also", "Further reading", "Notes", "Sources"],
    "ko": ["각주", "외부 링크", "같이 보기", "참고 문헌", "참조", "주해", "출처"],
}
SOURCE_NAME = {"en": "영어 위키백과", "ko": "한국어 위키백과"}


# ---------------- 위키백과 API ----------------
def call_api(lang, params):
    """위키백과 API 호출. User-Agent 에 연락처, 요청 간 대기, 429 · 5xx 재시도"""
    params = {**params, "format": "json", "formatversion": 2}
    url = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": f"AICoreProject/0.1 ({C.WIKI_CONTACT or 'contact-not-set'}) python-urllib"}
    wait = 2.0
    for attempt in range(MAX_RETRY):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            time.sleep(SLEEP)
            return data
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
            time.sleep(float(e.headers.get("Retry-After") or wait))
            wait *= 2
        except urllib.error.URLError:
            time.sleep(wait)
            wait *= 2
    raise RuntimeError("위키백과 API 재시도 초과")


def search(lang, query, limit):
    """검색 후보: [{lang, page_id, title, summary}] — 요약은 검색 결과 발췌(태그 제거)"""
    data = call_api(lang, {"action": "query", "list": "search", "srsearch": query,
                           "srlimit": limit, "srprop": "snippet"})
    results = []
    for item in data.get("query", {}).get("search", []):
        summary = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
        results.append({"lang": lang, "page_id": item["pageid"], "title": item["title"], "summary": summary})
    return results


def cut_reference_sections(text, names):
    out = []
    for line in text.split("\n"):
        heading = re.match(r"^=+\s*(.+?)\s*=+$", line.strip())
        if heading and heading.group(1) in names:
            break
        out.append(line)
    return "\n".join(out).strip()


def fetch(lang, page_id):
    data = call_api(lang, {"action": "query", "pageids": page_id, "prop": "extracts|info",
                           "explaintext": 1, "exsectionformat": "wiki", "inprop": "url"})
    page = data["query"]["pages"][0]
    if page.get("missing"):
        return None
    return {"page_id": page["pageid"], "title": page["title"], "url": page["fullurl"],
            "text": cut_reference_sections(page.get("extract", ""), CUT_SECTIONS[lang])}


# ---------------- manifest ----------------
def load_manifest():
    if os.path.exists(C.WIKI_MANIFEST_PATH):
        with open(C.WIKI_MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manifest(manifest):
    with open(C.WIKI_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)


def safe_file_name(text):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text)[:80]


# ---------------- 수집 ----------------
def collect_for_question(player_id, player_name, related_player, question, queries, select_fn, index_fn):
    """
    player_id      : 선수 ID (bbref)
    player_name    : 프롬프트 2 에 보여 줄 이름 (한/영)
    related_player : 문서 JSON 의 관련 항목 (한국어 이름)
    queries        : 프롬프트 1 이 만든 검색어 (원 질문 제외)
    select_fn      : (player_name, question, candidates) → 고른 후보 번호 목록 (프롬프트 2)
    index_fn       : (player_id, 저장한 파일 경로 목록) → 색인한 청크 수
    반환           : 수집 결과 요약 (진행 상태 표시 · 검증용)
    """
    manifest = load_manifest()
    entry = manifest.setdefault(player_id, {"keywords": [], "titles": [], "page_ids": [], "files": []})
    entry.setdefault("rejected", [])
    info = {"searched": [], "skipped": [], "candidates": [], "selected": [], "rejected": [], "chunks": 0}

    # 1) 검색어별 위키 검색 — 이미 검색한 검색어는 건너뜀
    #    영어 위키 검색어만, 최대 COLLECT_QUERIES 개 (실측: 한국어 검색 후보는 질문과 무관한 문서가 대부분, 호출 시간만 늘어남)
    candidates = {}
    english = [q for q in queries if not re.search(r"[가-힣]", q)][:C.COLLECT_QUERIES]
    for query in english:
        lang = "en"
        key = f"q:{lang}:{query.strip().lower()}"
        if key in entry["keywords"]:
            info["skipped"].append(query)
            continue
        info["searched"].append(query)
        entry["keywords"].append(key)
        for c in search(lang, query, C.COLLECT_CANDIDATES):
            if c["page_id"] in entry["page_ids"] or (c["lang"], c["page_id"]) in candidates:
                continue                       # 이미 수집한 문서 · 중복 후보 제외
            c["query"] = query
            candidates[(c["lang"], c["page_id"])] = c
    candidates = list(candidates.values())
    info["candidates"] = [c["title"] for c in candidates]
    if not candidates:
        save_manifest(manifest)
        return info

    # 2) 프롬프트 2 — 제목 · 요약만 보고 선별
    picked = select_fn(player_name, question, candidates)[:C.COLLECT_MAX_PICK]

    # 3) 선별 문서 본문 · URL 수집 → 문서 JSON 저장
    paths = []
    for i, c in enumerate(candidates, 1):
        if i not in picked:
            info["rejected"].append(c["title"])
            entry["rejected"].append({"title": c["title"], "lang": c["lang"], "query": c["query"]})
            continue
        page = fetch(c["lang"], c["page_id"])
        if not page or len(page["text"]) < C.COLLECT_MIN_CHARS:
            info["rejected"].append(c["title"] + " (본문 짧음)")
            continue
        doc = {**page, "source": SOURCE_NAME[c["lang"]], "player_id": player_id, "related_player": related_player,
               "search_query": c["query"], "collected_by": "question", "collected_at": date.today().isoformat()}
        name = f"{player_id}_{c['lang']}_{safe_file_name(page['title'])}.json"
        path = os.path.join(C.WIKI_DOCS_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        entry["titles"].append(page["title"])
        entry["page_ids"].append(page["page_id"])
        entry["files"].append(name)
        info["selected"].append(page["title"])
        paths.append(path)
    save_manifest(manifest)

    # 4) 청킹 · 색인 (외부 문서 컬렉션, 선수 범위)
    if paths:
        info["chunks"] = index_fn(player_id, paths)
    return info
