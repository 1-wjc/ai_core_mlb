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

*(구현 후 작성)*

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash
pip install -r requirements.txt
```

`.env`에 다음 값을 넣습니다. `.env`는 저장소에 올리지 않습니다.
```
GMS_KEY=발급받은_키
WIKI_CONTACT=your-email@example.com
```

## 3. 기능

### 필수 기능 (F2001 ~ F2012)
*(구현 후 작성)*

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
| 8 | *(예정)* | 색인 (메타데이터 컬렉션 · 외부 문서 컬렉션) | |

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

| 출처 | 사용 내용 | 라이선스 · 이용 조건 |
|---|---|---|
| [SABR Lahman Baseball Database 1871-2025](https://sabr.org/lahman-database/) | 선수 · 시즌 · 팀 기록 | **CC BY-SA 3.0 Unported**. Copyright 1996-2025 SABR, via donation from Sean Lahman. 니그로 리그 데이터(별도 라이선스)는 사용하지 않음 (AL · NL만 사용) |
| [Chadwick Baseball Bureau Register](https://github.com/chadwickbureau/register) | 선수 ID 매핑 | **Open Data Commons Attribution License (ODC-By 1.0)** |
| [Wikidata](https://www.wikidata.org/) | 한국어 이름, 위키 문서 연결 | **CC0** |
| [한국어 위키백과](https://ko.wikipedia.org/) · [영어 위키백과](https://en.wikipedia.org/) | 선수 · 시즌 서술 문서 (근거) | **CC BY-SA 4.0**. 근거마다 문서 제목과 원문 링크 표시 |

- 이 저장소에서 위 데이터를 가공한 결과물(선수 데이터, 시즌 기록 문서, 수집 문서)은 원 라이선스에 따라 **CC BY-SA**를 따릅니다.
- 위키백과 API는 User-Agent에 연락처를 넣고, 호출 간격과 재시도 규칙을 지킵니다.

## 6. 심화 기능 적용 요약

*(선택 후 작성)*
