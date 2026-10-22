from django.conf import settings
from django.contrib.staticfiles.views import serve as static_serve
from django.urls import include, path, re_path

urlpatterns = [
    path("", include("chat.urls")),
]
if not settings.DEBUG:
    # DEBUG 를 끄면 개발 서버가 정적 파일(CSS · JS)을 서빙하지 않으므로 직접 연결 (과제 시연용 단일 서버)
    urlpatterns.append(re_path(r"^static/(?P<path>.*)$", static_serve, {"insecure": True}))
