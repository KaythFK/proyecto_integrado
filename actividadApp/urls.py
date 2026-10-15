from django.urls import path
from . import views

urlpatterns = [
    path('', views.listar_actividades, name='listar_actividades'),
    path('crear/', views.crear_actividad, name='crear_actividad'),
    path('editar/<int:id_actividad>/', views.editar_actividad, name='editar_actividad'),
    path('desactivar/<int:id_actividad>/', views.desactivar_actividad, name='desactivar_actividad'),
]