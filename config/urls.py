from django.contrib import admin
from django.urls import path, include
from administracionApp import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('inicio/', views.inicio, name='inicio'),
    path('', views.main, name='main'),
    path('administracion/', include('administracionApp.urls')), 
    path('tubo/', include('tuboApp.urls')),
    path('actividades/', include('actividadApp.urls')),
    path('monitoreo/', include('monitoreoApp.urls')), 
]

