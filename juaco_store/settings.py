import os
import sys
from datetime import timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
# Las pruebas se ejecutan sin archivo de entorno: se les permiten los valores de
# desarrollo que un despliegue real tiene prohibidos.
RUNNING_TESTS = "test" in sys.argv


def load_env_file(path):
    """Lee un archivo de variables sin sobreescribir las que ya existen en el entorno."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


# Secretos para `manage.py runserver`. En Docker las variables llegan desde .env
# vía env_file, por lo que este archivo solo aplica al desarrollo directo.
load_env_file(BASE_DIR / ".env.local")


def env_bool(name, default=False):
    return os.getenv(name, "1" if default else "0").lower() in {"1", "true", "yes", "on"}


# Por defecto se asume producción: olvidar DJANGO_DEBUG deja el sitio en modo
# seguro en vez de publicar trazas, código fuente y el mapa de rutas.
DEBUG = env_bool("DJANGO_DEBUG", False)
IS_DEVELOPMENT = DEBUG or RUNNING_TESTS

DEV_SECRET_KEY = "dev-only-change-me"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY and IS_DEVELOPMENT:
    SECRET_KEY = DEV_SECRET_KEY
# La comprobación ya no depende de DEBUG para dispararse: sin llave propia, un
# despliegue se detiene en lugar de arrancar con la de ejemplo.
if not SECRET_KEY or (SECRET_KEY == DEV_SECRET_KEY and not IS_DEVELOPMENT):
    raise RuntimeError("DJANGO_SECRET_KEY debe configurarse en producción.")

ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "store",
]

# AxesBackend debe ir primero: bloquea el intento antes de que ModelBackend
# llegue a comprobar la contraseña real.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesBackend",
    "django.contrib.auth.backends.ModelBackend",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Al final, según recomienda django-axes: convierte el bloqueo detectado
    # arriba en una respuesta 429 con la plantilla de cuenta bloqueada.
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "juaco_store.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "store.context_processors.cart_summary",
                "store.context_processors.store_navigation",
            ],
        },
    }
]

WSGI_APPLICATION = "juaco_store.wsgi.application"
ASGI_APPLICATION = "juaco_store.asgi.application"

if os.getenv("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB"),
            "USER": os.getenv("POSTGRES_USER"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
            "HOST": os.getenv("POSTGRES_HOST", "db"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("POSTGRES_CONN_MAX_AGE", "60")),
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Bloqueo de intentos de inicio de sesión (django-axes). Se desactiva solo
# durante `manage.py test`; las pruebas del bloqueo lo reactivan explícitamente
# con override_settings para no interferir con el resto de la suite.
AXES_ENABLED = not RUNNING_TESTS
AXES_FAILURE_LIMIT = int(os.getenv("AXES_FAILURE_LIMIT", "5"))
AXES_COOLOFF_TIME = timedelta(minutes=int(os.getenv("AXES_COOLOFF_MINUTES", "15")))
# Combinación usuario+IP: bloquea solo esa cuenta desde ese origen. Bloquear
# por IP a secas dejaría fuera a cualquiera en la misma red (oficina, wifi
# compartido) apenas alguien más fallara varias veces desde ahí.
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
# Que el atacante siga insistiendo durante el bloqueo no debe extender el
# tiempo de espera indefinidamente y dejar al cliente real sin poder entrar.
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False
AXES_LOCKOUT_TEMPLATE = "store/account-locked.html"

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/assets/"
STATICFILES_DIRS = [BASE_DIR / "shome-html" / "assets"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/account-login.html"
LOGIN_REDIRECT_URL = "/account.html"
LOGOUT_REDIRECT_URL = "/"

# Recuperación de contraseña. En desarrollo el enlace se imprime en la consola;
# los despliegues usan SMTP y toman las credenciales exclusivamente del entorno.
if RUNNING_TESTS:
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
else:
    EMAIL_BACKEND = os.getenv(
        "DJANGO_EMAIL_BACKEND",
        "django.core.mail.backends.console.EmailBackend" if IS_DEVELOPMENT else "django.core.mail.backends.smtp.EmailBackend",
    )
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Nexus Luxury Footwear <no-reply@localhost>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT_SECONDS", "3600"))

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", not DEBUG)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
}

# Integración opcional de catálogo. Si no está configurada, los productos
# continúan usando la fecha de lanzamiento ingresada manualmente.
STOCKX_API_KEY = os.getenv("STOCKX_API_KEY", "")
STOCKX_CLIENT_ID = os.getenv("STOCKX_CLIENT_ID", "")
STOCKX_CLIENT_SECRET = os.getenv("STOCKX_CLIENT_SECRET", "")
STOCKX_REFRESH_TOKEN = os.getenv("STOCKX_REFRESH_TOKEN", "")
STOCKX_ACCESS_TOKEN = os.getenv("STOCKX_ACCESS_TOKEN", "")
STOCKX_TIMEOUT_SECONDS = int(os.getenv("STOCKX_TIMEOUT_SECONDS", "5"))

# Pasarela de pagos Bold (https://developers.bold.co). Sin llaves configuradas el
# método "Pago con Bold" no se ofrece en el checkout.
BOLD_IDENTITY_KEY = os.getenv("BOLD_IDENTITY_KEY", "")
BOLD_SECRET_KEY = os.getenv("BOLD_SECRET_KEY", "")
# Solo cambia el aviso visual del checkout; no afecta la validación de webhooks.
BOLD_TEST_MODE = env_bool("BOLD_TEST_MODE", False)
# El sandbox de Bold firma los webhooks con una llave vacía. Aceptar esa firma
# equivale a no validar nada: cualquiera podría marcar un pedido como pagado, así
# que vive en su propia variable y se rechaza fuera de desarrollo.
BOLD_ALLOW_UNSIGNED_WEBHOOKS = env_bool("BOLD_ALLOW_UNSIGNED_WEBHOOKS", False)
if BOLD_ALLOW_UNSIGNED_WEBHOOKS and not IS_DEVELOPMENT:
    raise RuntimeError(
        "BOLD_ALLOW_UNSIGNED_WEBHOOKS solo puede activarse con DJANGO_DEBUG=1: "
        "en producción permitiría falsificar pagos aprobados."
    )
BOLD_CURRENCY = os.getenv("BOLD_CURRENCY", "COP")
BOLD_API_BASE_URL = os.getenv("BOLD_API_BASE_URL", "https://payments.api.bold.co").rstrip("/")
BOLD_CHECKOUT_SCRIPT_URL = os.getenv("BOLD_CHECKOUT_SCRIPT_URL", "https://checkout.bold.co/library/boldPaymentButton.js")
BOLD_TIMEOUT_SECONDS = int(os.getenv("BOLD_TIMEOUT_SECONDS", "10"))
# Dominio HTTPS público (túnel o producción) para el retorno y el webhook de Bold.
BOLD_PUBLIC_BASE_URL = os.getenv("BOLD_PUBLIC_BASE_URL", "").rstrip("/")
PUBLIC_SITE_URL = os.getenv("PUBLIC_SITE_URL", BOLD_PUBLIC_BASE_URL).rstrip("/")
