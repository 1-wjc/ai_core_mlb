# MLB 세이버메트릭스 RAG — 근거를 대고 답하는 야구 기록 서비스

> AI 코어 프로젝트 2회차 · RAG 기반 도메인 지식 서비스
> *작성 중인 문서입니다. 진행에 맞춰 계속 갱신합니다.* (최종 갱신: 2026-10-22)

---

## 1. 프로젝트 개요

MLB 선수의 시즌 기록과 세이버메트릭스 지표, 위키백과 서술 문서를 근거로 질문에 답하고, 답변에 사용한 근거를 함께 보여 주는 서비스입니다.

- **항목**: 한국어 · 영어 위키백과 문서가 모두 있는 MLB 선수 (1901~2025 시즌 AL · NL 출장, 2,047명)
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
# 선택: CHAT_MODEL · EMBED_MODEL · CHUNK_SIZE · CHUNK_OVERLAP · TOP_K_RECORD · TOP_K_WIKI · PER_QUERY_K
#       COLLECT_MODE(auto|always|off) · COLLECT_IF_DISTANCE · HISTORY_TURNS · EXPLORE_CANDIDATES (rag/config.py)
# 선택: DJANGO_DEBUG=1 (개발 중에만. 기본은 꺼짐 → 오류 추적 정보를 화면에 보이지 않음)
```

색인과 질문 (4장의 데이터 준비를 먼저 실행)
```bash
python -m rag.indexer --players ryuhy01,troutmi01    # 일부 선수만
python -m rag.indexer --all                          # 전체
python -m scripts.ask ryuhy01 "2019년 평균자책점과 FIP 차이는?"
python -m scripts.ask --graph                        # 그래프 구조 (retrieve → generate)
python -m scripts.ask ryuhy01 "2019 시즌 투구 비교" --compare kershcl01
python -m scripts.ask kershcl01 "포스트시즌 부진" --search-compare   # 유사도 vs MMR 근거 비교
```

화면 (Django). GMS 키와 색인이 있으면 RAG 모드, 없으면 기록 검색 모드(질문의 연도 · 키워드로 기록 문서를 찾아 보여 줌, LLM 미사용)로 동작
```bash
python web/manage.py runserver      # http://127.0.0.1:8000
```

| 화면 | 주소 | 내용 |
|---|---|---|
| 메인 | `/` | 선수 검색(자동 완성) · 질문 예시(누르면 그 선수 페이지에서 바로 질문) · 시즌 타임라인(1901~2025 연도별 월드시리즈 우승 · MVP · 사이영상 · 부문 1위, MLB 전체 선수 기준) · 전체 선수 목록(투수/타자 · 이름순/최근순 · 구단별) |
| 선수 | `/players/<id>/` | 프로필 · 통산 기록 [기본 · 세이버 · 상세] · 커리어 그래프 · 시즌별 기록 [정규 · 포스트] × [기본 · 세이버 · 상세 · 수비] · 비슷한 선수 · 질문 패널 [질문 · 사실 확인] (스트리밍 · 근거 원문 미리보기 · 대화 저장) |
| 비교 | `/compare/?a=&b=` | 두 선수 통산 지표 비교 · 비교 질문 (F2010) |
| 조건 탐색 | `/explore/` | 자연어 조건 → 조건에 맞는 선수 카드 (F2011) |
| RAG 실험실 | `/lab/` | 청크 크기 · Top-k · 유사도/MMR · λ를 두 설정으로 나란히 실행해 근거 · 답변 비교 (F2014 확인용) |

화면 코드: `web/chat/pages.py`(페이지) · `web/chat/views.py`(JSON API) · `web/chat/templates/chat/` · `web/chat/static/chat/`

| API | 요청 | 응답 |
|---|---|---|
| `GET /api/status` | | `{mode, notice, key_ready, players, record_docs, index_meta, index_docs}` |
| `GET /api/players` | | `{players: [{player_id, name_ko, name_en, role, position, first_season, last_season}]}` |
| `POST /api/ask` | `{player_id, question, compare_id?, history?, mode?}` (`mode`: `ask` · `factcheck`) | `{answer, verdict?, sources: [{n, title, url, source, text?}], cited: [n], steps, collected, mode, elapsed}` (`text`는 인용한 근거만) |
| `POST /api/ask_stream` | `/api/ask`와 같음 | NDJSON 한 줄씩: `{type: evidence}` → `{type: token}` … → `{type: final}` (오류 시 `{type: error}`) |
| `POST /api/explore` | `{condition}` | `{cards: [{player_id, name_ko, name_en, role, position, first_season, last_season, reason}], candidates, elapsed}` |
| `POST /api/lab` | `{player_id, question, configs: [설정 A, 설정 B]}` | 설정별 근거 · 답변 · 소요 시간 |

| 설정 | 기본값 |
|---|---|
| 채팅 모델 | `gpt-5.4-mini` (GMS, OpenAI 호환 주소) |
| 임베딩 모델 | `text-embedding-3-large` (3072차원) |
| 청크 크기 / 겹침 | 1000 / 200 (위키 문서만 청킹, 기록 문서는 1문서 = 1청크) |
| Top-k | 기록 3 · 위키 4 (검색어당 후보 6개) + 선수 메타데이터 1개 항상 포함 + 질문에 나온 지표 사전 최대 3 |
| 위키 검색 | MMR (후보 30개 → λ 0.7로 4개) |
| 질문 시 보충 수집 | 가장 가까운 위키 근거 거리 > 0.33일 때만 (`COLLECT_MODE=auto`) |

## 3. 기능 — 요구사항별 구현 현황

표기: ✅ 충족 · 🟡 일부 충족 · 🔲 예정 · ➖ 해당 없음. 비고에는 명세서 세부 조건 중 아직 남은 부분을 적습니다.

### 3.1 필수 기능 (F2001 ~ F2012)

| 번호 | 요구사항 | 상태 | 구현 | 비고 |
|---|---|---|---|---|
| F2001 | 항목 메타데이터 로드 · 항목 1건 = 텍스트 1개 · 약 100건 이상 | ✅ | `build/01_build_players.py` → `players.json` 2,047명 (1901~2025). `index_text`에 이름 · 투타 · 포지션 · 출신 · 소속 · 통산 기록 · 최고 시즌 · 수상 · 포스트시즌 · 특징을 한 텍스트로 구성 | |
| F2002 | 임베딩 · Vector DB 색인 · 청크 수 확인 · 재색인 시 중복 없음 | ✅ | `rag/indexer.py` → `player_meta` 컬렉션, 청크 ID = `player_id`, upsert. 색인 건수는 화면(질문 패널 상단)과 CLI에 표시 | 재색인 2회 실행 시 새로 쓰기 0 · 건수 불변 확인 (5명 기준) |
| F2003 | 프롬프트 1(전문가 역할)로 검색어 추출 · 파싱 가능한 형식 · 항목 자체 문서는 항상 검색 대상 | ✅ | `rag/prompts.py` KEYWORD — "MLB 기록 분석가" 역할, JSON 배열 출력, 직전 대화로 "그 해" 같은 표현을 풀어 씀. 추출한 검색어는 색인 검색과 질문 시 위키 검색(F2004)에 사용. 선수 본인 한/영 위키 문서는 전원 사전 수집 · 색인 | |
| F2004 | 후보 수집 → 프롬프트 2로 선별 · 항목 자체 문서 항상 색인 · 본문과 URL 수집 · 수집한 검색어 재수집 안 함 | ✅ | 사전 배치: `collect/04` — 선수 본인 문서 4,105건(선별 없이 항상 색인). 질문 시 보충: `rag/collector.py` — 기존 위키 근거가 부족하면(가장 가까운 거리 > 0.33) 영어 검색어 2개로 위키 검색 → 프롬프트 2가 제목 · 요약만 보고 선별 → 본문 · URL 수집 → 문서 JSON 저장 → 청킹 · 색인 → 다시 검색. 검색어 · 수집 문서 · 버린 후보를 manifest에 기록 | 확인: 지터 "1998 양키스 팀 시즌 승수" → 후보 12개 중 "1998 New York Yankees season" 선별 · 수집 → 답변에 인용. 기준 거리는 실측(본인 문서에 있는 질문 0.23~0.32, 없는 질문 0.335~0.38). 수집하는 질문은 약 25~40초 |
| F2005 | 청크 크기 · 중복 적용 · 별도 컬렉션 · 제목 · 출처 · 관련 항목 저장 · 덮어쓰지 않는 ID · 설정으로 조정 | ✅ | `player_docs` 컬렉션. 위키는 1000자/200자 분할, ID = `player_id:문서ID:순번`, 메타데이터에 title · url · related_player · source. `CHUNK_SIZE` · `CHUNK_OVERLAP`은 `.env`로 조정. 팀 시즌 문서는 소속 선수 범위마다 따로 저장(ID에 선수 포함 → 서로 덮어쓰지 않음) | 기록 문서는 1문서 = 1청크(시즌 1행이 잘리지 않게) |
| F2006 | 메타데이터 청크 항상 포함 · 외부 청크 유사도 검색 · 병합 · 중복 제거 · Top-k 설정 | ✅ | `rag/graph.py` retrieve — 메타데이터는 ID로 직접 가져와 항상 근거 1번. 외부 문서는 `player_id` 필터 안에서 검색어별 검색 후 병합 · 중복 제거. 기록 · 위키를 나눠 `TOP_K_RECORD`(3) · `TOP_K_WIKI`(4), 질문에 연도가 있으면 기록은 그 시즌만 | |
| F2007 | LangGraph retrieve · generate 2노드 · 문서 내용만 사용 · 출처 유형 구분 · 근거 없으면 "확인되지 않는다" | ✅ | `build_graph()` — START → retrieve → generate → END (`python -m scripts.ask --graph`). 근거마다 출처 유형(메타데이터 / 기록 데이터(Lahman) / 영어 · 한국어 위키백과) 표시 | 근거에 없는 질문("좋아하는 음식") → "확인되지 않는다", 인용 0개 확인 |
| F2008 | 주요 주장에 근거 번호 · 실제 인용 근거만 표시 · 제목과 출처 · 인용 0개 안내 | ✅ | 프롬프트 3 규칙 + 답변에서 `[근거 N]` 추출 → 화면 "답변에 사용한 근거 N건"에 제목 · 출처 유형 · 원문 링크. 인용이 없으면 "답변에 인용된 근거가 없습니다" | |
| F2009 | 목록에서 항목 선택 · 항목별 대화 기록 유지 | ✅ | 선수(비교 시 선수 조합)별 대화를 브라우저(localStorage)에 저장해 새로고침 · 페이지 이동 후에도 유지. 직전 대화(최대 6개 메시지)를 서버로 보내 프롬프트 1 · 3에 넣음 | 확인: 지터 "1996년 신인왕 시즌 타율은?" → "그 다음 해 홈런 수는?" 을 1997년으로 풀어 10개라고 답함 |
| F2010 | 도메인 특화 기능 1개 이상 · 근거 제시 | ✅ | **① 두 선수 비교** — "비교할 선수"를 고르면 두 선수 범위를 각각 검색(메타데이터 · 기록 · 위키)하고, 비교 규칙을 붙인 프롬프트 3으로 항목별 "A 값 [근거] / B 값 [근거]" 형식으로 답함. 한쪽 근거가 없으면 "확인되지 않음". **② 사실 확인** — 질문 패널을 [사실 확인]으로 바꾸면 주장을 근거와 대조해 첫 줄에 "판정: 참 / 거짓 / 일부 사실 / 근거 부족"을 내고 화면에 판정 배지를 표시. **③ 구단 시절 합산** — 질문에 구단명이 나오면(`rag/team_era.py`) 그 구단에서만 뛴 시즌을 합산해 근거로 넣고, 시즌 중 이적한 해는 따로 표시 | 전체 색인 후 API로 확인: 류현진 vs 커쇼 "2019 시즌 투구 비교" → 승 · ERA · WHIP · 탈삼진 · 이닝 · FIP를 항목별로 양쪽 근거와 함께 비교, 포스트시즌까지 구분 (8.5초). 사실 확인 주장 5개 판정 모두 정답. 푸홀스 "카디널스 시절 홈런" → 구단 합산 근거로 답함 |
| F2011 | 자연어 조건 입력 · 조건에 맞는 항목만 제시 · 선택 시 대화로 이어짐 | ✅ | `rag/explore.py` — 숫자 조건("홈런 400개 이상")은 규칙으로 읽어 메타데이터 필터, 투타 · 출신 국가 · 수상은 색인 텍스트 포함 필터로 후보를 거른 뒤 의미 유사도로 최대 40명 → 프롬프트 2(조건 선별)가 조건 충족을 판정한 선수만 카드로. 카드를 누르면 그 선수 페이지(질문 패널)로 이동 | 확인: "홈런 400개 이상 좌타자" 9명, "사이영상 좌투수" 12명, "세이브 300개 이상" 12명, 존재하지 않는 조건(일본 출신 사이영상)은 0명. 약 3~25초 |
| F2012 | 진행 상태 표시 · 색인 없음/키 누락 안내 · 위험 도메인 면책 | ✅ | 처리 중 표시, 완료 후 검색어 · 문서 수집 결과(새 검색어 수 · 후보 수 · 선별 문서 제목) · 출처별 근거 수 · 소요 시간. 키가 없거나 색인이 0건이면 안내 후 기록 검색 모드(LLM 미사용)로 대신 답함. 색인 건수는 질문 패널 상단에 항상 표시 | 답변은 스트리밍으로 근거 목록부터 표시. 면책: 야구 기록은 위험 도메인이 아니라 해당 없음 |

### 3.2 심화 기능 (F2013 ~ F2016)

| 번호 | 요구사항 | 상태 | 구현 | 비고 |
|---|---|---|---|---|
| F2013 | HTML · CSS · JS 화면 · 화면과 서버 분리 · 요청/응답 형식 정의 · 질문 · 답변 · 근거 표시 | ✅ | Django가 화면(`web/chat/templates`, `static`)과 JSON API(`/api/status` · `players` · `ask` · `ask_stream` · `explore` · `lab`)를 따로 제공. 형식은 2장 표와 `web/chat/views.py` 머리 주석 | Streamlit 대신 Django 사용 |
| F2014 | MMR로 근거 다양성 확보 · 유사도 검색과 차이 확인 | ✅ | `rag/graph.py` `search_mmr` — 위키 청크 후보 30개를 가져와 λ=0.7로 4개 선택(`SEARCH_MODE` · `MMR_FETCH_K` · `MMR_LAMBDA` 설정). `python -m scripts.ask <선수> "<질문>" --search-compare` 로 두 방식의 근거와 근거끼리 평균 유사도를 나란히 출력. 화면에서는 `/lab/`에서 두 설정을 나란히 실행 | 실측: 커쇼 "포스트시즌 부진과 우승" 평균 유사도 0.771 → 0.751, 2017 · 와일드카드 절이 새로 들어옴. λ 0.5는 무관한 절(류현진 부상 질문에 "미디어 출연")까지 섞여 0.7 채택 |
| F2015 | RAG 사용 전후 답변 비교 문서 | ✅ | [`docs/rag_comparison.md`](docs/rag_comparison.md) — 질문 12개, 정확성: RAG 없이 ✅7 · 🟡2 · ❌3 / RAG ✅11 · ⭕1, 근거 제시 0/12 vs 11/11 | 유명 기록은 RAG 없이도 대부분 맞힘. 차이는 덜 알려진 기록 · 계산 지표에서 큼 |
| F2016 | 종류가 다른 출처 함께 색인 · 출처 종류 구분 표시 · 수집 · 청킹 차이 설명 | ✅ | 외부 문서 컬렉션에 출처 3종: 기록 데이터(Lahman CSV → 시즌 문서, 1행 = 1청크) · 위키백과 한/영(1000/200 분할) · 지표 사전(`build/metrics.json` 직접 작성, 지표 1개 = 1청크). 근거마다 출처 종류 표시. 지표 사전은 질문 · 검색어에 지표 이름이 나오면 근거에 추가 | 기록은 표가 잘리면 수치가 섞여 행 단위, 지표 사전은 정의 · 계산식 · 해석이 한 묶음이라 항목 단위. 명세서 예시(위키 + PDF)와 조합이 달라 인정 여부는 확인 필요 |

### 3.3 비기능 요구사항 (NF2001 ~ NF2007)

| 번호 | 요구사항 | 상태 | 구현 | 비고 |
|---|---|---|---|---|
| NF2001 | 대표 질문 처리 시간이 사용에 지장 없음 | ✅ | 답변 스트리밍으로 근거 목록을 먼저 보여 주고 답변은 생성되는 대로 표시. 보충 수집은 근거가 부족할 때만(거리 > 0.33) 하고 영어 검색어 2개로 줄여 약 25초. 보충 수집 없는 질문 4~15초, 조건 탐색 3~25초 (`gpt-5.4-mini`, GMS 응답 속도에 따라 변동) | 실측: 근거 표시 9.7초 · 첫 글자 10.6초 · 완료 16.8초 (GMS가 느린 시간대) |
| NF2002 | 이미 수집 · 색인한 검색어는 다시 수집하지 않음 | ✅ | 위키 수집 manifest에 선수별 검색어(`q:en:…`) · 문서 ID를 기록해 같은 검색어 · 같은 문서는 다시 수집하지 않음. 색인은 내용이 같은 청크를 다시 임베딩하지 않음 | |
| NF2003 | API 키는 환경변수 · 소스코드에 포함 안 함 | ✅ | `.env`(GMS_KEY · WIKI_CONTACT)만 사용, `.gitignore`로 제외, 저장소에는 `.env.example`만 | |
| NF2004 | 화면에 키 · 프롬프트 전문 · 오류 추적 정보 노출 안 함 | ✅ | API는 오류 시 일반 안내 문구만 반환, 프롬프트 · 키는 응답에 포함하지 않음. Django `DEBUG`는 기본 꺼짐(`DJANGO_DEBUG=1`일 때만 켜짐) | 확인: 없는 주소 → 일반 404 페이지(추적 정보 없음), 정적 파일 정상 제공 |
| NF2005 | 수집 · 색인 · 검색 · 생성 · UI 책임 분리, 도메인 부분은 데이터 준비 영역에 | ✅ | `collect/`(수집) · `build/`(도메인 정규화 · 지표 계산 · 한국어 표기) · `rag/indexer.py`(색인) · `rag/graph.py`(검색 · 생성) · `rag/prompts.py`(프롬프트) · `web/`(UI) | |
| NF2006 | 재시도 · 호출 간격 · User-Agent 연락처 | ✅ | 모든 수집 스크립트 User-Agent에 연락처(`.env`), 요청 간 대기, 위키 수집은 429 · 5xx 재시도(Retry-After 준수, 최대 4회) | |
| NF2007 | 데이터 · 문서 출처와 이용 조건 기록 · 준수 | ✅ | 5장(원천 출처 · 수집/가공 데이터별 라이선스), 화면 왼쪽 하단 출처 표기, 근거마다 원문 링크 | |

### 3.4 검증 · 산출물 (명세서 4 · 6장)

| 항목 | 상태 |
|---|---|
| 4장 검증 체크리스트 (통과 · 실패 · 미확인 + 화면 캡처) | 🔲 예정 |
| 요구사항 정의서 (도메인 조건 충족 근거 · 근거가 필요한 질문 · 기능/비기능 요구사항) | ✅ [`docs/requirements.md`](docs/requirements.md) |
| RAG 설계문서 (컬렉션 2개 구조 · 프롬프트 3개 · 청크 · Top-k 선택 이유와 변경 시 차이 · 문제와 해결) | ✅ [`docs/rag_design.md`](docs/rag_design.md) |
| RAG 전후 비교 문서 (F2015) | ✅ `docs/rag_comparison.md` |
| 소스코드 (수집 · 색인 스크립트 포함) · README | 🟡 진행 중 |

## 4. 데이터 준비 및 색인 절차

| 순서 | 스크립트 | 내용 | 결과 |
|---|---|---|---|
| 1 | `collect/01_download_lahman.py` | Lahman CSV 14개 다운로드 (선수 · 타격 · 투구 · 수비 · 팀 · 수상 · 출장 · 올스타 · 명예의 전당 · 포스트시즌 시리즈 결과 · 포스트시즌 타격/투구/수비) | `data/raw/lahman/` |
| 2 | `collect/02_download_chadwick.py` | Chadwick Register에서 범위 선수 ID 매핑만 추출 | `data/raw/chadwick/people_mlb.csv` |
| 3 | `collect/03_link_wikidata.py` | Wikidata로 한국어 이름 · 한/영 위키 문서 연결, 한국어 문서 길이 확인 | `data/raw/wikidata/players_wikidata.csv` |
| 4 | `collect/04_collect_player_wiki.py` | 선수 본인 한/영 위키 문서 수집 (문서 JSON + manifest, 재수집 방지) | `data/raw/wiki/` |
| 5 | `build/01_build_players.py` | 선수 1명 = 항목 1건으로 정규화 (프로필 · 통산 · 최고 시즌 · 수상 · 포스트시즌 · 특징 · 색인 텍스트) | `data/processed/players.json` |
| 6 | `build/02_build_record_docs.py` | 기록 문서: 선수×시즌(정규 · 포스트) · 팀×시즌 1행 = 문서 1개, 지표는 `build/metrics.py`로 로컬 계산 | `data/processed/record_docs.json` |
| 7 | `build/03_build_leaders.py` | 메인 시즌 타임라인: 연도별 홈런 · 타율 · 평균자책점 · 탈삼진 1위(MLB 전체 선수, 규정 = 그해 팀 경기 수 기준) · MVP · 사이영상 | `data/processed/season_leaders.json` |
| 8 | `build/metrics.json` | 지표 사전 38개 (정의 · 계산식 · 해석 · 참고 위키 문서, 직접 작성) — 색인 시 외부 문서 컬렉션에 출처 "지표 사전"으로 들어감 | `build/metrics.json` |
| 9 | `rag/indexer.py` | 색인: `player_meta` (선수 2,047) · `player_docs` (기록 44,389 + 위키 41,980 + 지표 사전 38 = 청크 86,407) | `chroma_db/` |

`data/` 폴더는 저장소에 포함하지 않습니다. 위 순서대로 스크립트를 실행하면 다시 만들어집니다. `build/` 스크립트는 `build/` 폴더 안의 공용 모듈(`lahman_loader.py`, `seasons.py`, `metrics.py`, `names_ko.py`)을 사용합니다.

현재 데이터 규모

| 항목 | 값 |
|---|---|
| 범위 선수 (1901~2025, AL · NL) | 19,200명 |
| Wikidata 연결 | 17,255명 |
| **항목 (한국어 · 영어 위키 문서 모두 있음)** | **2,047명** (투수 954 · 타자 1,093) |
| 위키 문서 (선수 본인 문서 + 질문 시 보충 수집, 참고문헌 절 제외) | 4,105건 (한국어 2,047 · 본문 중앙값 438자 / 영어 2,058 · 중앙값 7,294자) |
| 기록 문서 | 26,302건 (선수 정규시즌 19,249 · 선수 포스트시즌 4,347 · 팀 시즌 2,706) |
| 시즌 타임라인 | 125시즌 (부문 1위 500칸 중 서비스 선수 연결 388칸) |

범위를 1901년부터로 잡은 이유: 아메리칸리그가 창설된 해로, 이후 AL · NL 두 리그 체제가 지금까지 이어집니다. 1900년 이전은 리그 구성과 규칙이 달라 제외했습니다. 초기 시즌은 도루 실패 · 희생플라이 · 상대 타자 수 같은 열이 비어 있어, 그 값을 쓰는 지표는 계산하지 않고 비워 둡니다.

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
| `data/raw/chadwick/people_mlb.csv` | `collect/02` | Chadwick | ODC-By 1.0 | 범위 선수 19,200명 행 · 열만 추출 |
| `data/raw/wikidata/players_wikidata.csv` | `collect/03` | Wikidata (+ Chadwick ID) | CC0 (Chadwick ID 열은 ODC-By) | 이름 · 문서 제목 · 문서 길이만 조회 |
| `data/raw/wiki/docs/*.json` (4,105건) | `collect/04` | 한/영 위키백과 | **CC BY-SA 4.0** | 일반 텍스트로 추출, 각주 · 외부 링크 · 참고 문헌 절 제거 |
| `data/processed/players.json` | `build/01` | Lahman · Chadwick · Wikidata | **CC BY-SA 3.0** | 1901~2025 AL · NL 합산, 지표 계산, 한국어 표기, 규칙 기반 요약 문장 |
| `data/processed/record_docs.json` | `build/02` | Lahman | **CC BY-SA 3.0** | 선수 · 팀 시즌별 문서화, 세이버메트릭스 지표 계산 |
| `data/processed/season_leaders.json` | `build/03` | Lahman | **CC BY-SA 3.0** | 연도별 부문 1위 · 수상 집계 |
| `build/metrics.json` (지표 사전) | 직접 작성 | 위키백과 지표 문서 참고 (링크만, 본문 복제 없음) | 프로젝트 작성물 | 정의 · 계산식 · 해석을 직접 서술 |
| `chroma_db/` (색인) | `rag/indexer.py` | 위 전체 | 각 청크의 원 출처 라이선스 | 청킹 · 임베딩 |

- **동일 조건 변경 허락(SA)**: Lahman · 위키백과를 가공한 데이터는 공유할 때 같은 CC BY-SA 라이선스로 공유해야 합니다.
- **출처 표시**: 화면 하단과 답변 근거에 출처(Lahman · 위키백과 문서 제목과 URL)와 라이선스를 표시합니다.
- **저장소 배포 범위**: `data/`와 `chroma_db/`는 저장소에 포함하지 않습니다. 저장소에는 데이터를 받고 가공하는 코드만 있고, 데이터는 각 출처에서 직접 받아 만듭니다.
- **이용 예절 (NF2006)**: 위키백과 · Wikidata API 호출 시 User-Agent에 연락처(`.env`의 `WIKI_CONTACT`)를 넣고, 요청 사이에 대기합니다 (Wikidata 0.3~1초, 위키백과 0.4초). 위키백과 수집은 429 · 5xx 응답 시 Retry-After를 따라 최대 4회 재시도합니다. 한 번 수집한 문서는 manifest로 관리해 다시 받지 않습니다 (NF2002).
- **사용하지 않은 출처**: KBO 공식 사이트 · 스탯티즈(자동 수집 금지), Baseball-Reference · FanGraphs · Baseball Savant(대량 수집 · 재배포 제한).

## 6. 심화 기능 · 추가 기능 요약

| 기능 | 내용 | 코드 |
|---|---|---|
| F2013 프론트엔드 직접 구현 | Django 템플릿 + HTML · CSS · JS, 화면과 JSON API 분리 | `web/chat/` |
| F2014 MMR | 위키 근거 후보 30개 → λ 0.7로 4개. CLI `--search-compare` · `/lab/`에서 유사도 검색과 비교 | `rag/graph.py` `search_mmr` |
| F2015 RAG 전후 비교 | 질문 12개 비교 | `docs/rag_comparison.md` |
| F2016 여러 출처 결합 | 기록 데이터 · 위키백과 한/영 · 지표 사전, 출처별 청킹 | `rag/indexer.py` |
| 사실 확인 | 주장 → 참 / 거짓 / 일부 사실 / 근거 부족 판정 + 근거 | `rag/prompts.py` FACTCHECK_RULES |
| 구단 시절 합산 | 질문의 구단에서 뛴 시즌만 합산(이적 시즌 별도 표시) | `rag/team_era.py` |
| 근거 원문 미리보기 | 인용한 근거 청크 본문을 펼쳐 봄 | `web/chat/static/chat/ask.js` |
| 답변 스트리밍 | 근거 먼저, 답변은 생성되는 대로 (NDJSON) | `web/chat/rag_service.py` `stream` |
| RAG 실험실 | 청크 · Top-k · 검색 방식 두 설정 나란히 실행 | `rag/lab.py` · `/lab/` |
| 커리어 그래프 | 시즌별 지표 추이 + 리그 평균(100) 기준선 | `web/chat/static/chat/chart.js` |
| 비슷한 선수 | 통산 지표 6개 표준화 거리로 5명 | `web/chat/similar.py` |
| 시즌 타임라인 | 1901~2025 연도별 우승 · 수상 · 부문 1위 | `build/03_build_leaders.py` · `home.js` |
