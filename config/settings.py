from pathlib import Path
import os
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def lista_env(nombre, por_defecto=''):
    return [valor.strip() for valor in os.getenv(nombre, por_defecto).split(',') if valor.strip()]


# Seguridad: los valores reales van en el archivo .env de cada entorno (ver .env.example).
DEBUG = os.getenv('DEBUG', 'False').strip().lower() in ('1', 'true', 'si', 'sí', 'yes')

SECRET_KEY = os.getenv('SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('Falta SECRET_KEY en el archivo .env (obligatoria con DEBUG=False).')
    from django.core.management.utils import get_random_secret_key
    SECRET_KEY = get_random_secret_key()

ALLOWED_HOSTS = lista_env('ALLOWED_HOSTS', 'localhost,127.0.0.1' if DEBUG else '')
CSRF_TRUSTED_ORIGINS = lista_env('CSRF_TRUSTED_ORIGINS')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'administracionApp',
    'actividadApp',
    'monitoreoApp',
    'tuboApp',
    'usuariosApp',
    'comunidadApp',
    'django_filters',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'config.usuario_actual.UsuarioActualMiddleware',
    'usuariosApp.middleware.CambioClaveObligatorioMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'config.utils.rol_usuario',
                'config.menu.menu_lateral',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE'),
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''), 
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
    }
}

if 'mysql' in (DATABASES['default']['ENGINE'] or ''):
    DATABASES['default']['OPTIONS'] = {
        'init_command': "SET default_storage_engine=INNODB, sql_mode='STRICT_TRANS_TABLES'",
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'es-cl'

TIME_ZONE = 'America/Santiago'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Indica a @login_required a qué ruta enviar a los usuarios no autenticados
LOGIN_URL = 'usuariosApp:login'

# URL por defecto a la que redirigir si no hay un parámetro 'next'
LOGIN_REDIRECT_URL = 'inicio'


PASSWORD_RESET_TIMEOUT = 60 * 5


PHPMAILER_SCRIPT = os.getenv('PHPMAILER_SCRIPT', '')


# Protecciones de producción: solo con DEBUG=False. USAR_HTTPS=False permite probar en el servidor
# antes de tener certificado; con HTTPS activo las cookies viajan solo cifradas.
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'
if not DEBUG and os.getenv('USAR_HTTPS', 'True').strip().lower() in ('1', 'true', 'si', 'sí', 'yes'):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000'))

# HSTS no se extiende a otros subdominios municipales ni se inscribe en la lista de precarga de los navegadores.
SILENCED_SYSTEM_CHECKS = ['security.W005', 'security.W021']
