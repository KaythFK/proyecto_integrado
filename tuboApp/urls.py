from django.urls import path
from . import views

app_name = 'tuboApp'

urlpatterns = [
    path('', views.agenda, name='tubo'),
    path('estado/<int:id_compromiso>/', views.actualizar_progreso_tubo, name='actualizar_progreso_tubo'),
    path('cambiar-estado/<int:id_compromiso>/', views.cambiar_estado_tubo, name='cambiar_estado_tubo'),
    path('observacion/agregar/<int:id_compromiso>/', views.agregar_observacion_tubo, name='agregar_observacion_tubo'), # <--- NUEVA RUTA
    path('dashboard/', views.dashboard_coordinador, name='dashboard_coordinador'),
    path('actividades-globales/', views.listar_todas_actividades, name='listar_todas'),
]