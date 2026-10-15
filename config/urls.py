from django.contrib import admin
from django.urls import path, include
from administracionApp import views
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('inicio/', views.inicio, name='inicio'),
    path('administracion/', include('administracionApp.urls')), 
    path('tubo/', include('tuboApp.urls')),
    path('actividades/', include('actividadApp.urls')),
    path('monitoreo/', include('monitoreoApp.urls')), 
    path('usuarios/', include('usuariosApp.urls')),
    path('', RedirectView.as_view(pattern_name='login', permanent=False))
]