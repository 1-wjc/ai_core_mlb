# 03. Wikidata로 한국어 이름 · 한/영 위키 문서 연결 + 항목 후보 확정
# 실행: python collect/03_link_wikidata.py   (02_download_chadwick.py 먼저 실행)
#
# 출처   : Wikidata Query Service (https://query.wikidata.org/) — CC0
#          한국어 위키백과 API (문서 길이 확인용) — CC BY-SA
# 입력   : data/raw/chadwick/people_mlb.csv  (key_wikidata 열)
# 저장   : data/raw/wikidata/players_wikidata.csv
#
# Chadwick에 이미 Wikidata ID(Q번호)가 있으므로 이름 검색 없이 ID로 정확히 연결한다.
# 가져오는 것: 한국어 라벨, 영어 라벨, 한국어 위키 문서 제목, 영어 위키 문서 제목
# 한국어 문서가 있는 선수는 문서 길이(바이트)도 확인한다.

import csv
import json
import os
import time
import urllib.parse
import urllib.request

from env import contact

SPARQL_URL = "https://query.wikidata.org/sparql"
KO_API_URL = "https://ko.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": f"AICoreProject/0.1 ({contact()}) python-urllib"}
BATCH = 200          # SPARQL 한 번에 조회할 ID 수
MIN_KO_BYTES = 3000  # 한국어 문서 "약 1,000자 이상" 기준 (한글 1자 ≈ 3바이트)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHADWICK_PATH = os.path.join(BASE_DIR, "..", "data", "raw", "chadwick", "people_mlb.csv")
SAVE_DIR = os.path.join(BASE_DIR, "..", "data", "raw", "wikidata")


def get_json(url, params):
    full_url = url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(full_url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def query_wikidata(qids):
    """Q번호 목록에 대해 한/영 라벨과 한/영 위키 문서 제목을 가져온다."""
    values = " ".join("wd:" + q for q in qids)
    query = """
    SELECT ?item ?koLabel ?enLabel ?koTitle ?enTitle WHERE {
      VALUES ?item { %s }
      OPTIONAL { ?item rdfs:label ?koLabel FILTER(LANG(?koLabel) = "ko") }
      OPTIONAL { ?item rdfs:label ?enLabel FILTER(LANG(?enLabel) = "en") }
      OPTIONAL { ?ko schema:about ?item ; schema:isPartOf <https://ko.wikipedia.org/> ; schema:name ?koTitle }
      OPTIONAL { ?en schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?enTitle }
    }
    """ % values
    data = get_json(SPARQL_URL, {"query": query, "format": "json"})
    result = {}
    for b in data["results"]["bindings"]:
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        result[qid] = {
            "name_ko": b.get("koLabel", {}).get("value", ""),
            "name_en": b.get("enLabel", {}).get("value", ""),
            "ko_title": b.get("koTitle", {}).get("value", ""),
            "en_title": b.get("enTitle", {}).get("value", ""),
        }
    return result


def ko_page_lengths(titles):
    """한국어 위키 문서 제목 → 길이(바이트). 50개씩 조회."""
    lengths = {}
    for start in range(0, len(titles), 50):
        batch = titles[start:start + 50]
        data = get_json(KO_API_URL, {
            "action": "query", "titles": "|".join(batch),
            "prop": "info", "format": "json", "formatversion": 2,
        })
        for page in data["query"]["pages"]:
            if not page.get("missing"):
                lengths[page["title"]] = page.get("length", 0)
        time.sleep(0.3)
    return lengths


# ---------------- 1. Chadwick 읽기 ----------------
with open(CHADWICK_PATH, encoding="utf-8") as f:
    people = list(csv.DictReader(f))

qids = []
for row in people:
    if row["key_wikidata"]:
        qids.append(row["key_wikidata"])
print(f"Chadwick 범위 선수 {len(people):,}명 중 Wikidata ID 있음 {len(qids):,}명")

# ---------------- 2. Wikidata 조회 (200개씩) ----------------
wiki_info = {}
for start in range(0, len(qids), BATCH):
    batch = qids[start:start + BATCH]
    wiki_info.update(query_wikidata(batch))
    print(f"  Wikidata 조회 {min(start + BATCH, len(qids)):,}/{len(qids):,}")
    time.sleep(1)

# ---------------- 3. 한국어 문서 길이 ----------------
ko_titles = []
for info in wiki_info.values():
    if info["ko_title"]:
        ko_titles.append(info["ko_title"])
lengths = ko_page_lengths(ko_titles)

# ---------------- 4. 합쳐서 저장 ----------------
os.makedirs(SAVE_DIR, exist_ok=True)
out_path = os.path.join(SAVE_DIR, "players_wikidata.csv")
columns = ["key_bbref", "key_mlbam", "key_wikidata", "name_first", "name_last",
           "mlb_played_first", "mlb_played_last",
           "name_ko", "name_en", "ko_title", "ko_bytes", "en_title"]

rows = []
for row in people:
    info = wiki_info.get(row["key_wikidata"], {})
    ko_title = info.get("ko_title", "")
    rows.append({
        "key_bbref": row["key_bbref"],
        "key_mlbam": row["key_mlbam"],
        "key_wikidata": row["key_wikidata"],
        "name_first": row["name_first"],
        "name_last": row["name_last"],
        "mlb_played_first": row["mlb_played_first"],
        "mlb_played_last": row["mlb_played_last"],
        "name_ko": info.get("name_ko", ""),
        "name_en": info.get("name_en", ""),
        "ko_title": ko_title,
        "ko_bytes": lengths.get(ko_title, 0) if ko_title else 0,
        "en_title": info.get("en_title", ""),
    })

with open(out_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)

# ---------------- 5. 요약 ----------------
has_ko_label = 0
has_ko_doc = 0
has_en_doc = 0
has_both = 0
ko_long = 0
ko_lengths = []
for r in rows:
    if r["name_ko"]:
        has_ko_label += 1
    if r["ko_title"]:
        has_ko_doc += 1
        ko_lengths.append(r["ko_bytes"])
        if r["ko_bytes"] >= MIN_KO_BYTES:
            ko_long += 1
    if r["en_title"]:
        has_en_doc += 1
    if r["ko_title"] and r["en_title"]:
        has_both += 1

ko_lengths.sort()
median = ko_lengths[len(ko_lengths) // 2] if ko_lengths else 0

print()
print("===== 연결 결과 =====")
print(f"범위 선수              : {len(rows):,}명")
print(f"한국어 이름(라벨) 있음 : {has_ko_label:,}명")
print(f"영어 위키 문서 있음    : {has_en_doc:,}명")
print(f"한국어 위키 문서 있음  : {has_ko_doc:,}명  (문서 길이 중앙값 약 {median // 3:,}자)")
print(f"  └ 약 1,000자 이상    : {ko_long:,}명")
print(f"한/영 문서 모두 있음   : {has_both:,}명  ← 항목 후보 (선정 기준 ①②③ 충족)")
print("저장:", os.path.abspath(out_path))

with open(os.path.join(SAVE_DIR, "download_log.json"), "w", encoding="utf-8") as f:
    json.dump({
        "source": "Wikidata Query Service + 한국어 위키백과 API",
        "license": "Wikidata CC0 / Wikipedia CC BY-SA",
        "downloaded_at": time.strftime("%Y-%m-%d %H:%M"),
        "rows": len(rows),
        "ko_doc": has_ko_doc,
        "ko_and_en_doc": has_both,
    }, f, ensure_ascii=False, indent=2)
