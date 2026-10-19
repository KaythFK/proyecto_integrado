from django.urls import path
from . import views

app_name = 'actividadApp'

urlpatterns = [
    path('listar/', views.listar_actividades, name='listar_actividades'),
    path('editar/<int:id_actividad>/', views.editar_actividad, name='editar_actividad'),
    path('desactivar/<str:codigo_unico>/', views.desactivar_actividad, name='desactivar_actividad'),
    path('dashboard_profesional/', views.dashboard_profesional, name='dashboard_profesional'),
    path('profesional/actividad/registrar/', views.registrar_actividad, name='registrar_actividad'),
    path('profesional/actividad/registrar/<int:actividad_id>/', views.registrar_actividad, name='registrar_actividad_con_id'),
    path('profesional/evidencia/registrar/<int:actividad_id>/', views.registrar_evidencia, name='registrar_evidencia'),
    path('profesional/tubo/actualizar/<int:id_compromiso>/', views.actualizar_estado_tubo, name='actualizar_estado_tubo'),
]