# Django 설정 — DB · 로그인 없이 화면(HTML/JS)과 JSON API만 제공
import mimetypes
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent          # web/
PROJECT_DIR = BASE_DIR.parent                              # src/ (.env · rag 패키지)
load_dotenv(PROJECT_DIR / ".env")
sys.path.insert(0, str(PROJECT_DIR))                     # rag 패키지 사용

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-for-production")   # 배포 시 .env 에 임의의 긴 문자열
# NF2004: 기본은 DEBUG 끔 — 오류가 나도 오류 추적 페이지를 화면에 내보내지 않는다. 개발할 때만 .env 에 DJANGO_DEBUG=1
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

# Windows 는 레지스트리 설정에 따라 .js 를 text/plain 으로 알려 주어 브라우저가 스크립트 실행을 거부한다 → 직접 지정
mimetypes.add_type("text/javascript", ".js", True)
mimetypes.add_type("text/css", ".css", True)
# 배포: 접속 주소(도메인 · IP)를 .env 의 DJANGO_ALLOWED_HOSTS 에 쉼표로 (기본은 이 PC 에서만)
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]
# https 도메인 · 다른 포트로 접속하면 POST(질문) 에 필요한 출처 — 예: https://mlb.example.com,http://10.0.0.5:8000
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request", "chat.context.assets"]},
}]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {}
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# 데이터 경로 (data/ 는 collect → build 스크립트로 생성)
# 수집 데이터 폴더 — 프로젝트 루트(src 의 부모)의 data/. .env 의 DATA_DIR 로 바꿀 수 있음
DATA_DIR = Path(os.environ.get("DATA_DIR") or PROJECT_DIR.parent / "data")
PLAYERS_PATH = DATA_DIR / "processed" / "players.json"
RECORD_DOCS_PATH = DATA_DIR / "processed" / "record_docs.json"
SEASON_LEADERS_PATH = DATA_DIR / "processed" / "season_leaders.json"   # build/03
SEASON_RANKS_PATH = DATA_DIR / "processed" / "season_ranks.json"       # build/04 시즌 리그 순위
