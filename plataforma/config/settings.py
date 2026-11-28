"""Configuração da plataforma Django da Lista Mestra."""

import os
import sys
import warnings
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _database_from_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise ImproperlyConfigured(
            "DATABASE_URL deve usar o esquema postgres:// ou postgresql://."
        )
    if not parsed.hostname or not parsed.path.strip("/"):
        raise ImproperlyConfigured(
            "DATABASE_URL precisa informar o host e o nome do banco."
        )

    options = {}
    query_options = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "sslmode" in query_options:
        options["sslmode"] = query_options.pop("sslmode")

    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(parsed.port or ""),
        "CONN_MAX_AGE": 60,
    }
    if options:
        config["OPTIONS"] = options
    if query_options:
        config.setdefault("OPTIONS", {}).update(query_options)
    return config


DEBUG = _env_bool("SCLME_DEBUG", True)
SECRET_KEY = os.environ.get("SCLME_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "Defina SCLME_SECRET_KEY quando SCLME_DEBUG estiver desativado."
        )
    SECRET_KEY = "dev-only-sclme-secret-key-change-before-deploying"
    warnings.warn(
        "SCLME_SECRET_KEY não definida; usando chave exclusiva para desenvolvimento.",
        RuntimeWarning,
        stacklevel=2,
    )

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "SCLME_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1],testserver"
    ).split(",")
    if host.strip()
]

_database_url = os.environ.get("DATABASE_URL", "").strip()
DATABASES = {
    "default": _database_from_url(_database_url)
    if _database_url
    else {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "dev.sqlite3",
    }
}

_backup_dir_configurado = os.environ.get("SCLME_BACKUP_DIR", "").strip()
SCLME_BACKUP_DIR = Path(_backup_dir_configurado).expanduser() if _backup_dir_configurado else REPO_ROOT / "backups"
if not SCLME_BACKUP_DIR.is_absolute():
    SCLME_BACKUP_DIR = REPO_ROOT / SCLME_BACKUP_DIR

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "simple_history",
    "contas.apps.ContasConfig",
    "contratos.apps.ContratosConfig",
    "documentos.apps.DocumentosConfig",
    "importacoes.apps.ImportacoesConfig",
    "painel.apps.PainelConfig",
    "registro.apps.RegistroConfig",
    "acoes.apps.AcoesConfig",
    "backups.apps.BackupsConfig",
    "grds.apps.GrdsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "painel.context_processors.contratos_do_painel",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_USER_MODEL = "contas.Usuario"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "contratos_escolher"
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
