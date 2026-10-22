from django.urls import path

from chat import pages, views

urlpatterns = [
    # 화면
    path("", pages.home, name="home"),
    path("players/<str:player_id>/", pages.player_detail, name="player"),
    path("compare/", pages.compare, name="compare"),
    path("explore/", pages.explore_page, name="explore_page"),
    # JSON API
    path("api/status", views.status, name="api_status"),
    path("api/players", views.players, name="api_players"),
    path("api/ask", views.ask, name="api_ask"),
    path("api/explore", views.explore, name="api_explore"),
]
