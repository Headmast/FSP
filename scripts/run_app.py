#!/usr/bin/env python3
"""Run Gunicorn using the same per-worktree settings as Django management commands."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from config import settings
import django
django.setup()
from profiles.privacy import reconcile
reconcile()
port = int(os.environ.get('APP_PORT', '8011'))
if not 1024 <= port <= 65535:
    raise SystemExit('APP_PORT must be between 1024 and 65535')
os.execv(sys.executable, [sys.executable, '-m', 'gunicorn', '--chdir', str(ROOT / 'app'),
    'config.wsgi:application', '--bind', f'127.0.0.1:{port}', '--workers', '1', '--threads', '4'])
