import json
import logging
import os
import shutil
import subprocess

from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _ejecutar_phpmailer(datos, aviso_desarrollo):
    php = shutil.which('php')
    if php is None:
        # En desarrollo (sin PHP instalado) mostramos el correo en la consola
        if settings.DEBUG:
            print(aviso_desarrollo)
            return True
        logger.error('No se encontró PHP en el servidor; no se puede usar PHPMailer.')
        return False

    # Script PHP que usa la librería PHPMailer (se configura con PHPMAILER_SCRIPT en el .env)
    script = settings.PHPMAILER_SCRIPT
    if not os.path.isfile(script):
        logger.error('No se encontró el script de PHPMailer en: %s', script)
        return False

    try:
        resultado = subprocess.run(
            [php, script],
            cwd=os.path.dirname(script),
            input=json.dumps(datos),
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        logger.error('PHPMailer tardó demasiado en responder.')
        return False

    if resultado.returncode != 0:
        logger.error('PHPMailer falló: %s', resultado.stderr or resultado.stdout)
        return False

    return True


def enviar_correo(destinatario, enlace):
    datos = {
        'destinatario': destinatario,
        'enlace': enlace,
        'minutos': settings.PASSWORD_RESET_TIMEOUT // 60,
    }
    return _ejecutar_phpmailer(datos, f'\n[CORREO DE PRUEBA] Para: {destinatario}\nEnlace de recuperación: {enlace}\n')


def contenido_credenciales(nombre, usuario, clave_temporal, enlace_ingreso):
    contexto = {'nombre': nombre, 'usuario': usuario, 'clave_temporal': clave_temporal, 'enlace_ingreso': enlace_ingreso}
    html = render_to_string('correos/credenciales.html', contexto)
    texto = (f'Hola {nombre}. Se creó tu cuenta en el Sistema de Gestión y Registro Territorial.\n'
             f'Usuario: {usuario}\nClave temporal: {clave_temporal}\n'
             f'Ingresa en {enlace_ingreso}. Al entrar por primera vez deberás cambiar esta clave.')
    return html, texto


def enviar_credenciales(destinatario, nombre, clave_temporal, enlace_ingreso):
    html, texto = contenido_credenciales(nombre, destinatario, clave_temporal, enlace_ingreso)
    datos = {
        'destinatario': destinatario,
        'asunto': 'Tus credenciales de acceso al SGR',
        'html': html,
        'texto': texto,
    }
    return _ejecutar_phpmailer(datos, f'\n[CORREO DE PRUEBA] Para: {destinatario}\n{texto}\n')
