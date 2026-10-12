import os
import shlex
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT = BASE_DIR.parent
original_env = set(os.environ)
env_paths = [ROOT / ".env"]
if os.environ.get("FSP_ENV_FILE"):
    env_paths.append(Path(os.environ["FSP_ENV_FILE"]))
env_paths.append(ROOT / ".env.worktree")
for path in env_paths:
    if path.is_file():
        for line in path.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if separator and key.strip() not in original_env:
                parsed = shlex.split(value.strip())
                os.environ[key.strip()] = parsed[0] if parsed else ""

DEBUG = os.environ.get("DEBUG", "1") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY required with DEBUG=0")
    SECRET_KEY = "development-only-fsp-secret-change-before-deployment"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(",")
CSRF_TRUSTED_ORIGINS = [x for x in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if x]
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
                  "django.contrib.messages", "django.contrib.staticfiles", "accounts", "profiles", "assessments", "hiring", "assistant", "api"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware",
              "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
              "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
              "django.contrib.messages.middleware.MessageMiddleware", "profiles.privacy_middleware.PrivacyGuardMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"],
              "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request",
              "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", str(ROOT / ".runtime" / "db.sqlite3")))
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = ROOT / DATABASE_PATH
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
PRIVACY_LEDGER_PATH = Path(os.environ.get('PRIVACY_LEDGER_PATH', str(DATABASE_PATH.parent / 'privacy-ledger.jsonl')))
PRIVACY_ARCHIVE_DAYS = 180
PRIVACY_BACKUP_DAYS = 7
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATABASE_PATH,
              "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE", "init_command": "PRAGMA journal_mode=WAL; PRAGMA secure_delete=ON;"}}}
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
                            {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}]
LANGUAGE_CODE = "ru"
TIME_ZONE = "Europe/Moscow"
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static", ("prototype", ROOT / "prototype")]
STATIC_ROOT = ROOT / ".runtime" / "static"
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 3600 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
X_FRAME_OPTIONS = "DENY"

LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"api_console": {"class": "logging.StreamHandler", "stream": "ext://sys.stderr"}},
           "loggers": {"fsp.api": {"handlers": ["api_console"], "level": "INFO", "propagate": False}}}
