from django.urls import path
from . import views

app_name = 'administracionApp'

urlpatterns = [
    path('', views.main, name='main'),
    path('inicio/', views.inicio, name='inicio'),
    path('directorio_profesional/', views.directorio_profesional, name='directorio_profesional'),
    path('delegaciones/', views.delegaciones, name='delegaciones'),
]