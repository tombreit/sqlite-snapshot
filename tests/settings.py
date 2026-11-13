"""Minimal Django settings for the contrib.django tests.

The default database is in memory; tests that need a file point its NAME at
one (see test_django.py).
"""

SECRET_KEY = "not-secret"
INSTALLED_APPS = ["sqlite_snapshot.contrib.django"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
USE_TZ = True
