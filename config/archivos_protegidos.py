from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.views.static import serve

from actividadApp.models import Evidencia, Retroalimentacion
from config.utils import validar_acceso_actividad

GLOBALES = ('Administrador', 'Coordinador')


def _es_global(user):
    return user.is_superuser or user.groups.filter(name__in=GLOBALES).exists()


def _puede_ver_evidencia(user, ruta):
    evidencia = Evidencia.objects.filter(archivo_foto=ruta).select_related('id_actividad__id_profesional').first()
    if evidencia is None:
        raise Http404('Archivo no encontrado.')
    if _es_global(user):
        return
    validar_acceso_actividad(user, evidencia.id_actividad)


def _puede_ver_respaldo(user, ruta):
    respaldos = Retroalimentacion.objects.filter(archivo_respaldo=ruta)
    if not respaldos.exists():
        raise Http404('Archivo no encontrado.')
    if _es_global(user):
        return
    profesional = getattr(user, 'profesional', None)
    if profesional is not None:
        if user.groups.filter(name='Delegado').exists() and respaldos.filter(delegacion_id=profesional.id_delegacion_id).exists():
            return
        if respaldos.filter(Q(retroalimentado=profesional) | Q(receptor=profesional)).exists():
            return
    raise PermissionDenied('No tienes permiso para ver este archivo.')


REGLAS = {
    'evidencias/': _puede_ver_evidencia,
    'retroalimentaciones/': _puede_ver_respaldo,
    'fotos_perfil/': None,
}


@login_required
def servir_archivo(request, ruta):
    """Entrega un archivo de MEDIA solo si el usuario tiene permiso sobre el registro al que pertenece."""
    ruta = ruta.replace('\\', '/').lstrip('/')
    carpeta = next((c for c in REGLAS if ruta.startswith(c)), None)
    if carpeta is None:
        raise Http404('Archivo no encontrado.')
    regla = REGLAS[carpeta]
    if regla is not None:
        regla(request.user, ruta)
    respuesta = serve(request, ruta, document_root=settings.MEDIA_ROOT)
    respuesta['Cache-Control'] = 'private, max-age=0, no-store'
    return respuesta
