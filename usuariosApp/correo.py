import json
import logging
import os
import shutil
import subprocess

from django.conf import settings

logger = logging.getLogger(__name__)


def enviar_correo(destinatario, enlace):
    datos = json.dumps({
        'destinatario': destinatario,
        'enlace': enlace,
        'minutos': settings.PASSWORD_RESET_TIMEOUT // 60,
    })

    php = shutil.which('php')
    if php is None:
        # En desarrollo (sin PHP instalado) mostramos el correo en la consola
        if settings.DEBUG:
            print(f'\n[CORREO DE PRUEBA] Para: {destinatario}\nEnlace de recuperación: {enlace}\n')
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
            input=datos,
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
