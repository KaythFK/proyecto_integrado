from django.urls import path
from . import views

app_name = 'tuboApp'

urlpatterns = [
    path('', views.agenda, name='tubo'),
    path('estado/<int:id_compromiso>/', views.actualizar_progreso_tubo, name='actualizar_progreso_tubo'),
    path('cambiar-estado/<int:id_compromiso>/', views.cambiar_estado_tubo, name='cambiar_estado_tubo'),
    path('reasignar/<int:id_compromiso>/', views.reasignar_compromiso, name='reasignar_compromiso'),
    path('dashboard/', views.dashboard_coordinador, name='dashboard_coordinador'),
    path('actividades-globales/', views.listar_todas_actividades, name='listar_todas'),
    path('detalle-actividad/<int:pk>/', views.detalle_actividad, name='detalle_actividad'),
]