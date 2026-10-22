# 색인 — 컬렉션 2개 (F2002 · F2005 · F2016)
#   player_meta : 선수 1명 = 청크 1개, ID = player_id
#   player_docs : 기록 문서(1문서 = 1청크) + 위키 문서(청킹) + 지표 사전(지표 1개 = 1청크), ID = 항목ID:문서ID:순번
#                 지표 사전은 특정 선수 항목이 아니므로 항목ID 자리에 _glossary 를 쓴다
#
# 실행
#   python -m rag.indexer --players ryuhy01,troutmi01     # 일부 선수만 (흐름 확인용)
#   python -m rag.indexer --all                           # 전체
#
# 같은 ID는 덮어쓰고(upsert), 내용이 같은 청크는 임베딩을 다시 하지 않는다.
# 청크 설정이 바뀌어 사라진 청크(예: 순번이 줄어듦)는 지운다.

import argparse
import glob
import json
import os
import time

import chromadb
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag import config as C


# ---------------- 연결 ----------------
def get_embeddings():
    return OpenAIEmbeddings(
        model=C.EMBED_MODEL, api_key=C.GMS_KEY, base_url=C.GMS_BASE_URL,
        check_embedding_ctx_length=False,          # 토큰 배열 대신 문자열 그대로 보냄
        chunk_size=C.EMBED_BATCH,
    )


def get_collections():
    client = chromadb.PersistentClient(path=C.CHROMA_DIR)
    meta = client.get_or_create_collection(C.META_COLLECTION, metadata={"hnsw:space": "cosine"})
    docs = client.get_or_create_collection(C.DOCS_COLLECTION, metadata={"hnsw:space": "cosine"})
    return meta, docs


def clean_meta(d):
    """Chroma 메타데이터는 str · int · float · bool 만 가능, None 제외"""
    return {k: v for k, v in d.items() if isinstance(v, (str, int, float, bool))}


# ---------------- 청크 만들기 ----------------
def player_meta_chunk(p):
    bat = p["career"].get("batting", {})
    pit = p["career"].get("pitching", {})
    meta = {
        "player_id": p["player_id"], "name_ko": p["name_ko"], "name_en": p["name_en"],
        "role": p["role"], "primary_position": p["primary_position"], "two_way": p["two_way"],
        "first_season": p["first_season"], "last_season": p["last_season"],
        "birth_country": p["birth_country"], "teams": " | ".join(p["teams"]),
        "title": f"{p['name_ko']} 선수 정보", "url": p["ko_wiki"]["url"], "source": "메타데이터",
    }
    if bat:
        meta.update({"bat_PA": bat["metrics"].get("PA"), "bat_HR": bat["stats"].get("HR"),
                     "bat_SB": bat["stats"].get("SB"), "bat_AVG": bat["metrics"].get("AVG"),
                     "bat_OPS": bat["metrics"].get("OPS"), "bat_OPS_plus": bat["metrics"].get("OPS_plus")})
    if pit:
        meta.update({"pit_W": pit["stats"].get("W"), "pit_SV": pit["stats"].get("SV"),
                     "pit_SO": pit["stats"].get("SO"), "pit_ERA": pit["metrics"].get("ERA"),
                     "pit_ERA_plus": pit["metrics"].get("ERA_plus"), "pit_FIP": pit["metrics"].get("FIP")})
    return {"id": p["player_id"], "text": p["index_text"], "meta": clean_meta(meta)}


def record_chunks(pid, player_docs, team_docs):
    """선수의 시즌 기록 문서 + 그 시즌 소속 팀 문서 (팀 문서는 선수 범위마다 복사)"""
    chunks = []
    seen_team = set()
    for d in player_docs:
        chunks.append(record_chunk(pid, d))
        if d["doc_type"] != "season_regular":
            continue
        for team_id in d["teams"]:
            team_doc = team_docs.get(f"rec:team:{team_id}:{d['season']}")
            if team_doc and team_doc["doc_id"] not in seen_team:
                seen_team.add(team_doc["doc_id"])
                chunks.append(record_chunk(pid, team_doc, related=d["related_player"]))
    return chunks


def record_chunk(pid, d, related=None):
    meta = {
        "player_id": pid, "doc_id": d["doc_id"], "seq": 0, "title": d["title"], "url": d["url"],
        "source": d["source"], "doc_type": d["doc_type"], "season": d["season"],
        "related_player": related or d["related_player"],
    }
    return {"id": f"{pid}:{d['doc_id']}:0", "text": d["text"], "meta": clean_meta(meta)}


def wiki_chunks(pid, wiki_files, splitter):
    chunks = []
    for path in wiki_files:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        lang = "ko" if d["source"].startswith("한국어") else "en"
        doc_id = f"wiki-{lang}-{d['page_id']}"
        header = f"[선수: {d['related_player']} · {d['source']} · {d['title']}]\n"
        for seq, piece in enumerate(splitter.split_text(d["text"])):
            meta = {
                "player_id": pid, "doc_id": doc_id, "seq": seq, "title": d["title"], "url": d["url"],
                "source": d["source"], "doc_type": "wiki", "related_player": d["related_player"],
            }
            chunks.append({"id": f"{pid}:{doc_id}:{seq}", "text": header + piece, "meta": clean_meta(meta)})
    return chunks


GLOSSARY_ID = "_glossary"


def metric_chunks():
    """지표 사전(build/metrics.json) — 지표 1개 = 청크 1개 (출처 종류: 지표 사전)"""
    with open(C.METRICS_DICT_PATH, encoding="utf-8") as f:
        metrics = json.load(f)["metrics"]
    chunks = []
    for m in metrics:
        lines = [f"[지표 사전] {m['name_ko']} ({m['name_en']}) · 다른 이름: {', '.join(m['aliases'])} · 적용: {m['applies_to']}",
                 f"정의: {m['description']}", f"계산식: {m['formula']}", f"해석: {m['better']}"]
        if m.get("service_note"):
            lines.append(f"이 서비스의 계산: {m['service_note']}")
        if m["needs_league"]:
            lines.append("리그 기준값이 필요한 지표 (포스트시즌은 계산하지 않음)")
        doc_id = f"metric-{m['metric_id']}"
        meta = {"player_id": GLOSSARY_ID, "doc_id": doc_id, "seq": 0, "title": f"지표 사전: {m['name_ko']}",
                "url": m["reference"]["url"], "source": "지표 사전", "doc_type": "metric", "metric_id": m["metric_id"],
                "aliases": "|".join(m["aliases"]), "related_player": ""}
        chunks.append({"id": f"{GLOSSARY_ID}:{doc_id}:0", "text": "\n".join(lines), "meta": clean_meta(meta)})
    return chunks


# ---------------- 저장 (바뀐 것만 임베딩) ----------------
def upsert(collection, chunks, embeddings, cache):
    """cache: {텍스트: 벡터} — 같은 팀 문서처럼 텍스트가 같은 청크는 한 번만 임베딩"""
    ids = [c["id"] for c in chunks]
    existing = {}
    for i in range(0, len(ids), 500):
        got = collection.get(ids=ids[i:i + 500], include=["documents"])
        existing.update(dict(zip(got["ids"], got["documents"])))

    todo = [c for c in chunks if existing.get(c["id"]) != c["text"]]
    new_texts = list({c["text"] for c in todo if c["text"] not in cache})
    for i in range(0, len(new_texts), C.EMBED_BATCH):
        batch = new_texts[i:i + C.EMBED_BATCH]
        for text, vector in zip(batch, embeddings.embed_documents(batch)):
            cache[text] = vector
    for i in range(0, len(todo), 500):
        part = todo[i:i + 500]
        collection.upsert(ids=[c["id"] for c in part], documents=[c["text"] for c in part],
                          embeddings=[cache[c["text"]] for c in part], metadatas=[c["meta"] for c in part])
    return len(todo), len(new_texts)


def remove_stale(collection, pid, keep_ids):
    got = collection.get(where={"player_id": pid}, include=[])
    stale = [i for i in got["ids"] if i not in keep_ids]
    if stale:
        collection.delete(ids=stale)
    return len(stale)


def index_wiki_files(player_id, paths):
    """질문 시 보충 수집한 위키 문서를 선수 범위로 청킹 · 색인 (F2004). 색인한 청크 수를 돌려준다"""
    _, docs_col = get_collections()
    splitter = RecursiveCharacterTextSplitter(chunk_size=C.CHUNK_SIZE, chunk_overlap=C.CHUNK_OVERLAP)
    chunks = wiki_chunks(player_id, paths, splitter)
    upsert(docs_col, chunks, get_embeddings(), {})
    return len(chunks)


# ---------------- 실행 ----------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--players", help="쉼표로 구분한 player_id (bbref)")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if not C.GMS_KEY:
        raise SystemExit(".env 에 GMS_KEY 가 없습니다.")
    if not args.players and not args.all:
        raise SystemExit("--players 또는 --all 을 지정하세요.")

    with open(C.PLAYERS_PATH, encoding="utf-8") as f:
        players = json.load(f)
    with open(C.RECORD_DOCS_PATH, encoding="utf-8") as f:
        record_docs = json.load(f)
    if args.players:
        wanted = set(args.players.split(","))
        players = [p for p in players if p["player_id"] in wanted]
        missing = wanted - {p["player_id"] for p in players}
        if missing:
            print("항목에 없는 선수:", ", ".join(sorted(missing)))

    team_docs = {d["doc_id"]: d for d in record_docs if d["doc_type"] == "team_season"}
    docs_by_player = {}
    for d in record_docs:
        if d["player_id"]:
            docs_by_player.setdefault(d["player_id"], []).append(d)

    splitter = RecursiveCharacterTextSplitter(chunk_size=C.CHUNK_SIZE, chunk_overlap=C.CHUNK_OVERLAP)
    embeddings = get_embeddings()
    meta_col, docs_col = get_collections()
    cache = {}
    start = time.time()
    print(f"설정: 임베딩 {C.EMBED_MODEL} · 청크 {C.CHUNK_SIZE}/{C.CHUNK_OVERLAP} · 대상 선수 {len(players):,}명")

    # 1) 메타데이터 컬렉션
    meta_chunks = [player_meta_chunk(p) for p in players]
    written, embedded = upsert(meta_col, meta_chunks, embeddings, cache)
    print(f"[player_meta] 청크 {len(meta_chunks):,} · 새로 쓰기 {written:,} · 임베딩 {embedded:,}")

    # 2) 지표 사전 (외부 문서 컬렉션, 항목 ID 자리 = _glossary)
    glossary = metric_chunks()
    written, embedded = upsert(docs_col, glossary, embeddings, cache)
    stale = remove_stale(docs_col, GLOSSARY_ID, {c["id"] for c in glossary})
    print(f"[지표 사전] 청크 {len(glossary):,} · 새로 쓰기 {written:,} · 임베딩 {embedded:,} · 삭제 {stale}")

    # 3) 외부 문서 컬렉션 (선수 단위)
    total = {"record": 0, "wiki": 0, "written": 0, "embedded": 0, "stale": 0}
    for n, p in enumerate(players, 1):
        pid = p["player_id"]
        rec = record_chunks(pid, docs_by_player.get(pid, []), team_docs)
        wiki = wiki_chunks(pid, sorted(glob.glob(os.path.join(C.WIKI_DOCS_DIR, f"{pid}_*.json"))), splitter)
        written, embedded = upsert(docs_col, rec + wiki, embeddings, cache)
        stale = remove_stale(docs_col, pid, {c["id"] for c in rec + wiki})
        total["record"] += len(rec)
        total["wiki"] += len(wiki)
        total["written"] += written
        total["embedded"] += embedded
        total["stale"] += stale
        if n % 50 == 0 or n == len(players):
            print(f"  {n:,}/{len(players):,}명 · 기록 청크 {total['record']:,} · 위키 청크 {total['wiki']:,} · "
                  f"새로 쓰기 {total['written']:,} · 임베딩 {total['embedded']:,} · 삭제 {total['stale']:,} · "
                  f"{time.time() - start:.0f}초")

    print(f"\n색인 건수 — player_meta {meta_col.count():,} · player_docs {docs_col.count():,}")


if __name__ == "__main__":
    main()
