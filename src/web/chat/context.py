# 템플릿 공통 값 — 정적 파일 버전 (style.css · *.js 주소 뒤 ?v=)
#   정적 파일이 바뀌면 주소가 달라져 브라우저가 예전 파일을 캐시에서 쓰지 않는다 (강력 새로고침 불필요)

import os

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "chat")


def assets(request):
    try:
        version = int(max(os.path.getmtime(os.path.join(STATIC_DIR, f)) for f in os.listdir(STATIC_DIR)))
    except (OSError, ValueError):
        version = 0
    return {"asset_v": version}
