# Django 설정 — DB · 로그인 없이 화면(HTML/JS)과 JSON API만 제공
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent          # web/
PROJECT_DIR = BASE_DIR.parent                              # ai_core_pjt_02/
load_dotenv(PROJECT_DIR / ".env")
sys.path.insert(0, str(PROJECT_DIR))                     # rag 패키지 사용

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-for-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

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
    "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
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
PLAYERS_PATH = PROJECT_DIR / "data" / "processed" / "players.json"
RECORD_DOCS_PATH = PROJECT_DIR / "data" / "processed" / "record_docs.json"
