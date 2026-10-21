# MLB 세이버메트릭스 RAG — 근거를 대고 답하는 야구 기록 서비스

> AI 코어 프로젝트 2회차 · RAG 기반 도메인 지식 서비스
> *작성 중인 문서입니다. 진행에 맞춰 계속 갱신합니다.* (최종 갱신: 2026-10-21)

---

## 1. 프로젝트 개요

MLB 선수의 시즌 기록과 세이버메트릭스 지표, 위키백과 서술 문서를 근거로 질문에 답하고, 답변에 사용한 근거를 함께 보여 주는 서비스입니다.

- **항목**: 한국어 · 영어 위키백과 문서가 모두 있는 MLB 선수 (1990~2025 시즌 AL · NL 출장)
- **근거**: 기록 데이터(Lahman, 직접 계산한 지표) + 위키백과 문서(한국어 · 영어) + 지표 사전
- **원칙**: 근거에 없는 내용은 "확인되지 않는다"고 답하고, 수치는 코드로 계산한 값만 인용
- **서비스 범위**: 2025 시즌까지

## 2. 실행 방법

Python 3.11 기준 (명세서 지정 버전 + Django).

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env                 # 값 채우기
```

`.env` (저장소에 올리지 않음)
```
GMS_KEY=발급받은_키
WIKI_CONTACT=your-email@example.com
# 선택: CHAT_MODEL · EMBED_MODEL · CHUNK_SIZE · CHUNK_OVERLAP · TOP_K · PER_QUERY_K
```

색인과 질문 (4장의 데이터 준비를 먼저 실행)
```bash
python -m rag.indexer --players ryuhy01,troutmi01    # 일부 선수만
python -m rag.indexer --all                          # 전체
python -m scripts.ask ryuhy01 "2019년 평균자책점과 FIP 차이는?"
python -m scripts.ask --graph                        # 그래프 구조 (retrieve → generate)
```

| 설정 | 기본값 |
|---|---|
| 채팅 모델 | `gpt-5.4-mini` (GMS, OpenAI 호환 주소) |
| 임베딩 모델 | `text-embedding-3-large` (3072차원) |
| 청크 크기 / 겹침 | 1000 / 200 (위키 문서만 청킹, 기록 문서는 1문서 = 1청크) |
| Top-k | 외부 청크 6개 (검색어당 후보 6개) + 선수 메타데이터 1개 항상 포함 |

## 3. 기능

### 필수 기능 (F2001 ~ F2012)

| 기능 | 상태 | 구현 |
|---|---|---|
| F2001 · F2002 메타데이터 색인 | ✅ | `rag/indexer.py` — `player_meta`, 선수 1명 = 청크 1개, ID = `player_id`, upsert라 재색인해도 건수 불변 |
| F2003 검색어 추출 (프롬프트 1) | ✅ | `rag/prompts.py` — JSON 배열, 영어 검색어 우선 |
| F2004 후보 선별 · 보충 수집 (프롬프트 2) | 🔲 | 프롬프트만 작성, 질문 시 보충 수집은 예정 |
| F2005 외부 문서 색인 | ✅ | `player_docs`, ID = `player_id:문서ID:순번`, `player_id` 필터. 팀 시즌 문서는 그 시즌 소속 선수 범위마다 복사 |
| F2006 · F2007 retrieve → generate | ✅ | `rag/graph.py` — 메타데이터 항상 포함 + 선수 범위 유사도 검색, 병합 · 중복 제거, 근거 없으면 "확인되지 않는다" |
| F2008 인용 근거 표시 (프롬프트 3) | ✅ | 답변의 [근거 N]만 골라 제목 · URL 표시, 인용 0개 안내 |
| F2009 ~ F2012 | 🔲 | 예정 (Django 화면) |

### 심화 기능 (F2013 ~ F2016)
*(선택 후 작성)*

## 4. 데이터 준비 및 색인 절차

| 순서 | 스크립트 | 내용 | 결과 |
|---|---|---|---|
| 1 | `collect/01_download_lahman.py` | Lahman CSV 14개 다운로드 (선수 · 타격 · 투구 · 수비 · 팀 · 수상 · 출장 · 올스타 · 명예의 전당 · 포스트시즌 시리즈 결과 · 포스트시즌 타격/투구/수비) | `data/raw/lahman/` |
| 2 | `collect/02_download_chadwick.py` | Chadwick Register에서 범위 선수 ID 매핑만 추출 | `data/raw/chadwick/people_mlb_1990_2025.csv` |
| 3 | `collect/03_link_wikidata.py` | Wikidata로 한국어 이름 · 한/영 위키 문서 연결, 한국어 문서 길이 확인 | `data/raw/wikidata/players_wikidata.csv` |
| 4 | `collect/04_collect_player_wiki.py` | 선수 본인 한/영 위키 문서 수집 (문서 JSON + manifest, 재수집 방지) | `data/raw/wiki/` |
| 5 | `build/01_build_players.py` | 선수 1명 = 항목 1건으로 정규화 (프로필 · 통산 · 최고 시즌 · 수상 · 포스트시즌 · 특징 · 색인 텍스트) | `data/processed/players.json` |
| 6 | `build/02_build_record_docs.py` | 기록 문서: 선수×시즌(정규 · 포스트) · 팀×시즌 1행 = 문서 1개, 지표는 `build/metrics.py`로 로컬 계산 | `data/processed/record_docs.json` |
| 7 | *(예정)* | 지표 사전 (직접 작성) | `build/metrics.json` |
| 8 | `rag/indexer.py` | 색인: `player_meta` (선수 1,466) · `player_docs` (기록 문서 + 위키 청크) | `chroma_db/` |

`data/` 폴더는 저장소에 포함하지 않습니다. 위 순서대로 스크립트를 실행하면 다시 만들어집니다. `build/` 스크립트는 `build/` 폴더 안의 공용 모듈(`lahman_loader.py`, `seasons.py`, `metrics.py`, `names_ko.py`)을 사용합니다.

현재 데이터 규모

| 항목 | 값 |
|---|---|
| 범위 선수 (1990~2025, AL · NL) | 8,813명 |
| Wikidata 연결 | 7,691명 |
| **항목 (한국어 · 영어 위키 문서 모두 있음)** | **1,466명** (투수 724 · 타자 742) |
| 위키 문서 (선수 본인 문서, 참고문헌 절 제외) | 2,932건 (한국어 1,466 · 본문 중앙값 391자 / 영어 1,466 · 중앙값 7,228자) |
| 기록 문서 | 15,946건 (선수 정규시즌 11,788 · 선수 포스트시즌 3,100 · 팀 시즌 1,058) |

## 5. 사용한 데이터 · 문서의 출처와 이용 조건

### 5.1 원천 출처

| 출처 | 사용 내용 | 라이선스 · 이용 조건 |
|---|---|---|
| [SABR Lahman Baseball Database 1871-2025](https://sabr.org/lahman-database/) | 선수 · 시즌 · 팀 · 수상 · 포스트시즌 기록 | **[CC BY-SA 3.0 Unported](https://creativecommons.org/licenses/by-sa/3.0/)**. Copyright 1996-2025 SABR, via donation from Sean Lahman (readme2025.txt "0.1 Copyright Notice" 확인). 별도 라이선스(Seamheads)인 니그로 리그 데이터는 사용하지 않음 (AL · NL만) |
| [Chadwick Baseball Bureau Register](https://github.com/chadwickbureau/register) | 선수 ID 매핑 (bbref · MLBAM · Wikidata) | **[ODC-By 1.0](https://opendatacommons.org/licenses/by/1-0/)** (출처 표시) |
| [Wikidata](https://www.wikidata.org/) | 한국어 이름, 한/영 위키 문서 연결 | **[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)** (표시 의무 없음, 출처는 기록) |
| [한국어 위키백과](https://ko.wikipedia.org/) · [영어 위키백과](https://en.wikipedia.org/) | 선수 본인 문서 본문 (근거) | **[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)**. 문서마다 제목 · 원문 URL 보관, 답변 근거에 표시 |

### 5.2 수집 · 가공한 데이터의 라이선스

| 데이터 | 만든 스크립트 | 바탕 출처 | 따르는 라이선스 | 원본에서 바꾼 점 |
|---|---|---|---|---|
| `data/raw/lahman/*.csv` | `collect/01` | Lahman | CC BY-SA 3.0 | 없음 (원본 그대로) |
| `data/raw/chadwick/people_mlb_1990_2025.csv` | `collect/02` | Chadwick | ODC-By 1.0 | 범위 선수 8,813명 행 · 열만 추출 |
| `data/raw/wikidata/players_wikidata.csv` | `collect/03` | Wikidata (+ Chadwick ID) | CC0 (Chadwick ID 열은 ODC-By) | 이름 · 문서 제목 · 문서 길이만 조회 |
| `data/raw/wiki/docs/*.json` (2,932건) | `collect/04` | 한/영 위키백과 | **CC BY-SA 4.0** | 일반 텍스트로 추출, 각주 · 외부 링크 · 참고 문헌 절 제거 |
| `data/processed/players.json` | `build/01` | Lahman · Chadwick · Wikidata | **CC BY-SA 3.0** | 1990~2025 AL · NL 합산, 지표 계산, 한국어 표기, 규칙 기반 요약 문장 |
| `data/processed/record_docs.json` | `build/02` | Lahman | **CC BY-SA 3.0** | 선수 · 팀 시즌별 문서화, 세이버메트릭스 지표 계산 |
| `chroma_db/` (색인) | `rag/indexer.py` | 위 전체 | 각 청크의 원 출처 라이선스 | 청킹 · 임베딩 |

- **동일 조건 변경 허락(SA)**: Lahman · 위키백과를 가공한 데이터는 공유할 때 같은 CC BY-SA 라이선스로 공유해야 합니다.
- **출처 표시**: 화면 하단과 답변 근거에 출처(Lahman · 위키백과 문서 제목과 URL)와 라이선스를 표시합니다.
- **저장소 배포 범위**: `data/`와 `chroma_db/`는 저장소에 포함하지 않습니다. 저장소에는 데이터를 받고 가공하는 코드만 있고, 데이터는 각 출처에서 직접 받아 만듭니다.
- **이용 예절 (NF2006)**: 위키백과 · Wikidata API 호출 시 User-Agent에 연락처(`.env`의 `WIKI_CONTACT`)를 넣고, 요청 사이에 대기합니다 (Wikidata 0.3~1초, 위키백과 0.4초). 위키백과 수집은 429 · 5xx 응답 시 Retry-After를 따라 최대 4회 재시도합니다. 한 번 수집한 문서는 manifest로 관리해 다시 받지 않습니다 (NF2002).
- **사용하지 않은 출처**: KBO 공식 사이트 · 스탯티즈(자동 수집 금지), Baseball-Reference · FanGraphs · Baseball Savant(대량 수집 · 재배포 제한).

## 6. 심화 기능 적용 요약

*(선택 후 작성)*
