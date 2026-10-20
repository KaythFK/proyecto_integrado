from django.contrib import admin
from django.urls import path, include
from administracionApp import views
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('administracion/', include('administracionApp.urls')), 
    path('tubo/', include('tuboApp.urls')),
    path('actividades/', include('actividadApp.urls')),
    path('monitoreo/', include('monitoreoApp.urls')), 
    path('usuarios/', include('usuariosApp.urls')),
    path('', RedirectView.as_view(pattern_name='usuariosApp:login'), name='raiz'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)