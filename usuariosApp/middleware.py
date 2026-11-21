from django.conf import settings
from django.db import DatabaseError
from django.shortcuts import redirect
from django.urls import reverse

from .models import ClaveTemporal


class CambioClaveObligatorioMiddleware:
    """Mientras el usuario tenga su contraseña temporal, cualquier página lo lleva a cambiarla."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, 'user', None)
        if usuario is not None and usuario.is_authenticated and not self._permitida(request.path):
            try:
                pendiente = ClaveTemporal.objects.filter(usuario_id=usuario.pk).exists()
            except DatabaseError:
                pendiente = False
            if pendiente:
                return redirect('usuariosApp:cambiar_clave_inicial')
        return self.get_response(request)

    @staticmethod
    def _permitida(ruta):
        libres = [reverse('usuariosApp:cambiar_clave_inicial'), reverse('usuariosApp:logout')]
        libres += ['/' + url.lstrip('/') for url in (settings.STATIC_URL, settings.MEDIA_URL) if url]
        return any(ruta.startswith(libre) for libre in libres)
