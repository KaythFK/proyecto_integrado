from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator

from protocolo.base import CasoProtocolo


class CasoCP03(CasoProtocolo):
    codigo = 'CP-03'
    nombre = 'Recuperación de contraseña'

    def test_protocolo(self):
        usuario = User.objects.create_user('funcionario', password='Clave#2026')
        self.verificar('Token de recuperación vence en 5 minutos (PASSWORD_RESET_TIMEOUT = 300)', settings.PASSWORD_RESET_TIMEOUT == 300)
        token = default_token_generator.make_token(usuario)
        self.verificar('Token recién generado es válido', default_token_generator.check_token(usuario, token))
        reloj = default_token_generator._now
        default_token_generator._now = lambda: reloj() + timedelta(seconds=301)
        try:
            self.verificar('Token con más de 5 minutos es rechazado', not default_token_generator.check_token(usuario, token))
        finally:
            default_token_generator._now = reloj
        usuario.set_password('Nueva#Clave1')
        usuario.save()
        self.verificar('Token ya usado (contraseña cambiada) es rechazado', not default_token_generator.check_token(usuario, token))
        self.finalizar()


class CasoCP04(CasoProtocolo):
    codigo = 'CP-04'
    nombre = 'Contraseña almacenada con hash'

    def test_protocolo(self):
        usuario = User.objects.create_user('funcionario', password='Clave#2026')
        usuario.refresh_from_db()
        self.verificar('Contraseña guardada con hash PBKDF2, no en texto plano',
                       usuario.password.startswith('pbkdf2_sha256$') and 'Clave#2026' not in usuario.password)
        self.finalizar()
