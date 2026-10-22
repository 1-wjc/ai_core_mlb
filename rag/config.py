# 설정 — 모델 · 청크 · Top-k · 경로
# 값은 .env 또는 환경변수로 바꿀 수 있다 (예: CHUNK_SIZE=800). 키는 .env 에만 둔다 (NF2003).

import os

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))


def env_int(name, default):
    return int(os.environ.get(name, default))


# ---- GMS (SSAFY) — OpenAI 호환 주소 ----
GMS_KEY = os.environ.get("GMS_KEY", "")
GMS_BASE_URL = os.environ.get("GMS_BASE_URL", "https://gms.ssafy.io/gmsapi/api.openai.com/v1")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "gpt-5.4-mini")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-large")
EMBED_BATCH = env_int("EMBED_BATCH", 100)          # 임베딩 요청 1번에 보내는 텍스트 수

# ---- 청크 (F2005: 위키 문서만 청킹, 기록 문서는 1문서 = 1청크) ----
CHUNK_SIZE = env_int("CHUNK_SIZE", 1000)
CHUNK_OVERLAP = env_int("CHUNK_OVERLAP", 200)

# ---- 검색 (F2006) ----
# 기록 문서와 위키 문서를 따로 검색해 몫을 나눈다 (비슷한 시즌 기록이 위키 서술을 밀어내지 않게).
# 질문에 연도가 있으면 기록 문서는 그 시즌 것만 검색한다.
TOP_K_RECORD = env_int("TOP_K_RECORD", 3)          # 근거로 쓰는 기록 문서 수
TOP_K_WIKI = env_int("TOP_K_WIKI", 4)              # 근거로 쓰는 위키 청크 수
PER_QUERY_K = env_int("PER_QUERY_K", 6)            # 검색어 1개당 가져오는 후보 수

# 위키 청크 선택 방식 (F2014): mmr — 후보를 MMR_FETCH_K 개 가져와 다양성까지 고려해 고름 · similarity — 유사도 순
SEARCH_MODE = os.environ.get("SEARCH_MODE", "mmr")
MMR_FETCH_K = env_int("MMR_FETCH_K", 30)
MMR_LAMBDA = float(os.environ.get("MMR_LAMBDA", "0.7"))       # 1 에 가까울수록 유사도, 0 에 가까울수록 다양성 중시
# 실측(λ 0.5~0.8): 0.5 는 무관한 절까지 섞임(류현진 부상 질문에 "미디어 출연"), 0.7 은 질문 유사도를 유지하며 중복 감소
TOP_K_METRIC = env_int("TOP_K_METRIC", 3)          # 질문 · 검색어에 나온 지표의 사전 항목 최대 수

# ---- 질문 시 보충 수집 (F2004) ----
# auto: 기존 위키 근거가 부족할 때만(가장 가까운 거리 > COLLECT_IF_DISTANCE) · always: 새 검색어마다 · off: 수집 안 함
COLLECT_MODE = os.environ.get("COLLECT_MODE", "auto")
COLLECT_IF_DISTANCE = float(os.environ.get("COLLECT_IF_DISTANCE", "0.33"))   # 실측: 본인 문서에 있는 질문 0.23~0.32, 없는 질문 0.335~0.38
COLLECT_QUERIES = env_int("COLLECT_QUERIES", 2)         # 위키 검색에 쓰는 영어 검색어 수
COLLECT_CANDIDATES = env_int("COLLECT_CANDIDATES", 5)   # 검색어 1개당 위키 검색 후보 수
COLLECT_MAX_PICK = env_int("COLLECT_MAX_PICK", 2)        # 프롬프트 2가 고를 수 있는 최대 문서 수
COLLECT_MIN_CHARS = env_int("COLLECT_MIN_CHARS", 500)    # 본문이 너무 짧은 문서는 색인하지 않음
WIKI_CONTACT = os.environ.get("WIKI_CONTACT", "")

# ---- 대화 기록 (F2009) · 조건 탐색 (F2011) ----
HISTORY_TURNS = env_int("HISTORY_TURNS", 4)              # LLM에 넘기는 직전 대화 메시지 수
EXPLORE_CANDIDATES = env_int("EXPLORE_CANDIDATES", 40)   # 조건 탐색: 메타데이터에서 가져오는 후보 수
EXPLORE_MAX_PICK = env_int("EXPLORE_MAX_PICK", 12)       # 조건 탐색: 카드로 보여 줄 최대 선수 수

# ---- 경로 ----
PLAYERS_PATH = os.path.join(ROOT, "data", "processed", "players.json")
RECORD_DOCS_PATH = os.path.join(ROOT, "data", "processed", "record_docs.json")
METRICS_DICT_PATH = os.path.join(ROOT, "build", "metrics.json")    # 지표 사전 (직접 작성)
WIKI_DOCS_DIR = os.path.join(ROOT, "data", "raw", "wiki", "docs")
WIKI_MANIFEST_PATH = os.path.join(ROOT, "data", "raw", "wiki", "wiki_manifest.json")
CHROMA_DIR = os.path.join(ROOT, "chroma_db")

# ---- 컬렉션 (2개) ----
META_COLLECTION = "player_meta"
DOCS_COLLECTION = "player_docs"
