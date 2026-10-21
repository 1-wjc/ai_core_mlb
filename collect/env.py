# .env 읽기 (python-dotenv 없이 쓰는 최소 버전)
# 형식: KEY=VALUE 한 줄에 하나, # 으로 시작하면 주석. 이미 설정된 환경변수는 덮어쓰지 않는다.

import os

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


def load_env():
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def contact():
    """위키 · 데이터 API User-Agent 에 넣을 연락처 (NF2006). .env 의 WIKI_CONTACT"""
    load_env()
    value = os.environ.get("WIKI_CONTACT", "")
    if not value:
        raise SystemExit(".env 에 WIKI_CONTACT(연락처 이메일)를 넣어 주세요. .env.example 참고")
    return value
