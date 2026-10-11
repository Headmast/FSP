"""Validate externally supplied IDs before passing them to SQLite/Django."""
import re
from django.http import Http404

MAX_ID = 2**63 - 1


def parse_identifier(value, *, required=True):
    if value in (None, ""):
        if required:
            raise Http404("Идентификатор обязателен.")
        return None
    text = str(value)
    if not re.fullmatch(r"[0-9]{1,19}", text):
        raise Http404("Некорректный идентификатор.")
    identifier = int(text)
    if not 1 <= identifier <= MAX_ID:
        raise Http404("Некорректный идентификатор.")
    return identifier
