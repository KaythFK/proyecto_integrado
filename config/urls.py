from django.contrib import admin
from django.urls import include, path, re_path
from administracionApp import views
from usuariosApp import views as vistas_usuarios
from django.conf import settings
from config.archivos_protegidos import servir_archivo

urlpatterns = [
    path('admin/', admin.site.urls),
    path('administracion/', include('administracionApp.urls')), 
    path('tubo/', include('tuboApp.urls')),
    path('actividades/', include('actividadApp.urls')),
    path('monitoreo/', include('monitoreoApp.urls')), 
    path('usuarios/', include('usuariosApp.urls')),
    path('', vistas_usuarios.landing, name='raiz'),
    path('comunidad/', include('comunidadApp.urls')),
]

urlpatterns += [
    re_path(r'^' + settings.MEDIA_URL.lstrip('/') + r'(?P<ruta>.+)$', servir_archivo, name='archivo_protegido'),
]