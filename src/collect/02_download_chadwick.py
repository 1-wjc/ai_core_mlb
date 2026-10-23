# 02. Chadwick Register 내려받기 + 우리 범위 선수만 남기기
# 실행: python collect/02_download_chadwick.py   (01_download_lahman.py 먼저 실행)
#
# 출처   : Chadwick Baseball Bureau Register (https://github.com/chadwickbureau/register)
# 라이선스: Open Data Commons Attribution License (ODC-By 1.0) — README.md "License"
# 저장   : data/raw/chadwick/
#
# Register는 야구 관계자 약 50만 명의 ID 매핑표다 (people-0.csv ~ people-f.csv, 16개).
# 각 ID 체계를 잇는 열쇠로 쓴다.
#   Lahman People.csv 의 bbrefID  ==  Chadwick 의 key_bbref
#   Chadwick 의 key_wikidata       →  다음 단계(Wikidata)에서 한국어 이름 · 위키 문서 연결
#
# 범위: 1901~2025 시즌에 AL · NL(메이저리그)에서 타격 또는 투구 기록이 있는 선수 (1901 = 아메리칸리그 창설, 현대 야구 기준)
#       (니그로 리그 등 다른 리그 코드는 별도 라이선스 문제로 제외)

import csv
import io
import json
import os
import time
import urllib.request

from env import contact, data_dir

RAW_URL = "https://raw.githubusercontent.com/chadwickbureau/register/master/data/people-{}.csv"
HEADERS = {"User-Agent": f"AICoreProject/0.1 ({contact()})"}
FILE_KEYS = "0123456789abcdef"           # people-0.csv ~ people-f.csv

FIRST_SEASON = 1901
LAST_SEASON = 2025
LEAGUES = ["AL", "NL"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = data_dir()                              # 프로젝트 루트의 data/ (collect/env.py)
LAHMAN_DIR = os.path.join(DATA_DIR, "raw", "lahman")
SAVE_DIR = os.path.join(DATA_DIR, "raw", "chadwick")


def read_csv(path):
    """CSV를 dict 목록으로 읽는다 (파일 앞 BOM 제거)."""
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ---------------- 1. Lahman에서 우리 범위 선수 고르기 ----------------
target_lahman_ids = set()
for file_name in ["Batting.csv", "Pitching.csv"]:
    for row in read_csv(os.path.join(LAHMAN_DIR, file_name)):
        year = int(row["yearID"])
        if row["lgID"] in LEAGUES and FIRST_SEASON <= year <= LAST_SEASON:
            target_lahman_ids.add(row["playerID"])

# Lahman playerID → bbrefID
lahman_to_bbref = {}
for row in read_csv(os.path.join(LAHMAN_DIR, "People.csv")):
    if row["playerID"] in target_lahman_ids and row["bbrefID"]:
        lahman_to_bbref[row["playerID"]] = row["bbrefID"]

target_bbref_ids = set(lahman_to_bbref.values())
print(f"Lahman 범위 선수: {len(target_lahman_ids):,}명 (bbrefID 있음 {len(target_bbref_ids):,}명)")

# ---------------- 2. Chadwick 16개 파일을 받아 범위 선수만 남기기 ----------------
os.makedirs(SAVE_DIR, exist_ok=True)
kept_rows = []
header = None
total_rows = 0

for key in FILE_KEYS:
    url = RAW_URL.format(key)
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=120) as response:
        text = response.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames
    count = 0
    for row in reader:
        total_rows += 1
        if row["key_bbref"] in target_bbref_ids:
            kept_rows.append(row)
            count += 1
    print(f"people-{key}.csv: 남긴 행 {count}")
    time.sleep(0.5)

# ---------------- 3. 저장 ----------------
out_path = os.path.join(SAVE_DIR, "people_mlb.csv")
with open(out_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=header)
    writer.writeheader()
    writer.writerows(kept_rows)

with_wikidata = 0
with_mlbam = 0
for row in kept_rows:
    if row["key_wikidata"]:
        with_wikidata += 1
    if row["key_mlbam"]:
        with_mlbam += 1

print()
print(f"Chadwick 전체 행: {total_rows:,}")
print(f"범위 선수와 일치: {len(kept_rows):,}명 / Lahman 범위 {len(target_bbref_ids):,}명")
print(f"  - key_wikidata 있음: {with_wikidata:,}명")
print(f"  - key_mlbam 있음  : {with_mlbam:,}명")
print("저장:", os.path.abspath(out_path))

with open(os.path.join(SAVE_DIR, "download_log.json"), "w", encoding="utf-8") as f:
    json.dump({
        "source": "Chadwick Baseball Bureau Register",
        "url": "https://github.com/chadwickbureau/register",
        "license": "Open Data Commons Attribution License (ODC-By 1.0)",
        "downloaded_at": time.strftime("%Y-%m-%d %H:%M"),
        "filter": f"Lahman {FIRST_SEASON}-{LAST_SEASON} {'/'.join(LEAGUES)} 출장 선수 (bbrefID 일치)",
        "rows": len(kept_rows),
    }, f, ensure_ascii=False, indent=2)
