# 04. 선수 본인 위키 문서 수집 (한국어 · 영어) → 문서 JSON + manifest
# 실행: python collect/04_collect_player_wiki.py   (03_link_wikidata.py 먼저 실행)
#
# 출처   : 한국어 · 영어 위키백과 API — CC BY-SA 4.0 (근거 표시 시 제목 · 원문 링크 필수)
# 입력   : data/raw/wikidata/players_wikidata.csv  (ko_title, en_title)
# 저장   : data/raw/wiki/docs/{player_id}_{언어}_{문서제목}.json   (문서 1개 = 파일 1개)
#          data/raw/wiki/wiki_manifest.json                       (선수별 수집 이력)
#
# 명세서 F2004: "선택한 항목 자체를 다룬 문서는 선별 · 길이 등 어떤 제외 규칙보다 우선하여
#               항상 색인해야 한다." → 선수 본인 문서는 선별 프롬프트 없이 수집한다.
# 프롬프트 1 · 2를 거치는 추가 문서(관련 사건, 팀-시즌 등)는 GMS 키 확보 후 별도로 수집한다.
#
# 문서 JSON 스키마 (제공 영화 팩 위키 문서와 같은 구조, movie_id → player_id)
#   page_id, title, url, text, source, player_id, related_player, search_query, collected_at
#
# 외부 API 예절 (NF2006): User-Agent에 연락처, 요청 사이 대기, 429 · 5xx 재시도
# 이미 받은 문서는 다시 받지 않는다 (manifest 기준, NF2002) → 중간에 멈춰도 이어서 실행 가능

import csv
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from env import contact

HEADERS = {"User-Agent": f"AICoreProject/0.1 ({contact()}) python-urllib"}
SLEEP = 0.4               # 요청 사이 대기 (초)
MAX_RETRY = 4

# 영어 문서 끝부분의 참고 목록 절은 근거로 쓸 내용이 없어 잘라 낸다
CUT_SECTIONS_EN = ["References", "External links", "See also", "Further reading", "Notes", "Sources"]
CUT_SECTIONS_KO = ["각주", "외부 링크", "같이 보기", "참고 문헌", "참조", "주해", "출처"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(BASE_DIR, "..", "data", "raw", "wikidata", "players_wikidata.csv")
WIKI_DIR = os.path.join(BASE_DIR, "..", "data", "raw", "wiki")
DOCS_DIR = os.path.join(WIKI_DIR, "docs")
MANIFEST_PATH = os.path.join(WIKI_DIR, "wiki_manifest.json")


def call_api(lang, params):
    """위키백과 API 호출. 429(요청 과다) · 5xx는 기다렸다가 다시 시도한다."""
    params["format"] = "json"
    params["formatversion"] = 2
    url = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    wait = 2.0
    for attempt in range(1, MAX_RETRY + 1):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
            time.sleep(SLEEP)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                retry_after = e.headers.get("Retry-After")
                pause = float(retry_after) if retry_after else wait
                print(f"  [{e.code}] {pause:.0f}초 후 재시도 ({attempt}/{MAX_RETRY})")
                time.sleep(pause)
                wait *= 2
            else:
                raise
        except urllib.error.URLError:
            print(f"  [네트워크 오류] {wait:.0f}초 후 재시도 ({attempt}/{MAX_RETRY})")
            time.sleep(wait)
            wait *= 2
    raise RuntimeError("재시도 횟수를 넘었습니다: " + url)


def cut_reference_sections(text, section_names):
    """'== References ==' 같은 절이 나오면 그 뒤를 잘라 낸다."""
    lines = text.split("\n")
    result = []
    for line in lines:
        heading = re.match(r"^=+\s*(.+?)\s*=+$", line.strip())
        if heading and heading.group(1) in section_names:
            break
        result.append(line)
    return "\n".join(result).strip()


def fetch_page(lang, title):
    """문서 제목으로 본문(평문) · 문서 ID · 원문 URL을 받는다. 없으면 None."""
    data = call_api(lang, {
        "action": "query",
        "titles": title,
        "prop": "extracts|info",
        "explaintext": 1,          # 태그 없는 평문
        "exsectionformat": "wiki", # 절 제목을 '== 제목 ==' 형태로 남김 (청킹 · 절 자르기에 사용)
        "inprop": "url",
        "redirects": 1,
    })
    page = data["query"]["pages"][0]
    if page.get("missing"):
        return None
    return {"page_id": page["pageid"], "title": page["title"],
            "url": page["fullurl"], "text": page.get("extract", "")}


def safe_file_name(text):
    """파일 이름에 쓸 수 없는 문자를 _ 로 바꾼다."""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text)[:80]


# ---------------- 1. 입력 · manifest 읽기 ----------------
with open(INPUT_PATH, encoding="utf-8") as f:
    players = []
    for row in csv.DictReader(f):
        if row["ko_title"] and row["en_title"]:     # 항목 후보: 한/영 문서 모두 있는 선수
            players.append(row)
print(f"수집 대상 선수: {len(players):,}명 (문서 {len(players) * 2:,}건)")

os.makedirs(DOCS_DIR, exist_ok=True)
manifest = {}
if os.path.exists(MANIFEST_PATH):
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)

# ---------------- 2. 선수별 수집 ----------------
done = 0
skipped = 0
failed = []
for number, player in enumerate(players, start=1):
    player_id = player["key_bbref"]
    entry = manifest.get(player_id, {"keywords": [], "titles": [], "page_ids": [], "files": []})

    for lang, title_key, source, cut in [
        ("ko", "ko_title", "한국어 위키백과", CUT_SECTIONS_KO),
        ("en", "en_title", "영어 위키백과", CUT_SECTIONS_EN),
    ]:
        title = player[title_key]
        keyword = f"{lang}:{title}"
        if keyword in entry["keywords"]:            # 이미 수집한 검색어 → 건너뜀 (NF2002)
            skipped += 1
            continue
        try:
            page = fetch_page(lang, title)
        except Exception as e:
            failed.append((player_id, lang, title, str(e)))
            continue
        if page is None:
            failed.append((player_id, lang, title, "missing"))
            continue

        doc = {
            "page_id": page["page_id"],
            "title": page["title"],
            "url": page["url"],
            "text": cut_reference_sections(page["text"], cut),
            "source": source,
            "player_id": player_id,
            "related_player": player["name_ko"],
            "search_query": title,
            "collected_by": "player_page",          # 선수 본인 문서 (선별 프롬프트 없이 항상 포함)
            "collected_at": time.strftime("%Y-%m-%d"),
        }
        file_name = f"{player_id}_{lang}_{safe_file_name(page['title'])}.json"
        with open(os.path.join(DOCS_DIR, file_name), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)

        entry["keywords"].append(keyword)
        entry["titles"].append(page["title"])
        entry["page_ids"].append(page["page_id"])
        entry["files"].append(file_name)
        entry["collected_at"] = doc["collected_at"]
        done += 1

    manifest[player_id] = entry
    # 50명마다 manifest를 저장하고 진행 상황을 출력 (중간에 멈춰도 이어서 실행 가능)
    if number % 50 == 0 or number == len(players):
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        print(f"  {number:,}/{len(players):,}명 처리 | 새로 수집 {done:,} | 건너뜀 {skipped:,} | 실패 {len(failed)}")

# ---------------- 3. 요약 ----------------
ko_chars = []
en_chars = []
for file_name in os.listdir(DOCS_DIR):
    with open(os.path.join(DOCS_DIR, file_name), encoding="utf-8") as f:
        doc = json.load(f)
    if doc["source"] == "한국어 위키백과":
        ko_chars.append(len(doc["text"]))
    else:
        en_chars.append(len(doc["text"]))
ko_chars.sort()
en_chars.sort()

print()
print("===== 수집 결과 =====")
print(f"한국어 문서: {len(ko_chars):,}건 | 본문 중앙값 {ko_chars[len(ko_chars) // 2] if ko_chars else 0:,}자 | 합계 {sum(ko_chars):,}자")
print(f"영어 문서  : {len(en_chars):,}건 | 본문 중앙값 {en_chars[len(en_chars) // 2] if en_chars else 0:,}자 | 합계 {sum(en_chars):,}자")
print(f"실패: {len(failed)}건")
for item in failed[:20]:
    print("  ", item)

with open(os.path.join(WIKI_DIR, "download_log.json"), "w", encoding="utf-8") as f:
    json.dump({
        "source": "한국어 · 영어 위키백과 API (선수 본인 문서)",
        "license": "CC BY-SA 4.0",
        "collected_at": time.strftime("%Y-%m-%d %H:%M"),
        "ko_docs": len(ko_chars),
        "en_docs": len(en_chars),
        "failed": failed,
    }, f, ensure_ascii=False, indent=2)
