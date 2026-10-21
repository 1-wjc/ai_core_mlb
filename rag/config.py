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
TOP_K = env_int("TOP_K", 6)                        # 최종 근거로 쓰는 외부 청크 수
PER_QUERY_K = env_int("PER_QUERY_K", 6)            # 검색어 1개당 가져오는 후보 수

# ---- 경로 ----
PLAYERS_PATH = os.path.join(ROOT, "data", "processed", "players.json")
RECORD_DOCS_PATH = os.path.join(ROOT, "data", "processed", "record_docs.json")
WIKI_DOCS_DIR = os.path.join(ROOT, "data", "raw", "wiki", "docs")
CHROMA_DIR = os.path.join(ROOT, "chroma_db")

# ---- 컬렉션 (2개) ----
META_COLLECTION = "player_meta"
DOCS_COLLECTION = "player_docs"
