#!/usr/bin/env python
# Django 관리 명령 — 실행: python web/manage.py runserver
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
