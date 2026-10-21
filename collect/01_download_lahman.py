# 01. Lahman Baseball Database (SABR) CSV 내려받기
# 실행: python collect/01_download_lahman.py
#
# 출처   : SABR Lahman Baseball Database 1871-2025 (https://sabr.org/lahman-database/)
# 라이선스: Creative Commons Attribution-ShareAlike 3.0 Unported (readme2025.txt "0.1 Copyright Notice")
# 저장   : data/raw/lahman/
#
# SABR 페이지의 "Comma-delimited version" 링크는 Box 공유 폴더다.
#   1) 공유 폴더 페이지(HTML)에서 파일 이름과 파일 ID를 찾는다 (목록이 2쪽으로 나뉘어 있음)
#   2) 필요한 파일만 Box 공유 다운로드 주소로 내려받는다
# 표준 라이브러리만 사용한다.

import json
import os
import re
import time
import urllib.request

from env import contact

SHARED_NAME = "y1prhc795jk8zvmelfd3jq7tl389y6cd"          # SABR 페이지의 CSV 공유 링크 ID
FOLDER_URL = "https://sabr.box.com/s/" + SHARED_NAME
DOWNLOAD_URL = "https://sabr.box.com/index.php?rm=box_download_shared_file&shared_name={}&file_id={}"
HEADERS = {"User-Agent": f"Mozilla/5.0 (AICoreProject; {contact()})"}

# 이번 프로젝트에 쓰는 파일 (데이터 목록 A1~A7 + 라이선스 확인용 readme)
NEED_FILES = [
    "readme2025.txt",     # 라이선스 · 테이블 설명
    "People.csv",         # A1 선수 기본 정보
    "Batting.csv",        # A2 타격 시즌 기록
    "Pitching.csv",       # A3 투구 시즌 기록
    "Teams.csv",          # A4 팀 시즌 기록 (리그 합계, 파크 팩터)
    "AwardsPlayers.csv",  # A5 수상
    "Appearances.csv",    # A6 포지션별 출장
    "AllstarFull.csv",    # A7 올스타 (선택)
    "HallOfFame.csv",     # A7 명예의 전당 (선택)
    # 포스트시즌 (정규시즌 테이블과 분리된 별도 테이블)
    "SeriesPost.csv",     # A10 시리즈 결과 (연도 · 라운드 · 승리/패배 팀 · 승패 수)
    "BattingPost.csv",    # A11 선수 포스트시즌 타격 (시즌 × 라운드)
    "PitchingPost.csv",   # A11 선수 포스트시즌 투구 (시즌 × 라운드)
    "FieldingPost.csv",   # A11 선수 포스트시즌 수비 (선택)
    # 수비
    "Fielding.csv",       # A12 정규시즌 수비 (수비율 · 레인지 팩터)
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_DIR = os.path.join(BASE_DIR, "..", "data", "raw", "lahman")


def fetch(url):
    """주소의 내용을 bytes로 받아 온다."""
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def find_file_ids():
    """공유 폴더 페이지(1쪽, 2쪽)에서 {파일 이름: 파일 ID}를 찾는다."""
    file_ids = {}
    for page in [1, 2]:
        url = FOLDER_URL + "?page=" + str(page)
        html = fetch(url).decode("utf-8", errors="replace")
        # 페이지 안의 JSON 조각: "typedID":"f_123..." ... "name":"People.csv"
        pairs = re.findall(r'"typedID":"(f_\d+)".{0,400}?"name":"([^"]+)"', html, re.S)
        for typed_id, name in pairs:
            if name.endswith(".csv") or name.endswith(".txt"):
                if name not in file_ids:
                    file_ids[name] = typed_id
        time.sleep(1)
    return file_ids


# ---------------- 1. 파일 ID 찾기 ----------------
os.makedirs(SAVE_DIR, exist_ok=True)
file_ids = find_file_ids()
print("공유 폴더에서 찾은 파일 수:", len(file_ids))

missing = []
for name in NEED_FILES:
    if name not in file_ids:
        missing.append(name)
if missing:
    print("찾지 못한 파일:", missing)

# ---------------- 2. 필요한 파일만 내려받기 ----------------
print()
print("파일 | 크기 | 행 수 | 첫 줄(열 이름)")
for name in NEED_FILES:
    if name not in file_ids:
        continue
    path = os.path.join(SAVE_DIR, name)
    if os.path.exists(path):                       # 이미 받은 파일은 다시 받지 않는다
        with open(path, "rb") as f:
            data = f.read()
    else:
        data = fetch(DOWNLOAD_URL.format(SHARED_NAME, file_ids[name]))
        with open(path, "wb") as f:
            f.write(data)

    # 파일 앞의 BOM(﻿)을 떼고 첫 줄과 줄 수를 확인한다
    text = data.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    first_line = lines[0][:90] if lines else ""
    print(f"{name} | {len(data):,} bytes | {len(lines):,} | {first_line}")
    time.sleep(1)

# ---------------- 3. 라이선스 문구 확인 ----------------
readme_path = os.path.join(SAVE_DIR, "readme2025.txt")
if os.path.exists(readme_path):
    with open(readme_path, encoding="utf-8-sig", errors="replace") as f:
        readme = f.read()
    print()
    print("===== 라이선스 (readme2025.txt) =====")
    for line in readme.splitlines():
        if "copyright" in line.lower() or "licensed" in line.lower() or "creativecommons" in line.lower():
            print(line.strip())

# 내려받은 기록을 남긴다
with open(os.path.join(SAVE_DIR, "download_log.json"), "w", encoding="utf-8") as f:
    json.dump({
        "source": "SABR Lahman Baseball Database 1871-2025",
        "url": "https://sabr.org/lahman-database/",
        "license": "CC BY-SA 3.0 Unported",
        "downloaded_at": time.strftime("%Y-%m-%d %H:%M"),
        "files": [n for n in NEED_FILES if n in file_ids],
    }, f, ensure_ascii=False, indent=2)
print()
print("저장 위치:", os.path.abspath(SAVE_DIR))
