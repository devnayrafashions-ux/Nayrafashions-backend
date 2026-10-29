import os
from pathlib import Path
from datetime import timedelta
import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-me')
DEBUG = os.getenv('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '.onrender.com',
    'backend.nayrafashions.com',
    'www.backend.nayrafashions.com',
    'www.nayrafashions.com',
    'nayrafashions.com',
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',  # ADDED — needed for BLACKLIST_AFTER_ROTATION / logout
    'corsheaders',
    'cloudinary',
    'cloudinary_storage',
    'django_filters',
    # Your apps
    'users',
    'store',
    'orders',
    'payments',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',   # Must be first
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Database: use SQLite locally when `USE_SQLITE` is true, otherwise PostgreSQL
DATABASE_URL = os.getenv('DATABASE_URL')
USE_SQLITE = os.getenv('USE_SQLITE', 'False') == 'True'

if USE_SQLITE or not DATABASE_URL:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600
        )
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static & Media
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Cloudinary for images
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom user model
AUTH_USER_MODEL = 'users.CustomUser'

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'users.authentication.CookieJWTAuthentication',  # CHANGED — reads JWT from httpOnly cookie
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 12,
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,          # ADDED — invalidates old refresh token on rotation
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_COOKIE_ACCESS': 'access_token',      # ADDED — cookie name for access token
    'AUTH_COOKIE_REFRESH': 'refresh_token',    # ADDED — cookie name for refresh token
}

# ─── Cookie / CSRF settings ────────────────────────────────
# Required for httpOnly-cookie JWT auth. 'None' is needed (not 'Lax')
# because your frontend and backend are on different subdomains and
# browsers treat them as cross-site. SameSite=None cookies must also
# be Secure, which is true in production since your domain is served
# over HTTPS.
COOKIE_SECURE = not DEBUG
COOKIE_SAMESITE = 'None' if not DEBUG else 'Lax'

CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = COOKIE_SAMESITE
CSRF_COOKIE_HTTPONLY = False   # frontend JS must be able to read this one to echo it back
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = COOKIE_SAMESITE

CSRF_TRUSTED_ORIGINS = [
    'https://www.nayrafashions.com',
    'https://nayrafashions.com',
    'https://backend.nayrafashions.com',
]

# CORS — allow React frontend
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'https://www.nayrafashions.com',
    'https://nayrafashions.com',
]
CORS_ALLOW_CREDENTIALS = True

# Razorpay
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET')
RAZORPAY_WEBHOOK_SECRET = os.getenv('RAZORPAY_WEBHOOK_SECRET', '')

# ─── Email (shipment notifications) ────────────────────────────────
# NEW: SMTP config for sending order status emails (e.g. "Your order has
# shipped" with tracking info). Uses Gmail SMTP by default — to set this
# up:
#   1. Use a Gmail account (or any SMTP-compatible provider).
#   2. If using Gmail, enable 2-Step Verification on that account, then
#      generate an "App Password" at https://myaccount.google.com/apppasswords
#      (a regular Gmail password will NOT work here).
#   3. Add these to your .env file:
#        EMAIL_HOST_USER=youraddress@gmail.com
#        EMAIL_HOST_PASSWORD=your16charapppassword
#        DEFAULT_FROM_EMAIL=Nayra Fashions <youraddress@gmail.com>
# In DEBUG mode with no credentials set, emails are printed to the
# console instead of actually sending, so local dev doesn't break.
if DEBUG and not os.getenv('EMAIL_HOST_USER'):
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)
EMAIL_TIMEOUT = 10