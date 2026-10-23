# MLB 세이버메트릭스 RAG — 근거를 대고 답하는 야구 기록 서비스

> AI 코어 프로젝트 2회차 · RAG 기반 도메인 지식 서비스
> 최종 갱신: 2026-10-23

| 제출물 | 위치 |
|---|---|
| 1. 요구사항 정의서 | [`docs/requirements.md`](docs/requirements.md) |
| 2. RAG 파이프라인 설계문서 | [`RAG_파이프라인_설계문서.md`](RAG_파이프라인_설계문서.md) |
| 3. 검증 결과 (확인 항목별 결과 · 요구사항 대조표 · 테스트 결과표 · 화면 캡처) | [`docs/verification.md`](docs/verification.md) · [`docs/images/verify/`](docs/images/verify/) |
| RAG 사용 전후 비교 (F2015) | [`docs/rag_comparison.md`](docs/rag_comparison.md) |
| 4. 구현 소스코드 · 수집 데이터 | [`src/`](src/) (수집 `collect/` · 정규화 · 지표 `build/` · 색인 · 검색 · 생성 `rag/` · 화면 `web/` · CLI `scripts/`) · [`data/`](data/) |
| 5. 셀프 · 상호 체크리스트 | `체크리스트/` |
| 6. README | 이 문서 (실행 방법 2장 · 이용 흐름별 기능 설명 3장(필수 · 심화 · 추가 구분 표시) · 데이터 준비 4장 · 데이터 출처와 이용 조건 5장) |
| 개발 기록 | [`docs/progress_log.md`](docs/progress_log.md) (결정 로그) |

```
.
├── README.md
├── RAG_파이프라인_설계문서.md
├── data/                 수집 · 가공 데이터 (raw: 원천 CSV · 위키 문서 / processed: 선수 · 기록 문서 JSON)
├── src/                  실행에 필요한 모든 코드 — 명령은 이 폴더에서 실행
│   ├── collect/          수집 (Lahman · Chadwick · Wikidata · 위키백과)
│   ├── build/            정규화 · 지표 계산 · 한국어 표기 · 순위 · 마일스톤
│   ├── rag/              색인 · 검색 · 생성 (LangGraph) · 프롬프트
│   ├── web/              화면 (Django: 페이지 + JSON API)
│   ├── scripts/          확인용 CLI
│   ├── requirements.txt
│   └── .env.sample       .env 로 복사해 값 채움
├── docs/                 요구사항 정의서 · 검증 결과 · RAG 전후 비교 · 개발 기록 · 화면 캡처
└── 체크리스트/            셀프 · 상호 체크리스트
```

---

## 1. 프로젝트 개요

MLB 선수의 시즌 기록과 세이버메트릭스 지표, 위키백과 서술 문서를 근거로 질문에 답하고, 답변에 사용한 근거를 함께 보여 주는 서비스.

- **항목**: 한국어 · 영어 위키백과 문서가 모두 있는 MLB 선수 (1901\~2025 시즌 AL · NL 출장, 2,047명)
- **근거**: 기록 데이터(Lahman, 직접 계산한 지표) + 위키백과 문서(한국어 · 영어) + 지표 사전
- **원칙**: 근거에 없는 내용은 "확인되지 않는다"고 답하고, 수치는 코드로 계산한 값만 인용
- **서비스 범위**: 2025 시즌까지

## 2. 실행 방법

Python 3.11 기준 (명세서 지정 버전 + Django). **아래 명령은 모두 `src/` 폴더에서 실행.**

```bash
cd src
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash
pip install -r requirements.txt
cp .env.sample .env                  # 값 채우기
```

`src/.env` (저장소에 올리지 않음)
```
GMS_KEY=발급받은_키
WIKI_CONTACT=your-email@example.com
# 선택: CHAT_MODEL · EMBED_MODEL · CHUNK_SIZE · CHUNK_OVERLAP · TOP_K_RECORD · TOP_K_WIKI · PER_QUERY_K
#       COLLECT_MODE(auto|always|off) · COLLECT_IF_DISTANCE · HISTORY_TURNS · EXPLORE_CANDIDATES (rag/config.py)
# 선택: DJANGO_DEBUG=1 (개발 중에만. 기본은 꺼짐 → 오류 추적 정보를 화면에 보이지 않음)
# 선택: DATA_DIR=데이터 폴더 경로 (기본: 프로젝트 루트의 data/)
```

데이터 준비(4장, `data/`가 이미 있으면 생략) → 색인 → 화면 실행
```bash
python -m rag.indexer --all                          # 전체 색인 (일부만: --players ryuhy01,troutmi01)
python web/manage.py runserver                       # http://127.0.0.1:8000
```

GMS 키와 색인이 있으면 RAG 모드, 없으면 기록 검색 모드(질문의 연도 · 키워드로 기록 문서를 찾아 보여 줌, LLM 미사용)로 동작.

다른 PC · 서버에서 접속하게 실행 (배포)
```bash
# .env: DJANGO_SECRET_KEY · DJANGO_ALLOWED_HOSTS(접속 주소) · 필요하면 DJANGO_CSRF_TRUSTED_ORIGINS (https 도메인)
python web/manage.py runserver 0.0.0.0:8000
```
- 색인 `src/chroma_db/`(약 1.5GB)는 용량 때문에 저장소에 없음 → `python -m rag.indexer --all`로 생성(약 30분 · GMS 임베딩 크레딧 사용)하거나 만들어 둔 폴더를 그대로 복사
- DEBUG는 기본 꺼짐, 정적 파일은 앱이 직접 제공 (별도 웹 서버 설정 없이 동작)
- GMS 호출은 시간 제한 60초 · 일시 오류 시 3회 재시도 (`LLM_TIMEOUT` · `LLM_RETRIES`)

확인용 CLI
```bash
python -m scripts.ask ryuhy01 "2019년 평균자책점과 FIP 차이는?"
python -m scripts.ask ryuhy01 "2019 시즌 투구 비교" --compare kershcl01
python -m scripts.ask kershcl01 "포스트시즌 부진" --search-compare   # 유사도 vs MMR 근거 비교
python -m scripts.ask --graph                                       # 그래프 구조 (retrieve → generate)
```

## 3. 기능 — 이용 흐름

사용자가 선수를 찾고 → 기록을 보고 → 질문하는 순서로 정리. 코드 경로는 `src/` 기준. 기능마다 명세서 구분을 붙임: **[필수 F20xx]** · **[심화 F20xx]** · **[추가]** (명세서에 없고 이 서비스에서 더한 기능).
요구사항 번호별 정의는 [`docs/requirements.md`](docs/requirements.md), 번호별 동작 확인(실행 결과 · 수치 · 화면 캡처)은 [`docs/verification.md`](docs/verification.md).

| 화면 | 주소 | 하는 일 |
|---|---|---|
| 메인 | `/` | 선수 검색 · 질문 예시 · 시즌 타임라인 · 전체 선수 목록 |
| 선수 | `/players/<id>/` | 프로필 · 기록 · 그래프 · 비슷한 선수 · 질문 패널 |
| 비교 | `/compare/?a=&b=` | 두 선수 통산 비교 · 비교 질문 |
| 조건 탐색 | `/explore/` | 문장으로 조건을 입력해 선수 찾기 |
| RAG 실험실 | `/lab/` | 검색 설정 두 가지를 나란히 실행 |

### 3.1 선수 찾기

- **이름 검색** — 메인 검색창에 한글 · 영문 이름. 입력하는 동안 자동 완성, 검색하면 다른 영역은 숨기고 결과 카드만. 화면 이름과 표기가 다른 이름(클레이턴 커쇼 · 타이 콥 · 한국어 문서 제목 · Lahman 영문 이름)으로도 찾음 **[필수 F2009 · 추가: 검색 별칭]**
- **전체 선수 목록** — 투수 / 타자, 이름순 / 최근순(마지막 활약 연도), 구단별(옛 이름 시절 포함) 필터
- **조건 탐색** — "통산 홈런 500개 이상인 우타자"처럼 문장으로 입력하면 조건을 모두 만족하는 선수만 카드로. 숫자 · 투타 · 국가 · 수상은 코드 규칙으로 걸러 빠짐 · 섞임이 없고, 규칙 밖 조건("선발투수", "파워 히터")만 프롬프트 2가 판정. 카드에는 조건 값("통산 세이브 310개"), 최근 선수부터 24장씩. 카드를 누르면 그 선수 페이지에서 질문을 이어 감 **[필수 F2011]**
- **시즌 타임라인** — 1901\~2025 연도를 넘기며 월드시리즈 우승팀 · MVP · 사이영상 · 부문 1위 · 그해 큰 기록(500홈런 · 3,000안타 · 300승 · 3,000탈삼진 · 500세이브 등) 달성자(MLB 전체 선수 기준) **[추가]**
- **질문 예시** — 메인에서 누르면 그 선수 페이지에서 바로 질문

코드: `web/chat/pages.py` · `home.js` · `rag/explore.py` · `build/03_build_leaders.py`

### 3.2 선수 기록 보기

- **항목 데이터** — 선수 1명 = 항목 1건. 이름 · 투타 · 포지션 · 출신 · 소속 · 통산 기록 · 최고 시즌 · 수상 · 기록 달성 · 특징을 한 텍스트로 묶어 색인(`build/01_build_players.py` → `players.json` 2,047명) **[필수 F2001 · F2002]**
- **프로필** — 영어 이름(한글 병기) · 포지션 · 활약 기간 · 소속 구단 약자(마우스를 올리면 그 시대 구단 이름, 예: BSN = 보스턴 브레이브스)
- **이름 아래 칩** — 명예의 전당 · 월드시리즈 우승 · 올스타 / 플레이 스타일(통산 지표로 판정) / 기록 달성 / 수상
- **기록 달성(마일스톤)** — 통산 기록이 아래 단계를 넘은 시즌. 종류마다 가장 높은 단계 하나만 표시하고(500홈런이면 200 · 300 · 400홈런은 생략), 1900년 이전 시즌까지 포함한 실제 통산으로 계산 **[추가]**

  | 타격 | 단계 | 투구 | 단계 |
  |---|---|---|---|
  | 홈런 | 200부터 100 단위 | 승 | 100부터 100 단위 |
  | 안타 | 1,000부터 1,000 단위 | 탈삼진 | 1,000부터 1,000 단위 |
  | 타점 · 득점 · 볼넷 | 1,000부터 500 단위 | 세이브 | 200부터 100 단위 |
  | 2루타 | 400부터 100 단위 | 이닝 | 1,500부터 500 단위 |
  | 도루 | 300부터 100 단위 | | |
  | 출장 경기 | 2,000부터 500 단위 | | |

- **통산 · 시즌별 기록** — [기본 · 세이버 · 상세] 탭, 시즌별은 [정규 · 포스트] × [기본 · 세이버 · 상세 · 수비]. OPS+ · ERA+ · FIP 등 지표는 Lahman 원기록으로 직접 계산(`build/metrics.py`). 정규시즌 표에는 그 시즌 리그 순위 10위 안인 값 옆에 순위 배지(1901\~2025 AL · NL 전체 선수 기준, 비율 지표는 규정 타석 · 이닝 이상) **[추가: 시즌 리그 순위]**
- **커리어 그래프** — 시즌별 OPS+ · ERA+ 등 추이, 리그 평균(100) 기준선 **[추가]**
- **비슷한 선수** — 통산 비율 지표 6개를 표준화한 거리로 5명. 투수는 역할에 따라 세이브 · 선발 비율 지표를 빼고 선발은 선발끼리 **[추가]**

코드: `web/chat/pages.py` · `templates/chat/player.html` · `chart.js` · `similar.py` · `build/01_build_players.py` · `build/milestones.py` · `build/04_build_ranks.py`

### 3.3 질문하기 (RAG)

선수 페이지 오른쪽 질문 패널. 질문 한 번에 아래 순서로 동작 (LangGraph `retrieve` → `generate` 2노드) **[필수 F2007]**

1. **검색어 추출** — 프롬프트 1이 MLB 기록 분석가 역할로 검색어를 JSON 배열로 뽑음. 직전 대화로 "그 해" 같은 표현을 풀어 씀 **[필수 F2003 · F2009]**
2. **근거 검색** — 선수 메타데이터는 항상 근거 1번 **[필수 F2002 · F2006]**. 그 선수 범위 안에서 기록 문서(질문 연도가 있으면 그 시즌만)와 위키 청크를 검색해 병합 · 중복 제거 **[필수 F2005 · F2006]**. 위키는 MMR로 서로 다른 내용을 고름 **[심화 F2014]**. 질문에 구단이 나오면 그 구단 시절 합산, "몇 위 · 리그 1위"를 물으면 시즌 리그 순위, 지표 이름이 나오면 지표 사전 항목도 근거로 **[심화 F2016]**
3. **보충 수집** — 위키 근거가 부족하면 위키백과를 검색해 프롬프트 2가 제목 · 요약만 보고 고른 문서를 수집 · 색인한 뒤 다시 검색. 한 번 수집한 검색어 · 문서는 다시 받지 않음 **[필수 F2004]**
4. **답변 생성** — 프롬프트 3이 근거에 있는 내용만, 주장마다 `[근거 N]`, 근거가 없으면 "확인되지 않는다" **[필수 F2007]**
5. **표시** — 근거 목록을 먼저 보여 주고 답변은 생성되는 대로(스트리밍) **[추가]**. 실제 인용한 근거만 출처 종류(메타데이터 · 기록 데이터 · 영어/한국어 위키백과 · 지표 사전) · 원문 링크 · 인용한 본문과 함께, 인용이 없으면 안내 **[필수 F2008 · 심화 F2016 · 추가: 원문 미리보기]**. 답변 수치가 근거 본문에 있는지 코드로 대조해 근거에 없는 수치(계산값 등)와 근거 번호 없는 문장을 표시 **[추가: 문장별 근거 점검]**
6. **진행 상태 · 안내** — 검색어 · 문서 수집 결과 · 출처별 근거 수 · 소요 시간. 키가 없거나 색인이 비면 안내 후 기록 검색 모드로 답변 **[필수 F2012]**
7. **대화 기록** — 선수(비교는 선수 조합)별로 브라우저에 저장, 다른 선수와 섞이지 않음 **[필수 F2009]**

| 기본 설정 (`rag/config.py`, `.env`로 변경) | 값 |
|---|---|
| 채팅 · 임베딩 모델 | `gpt-5.4-mini` · `text-embedding-3-large` (GMS, OpenAI 호환 주소) |
| 청크 크기 / 겹침 | 위키 1000 / 200, 기록 문서는 1문서 = 1청크, 지표 사전은 지표 1개 = 1청크 |
| Top-k | 기록 3 · 위키 4 + 메타데이터 1 항상 + 지표 사전 최대 3 |
| 위키 검색 | MMR (후보 30개 → λ 0.7로 4개) |
| 보충 수집 | 가장 가까운 위키 근거 거리 > 0.33일 때만 |

코드: `rag/graph.py` · `prompts.py` · `collector.py` · `indexer.py` · `team_era.py` · `ranks.py` · `citecheck.py` · `web/chat/static/chat/ask.js`

### 3.4 비교 · 사실 확인

- **두 선수 비교** — 비교 화면에서 두 선수를 고르면 통산 지표 표(더 나은 값 강조)와 비교 질문. 질문은 두 선수 범위를 각각 검색해 항목별 "A 값 [근거] / B 값 [근거]" **[필수 F2010]**
- **시대 보정** — 비교 표를 [원래 기록 · 리그 대비]로 전환. 리그 대비는 시즌마다 리그 평균과 비교해 출전량으로 가중한 지수(100 = 리그 평균)로, 루스 vs 저지처럼 시대가 다른 선수 비교용. 비교 질문 · "시대 · 리그 대비" 질문에는 이 지수가 근거로 들어감 **[추가]**
- **사실 확인** — 질문 패널을 [사실 확인]으로 바꾸고 주장을 입력하면 근거와 대조해 "참 · 거짓 · 일부 사실 · 근거 부족" 판정 배지와 근거 **[필수 F2010]**
- **구단 시절 합산** — "카디널스 시절 통산 홈런은?"처럼 구단을 지정하면 그 구단에서 뛴 시즌을 코드로 합산해 근거로 (시즌 중 이적한 해는 빼고 밝힘) **[필수 F2010]**

코드: `templates/chat/compare.html` · `rag/relative.py` · `rag/team_era.py` · `rag/prompts.py`(COMPARE_RULES · FACTCHECK_RULES)

### 3.5 검색 설정 실험

- **RAG 실험실** — 같은 선수 · 같은 질문을 두 설정(청크 크기 · 기록/위키 Top-k · 유사도/MMR · λ)으로 나란히 실행해 근거 목록 · 근거끼리 평균 유사도 · 답변 차이를 봄. 청크 크기를 바꾸면 그 선수 문서만 메모리에 임시 색인 **[심화 F2014 확인용 · 추가]**
- **RAG 사용 전후 비교** — 근거 없이 틀리기 쉬운 질문 12개를 RAG 없이 / RAG로 답하게 한 비교 문서 [`docs/rag_comparison.md`](docs/rag_comparison.md) **[심화 F2015]**

코드: `rag/lab.py` · `templates/chat/lab.html` · `lab.js`

### 3.6 화면과 서버 구조

Django가 화면(템플릿 + HTML · CSS · JS)과 JSON API를 나눠 제공 (Streamlit 대신) **[심화 F2013]**. 화면 코드: `web/chat/pages.py`(페이지) · `views.py`(API) · `templates/chat/` · `static/chat/`

| API | 요청 | 응답 |
|---|---|---|
| `GET /api/status` | | `{mode, notice, key_ready, players, record_docs, index_meta, index_docs}` |
| `GET /api/players` | | `{players: [{player_id, name_ko, name_en, aliases, role, position, first_season, last_season}]}` |
| `POST /api/ask` | `{player_id, question, compare_id?, history?, mode?}` (`mode`: `ask` · `factcheck`) | `{answer, verdict?, sources: [{n, title, url, source, text?}], cited: [n], steps, collected, check, mode, elapsed}` (`text`는 인용한 근거만, `check`는 문장별 근거 점검) |
| `POST /api/ask_stream` | `/api/ask`와 같음 | NDJSON 한 줄씩: `{type: evidence}` → `{type: token}` … → `{type: final}` (오류 시 `{type: error}`) |
| `POST /api/explore` | `{condition}` | `{cards: [{player_id, name_ko, name_en, role, position, first_season, last_season, reason}], candidates, rule, elapsed}` |
| `POST /api/lab` | `{player_id, question, configs: [설정 A, 설정 B]}` | 설정별 근거 · 답변 · 소요 시간 |

비기능 요구사항(NF2001 \~ NF2007)의 구현과 확인은 [`docs/verification.md`](docs/verification.md) 4.7. 키 관리는 2장, 출처 · 이용 조건과 외부 호출 예절은 5장.

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
| 7-2 | `build/04_build_ranks.py` | 시즌 리그 순위: 1901\~2025 AL · NL 전체 선수로 시즌 · 리그별 순위 (홈런 · 안타 · 타점 · 득점 · 도루 · 볼넷 · 타율 · 출루율 · 장타율 · OPS · 승 · 세이브 · 탈삼진 · 이닝 · 평균자책점 · WHIP, 서비스 선수의 10위 안만 저장) | `data/processed/season_ranks.json` |
| 8 | `build/metrics.json` | 지표 사전 38개 (정의 · 계산식 · 해석 · 참고 위키 문서, 직접 작성) — 색인 시 외부 문서 컬렉션에 출처 "지표 사전"으로 들어감 | `build/metrics.json` |
| 9 | `rag/indexer.py` | 색인: `player_meta` (선수 2,047) · `player_docs` (기록 44,389 + 위키 41,980 + 지표 사전 38 = 청크 86,407) | `src/chroma_db/` |

스크립트 경로는 `src/` 기준이고 결과는 프로젝트 루트의 `data/`에 저장. `data/`에는 수집 · 가공 결과가 들어 있으며, 없으면 위 순서대로 실행해 다시 만들 수 있음(수집 약 1시간 · 빌드 수 분). 색인 `src/chroma_db/`는 용량(약 1.5GB) 때문에 저장소에 포함하지 않음. `build/` 스크립트는 `build/` 폴더 안의 공용 모듈(`lahman_loader.py`, `seasons.py`, `metrics.py`, `names_ko.py`, `milestones.py`)을 사용.

현재 데이터 규모

| 항목 | 값 |
|---|---|
| 범위 선수 (1901\~2025, AL · NL) | 19,200명 |
| Wikidata 연결 | 17,255명 |
| **항목 (한국어 · 영어 위키 문서 모두 있음)** | **2,047명** (투수 954 · 타자 1,093) |
| 위키 문서 (선수 본인 문서 + 질문 시 보충 수집, 참고문헌 절 제외) | 4,105건 (한국어 2,047 · 본문 중앙값 438자 / 영어 2,058 · 중앙값 7,294자) |
| 기록 문서 | 26,302건 (선수 정규시즌 19,249 · 선수 포스트시즌 4,347 · 팀 시즌 2,706) |
| 시즌 타임라인 | 125시즌 (부문 1위 500칸 중 서비스 선수 연결 388칸) |

범위를 1901년부터로 잡은 이유: 아메리칸리그가 창설된 해로, 이후 AL · NL 두 리그 체제가 지금까지 이어짐. 1900년 이전은 리그 구성과 규칙이 달라 제외. 초기 시즌은 도루 실패 · 희생플라이 · 상대 타자 수 같은 열이 비어 있어, 그 값을 쓰는 지표는 계산하지 않고 비워 둠.

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
| `data/processed/players.json` | `build/01` | Lahman · Chadwick · Wikidata | **CC BY-SA 3.0** | 1901\~2025 AL · NL 합산, 지표 계산, 한국어 표기, 규칙 기반 요약 문장 |
| `data/processed/record_docs.json` | `build/02` | Lahman | **CC BY-SA 3.0** | 선수 · 팀 시즌별 문서화, 세이버메트릭스 지표 계산 |
| `data/processed/season_leaders.json` | `build/03` | Lahman | **CC BY-SA 3.0** | 연도별 부문 1위 · 수상 집계 |
| `data/processed/season_ranks.json` | `build/04` | Lahman | **CC BY-SA 3.0** | 시즌 · 리그별 순위 집계 |
| `build/metrics.json` (지표 사전) | 직접 작성 | 위키백과 지표 문서 참고 (링크만, 본문 복제 없음) | 프로젝트 작성물 | 정의 · 계산식 · 해석을 직접 서술 |
| `src/chroma_db/` (색인, 저장소 제외) | `rag/indexer.py` | 위 전체 | 각 청크의 원 출처 라이선스 | 청킹 · 임베딩 |

- **동일 조건 변경 허락(SA)**: Lahman · 위키백과를 가공한 데이터는 공유할 때 같은 CC BY-SA 라이선스로 공유해야 함.
- **출처 표시**: 화면 하단과 답변 근거에 출처(Lahman · 위키백과 문서 제목과 URL)와 라이선스를 표시.
- **저장소 배포 범위**: 수집 · 가공 데이터(`data/`)는 위 이용 조건(출처 표시 · 동일 조건 공유)에 따라 포함. 색인 `src/chroma_db/`는 용량 때문에 제외하고 스크립트로 생성. 각 데이터는 원 출처의 라이선스를 따름.
- **이용 예절 (NF2006)**: 위키백과 · Wikidata API 호출 시 User-Agent에 연락처(`.env`의 `WIKI_CONTACT`)를 넣고, 요청 사이에 대기 (Wikidata 0.3\~1초, 위키백과 0.4초). 위키백과 수집은 429 · 5xx 응답 시 Retry-After를 따라 최대 4회 재시도. 한 번 수집한 문서는 manifest로 관리해 다시 받지 않음 (NF2002).
- **사용하지 않은 출처**: KBO 공식 사이트 · 스탯티즈(자동 수집 금지), Baseball-Reference · FanGraphs · Baseball Savant(대량 수집 · 재배포 제한).
