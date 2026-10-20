from django.urls import path
from . import views

app_name = 'administracionApp'

urlpatterns = [
    path('', views.main, name='main'),
    path('dashboard_admin/', views.dashboard_admin, name='dashboard_admin'),
    path('admin-actividades/', views.lista_actividades, name='admin-actividades'),
    path('admin-actividades/crear/', views.crear_actividad, name='crear_actividad'),
    path('admin-actividades/editar/<int:id_actividad>/', views.editar_actividad, name='editar_actividad'),
    path('admin-actividades/estado/<int:id_actividad>/', views.desactivar_actividad, name='desactivar_actividad'),
    #Profesionales
    path('profesionales/', views.directorio_profesional, name='directorio_profesional'),
    path('profesionales/crear/', views.crear_profesional, name='crear_profesional'),
    path('profesionales/editar/<int:id_profesional>/', views.editar_profesional, name='editar_profesional'),
    path('profesionales/estado/<int:id_profesional>/', views.cambiar_estado_profesional, name='cambiar_estado_profesional'),
    #Delegaciones
    path('delegaciones/', views.delegaciones, name='delegaciones'),
    path('delegaciones/crear/', views.crear_delegacion, name='crear_delegacion'),
    path('delegaciones/editar/<int:id_delegacion>/', views.editar_delegacion, name='editar_delegacion'),
    path('delegaciones/estado/<int:id_delegacion>/', views.cambiar_estado_delegacion, name='cambiar_estado_delegacion'),
    #Cargos
    path('cargos/', views.lista_cargos, name='lista_cargos'),
    path('cargos/crear/', views.crear_cargo, name='crear_cargo'),
    path('cargos/editar/<int:id_cargo>/', views.editar_cargo, name='editar_cargo'),
    path('cargos/estado/<int:id_cargo>/', views.cambiar_estado_cargo, name='cambiar_estado_cargo'),
    #Catalogos
    path('catalogos/', views.panel_catalogos, name='panel_catalogos'),
    path('catalogos/gestionar/', views.gestionar_catalogo, name='gestionar_catalogo'),
    #Periodos
    path('periodos/', views.lista_periodos, name='lista_periodos'),
    path('periodos/crear/', views.crear_periodo, name='crear_periodo'),
    path('periodos/editar/<int:id_periodo>/', views.editar_periodo, name='editar_periodo'),
    path('periodos/estado/<int:id_periodo>/', views.cambiar_estado_periodo, name='cambiar_estado_periodo'),
    #Vecinos
    # --- RUTAS DE VECINOS ---
    path('vecinos/', views.lista_vecinos, name='lista_vecinos'),
    path('vecinos/crear/', views.crear_vecino, name='crear_vecino'),
    path('vecinos/editar/<int:id_vecino>/', views.editar_vecino, name='editar_vecino'),
    path('vecinos/estado/<int:id_vecino>/', views.cambiar_estado_vecino, name='cambiar_estado_vecino'),
]
