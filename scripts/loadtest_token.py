"""Emit un JWT access pour k6 (stdout) — sans ecriture OutstandingToken."""
from __future__ import annotations

import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pinova_backend.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.contrib.auth.models import User  # noqa: E402
from rest_framework_simplejwt.tokens import AccessToken  # noqa: E402

username = os.environ.get('LOADTEST_USER', 'loadtest')
user = User.objects.get(username=username)
print(str(AccessToken.for_user(user)))
