from django.urls import path
from . import views

app_name = 'actividadApp'

urlpatterns = [
    path('listar/', views.listar_actividades, name='listar_actividades'),
    path('editar/<int:id_actividad>/', views.editar_actividad, name='editar_actividad'),
    path('desactivar/<str:codigo_unico>/', views.desactivar_actividad, name='desactivar_actividad'),
    path('dashboard_profesional/', views.dashboard_profesional, name='dashboard_profesional'),
    path('profesional/actividad/registrar/', views.registrar_actividad, name='registrar_actividad'),
    path('actualizar-progreso-actividad/<int:id_actividad>/', views.actualizar_progreso_actividad, name='actualizar_progreso_actividad'),
    path('profesional/actividad/registrar/<int:actividad_id>/', views.registrar_actividad, name='registrar_actividad_con_id'),
    path('profesional/evidencia/registrar/<int:actividad_id>/', views.registrar_evidencia, name='registrar_evidencia'),
    path('profesional/tubo/actualizar/<int:id_compromiso>/', views.actualizar_estado_tubo, name='actualizar_estado_tubo'),
    # --- RUTAS DEL DELEGADO PARA ACTIVIDADES ---
    path('delegado/lista/', views.actividades_delegacion, name='actividades_delegacion'),
    path('delegado/registrar/', views.registrar_actividad_delegado, name='registrar_actividad_delegado'),
    path('delegado/editar/<int:id_actividad>/', views.editar_actividad_delegado, name='editar_actividad_delegado'),
    path('delegado/estado/<int:id_actividad>/', views.cambiar_estado_actividad_delegado, name='cambiar_estado_actividad_delegado'),
    #Ausencias
    path('ausencias/', views.lista_ausencias, name='lista_ausencias'),
    path('ausencias/crear/', views.crear_ausencia, name='crear_ausencia'),
    path('ausencias/editar/<int:id_ausencia>/', views.editar_ausencia, name='editar_ausencia'),
    path('ausencias/estado/<int:id_ausencia>/', views.cambiar_estado_ausencia, name='cambiar_estado_ausencia'),
    #Retroalimentaciones
    path('retroalimentaciones/', views.lista_retroalimentaciones, name='lista_retroalimentaciones'),
    path('retroalimentaciones/crear/', views.crear_retroalimentacion, name='crear_retroalimentacion'),
    path('retroalimentaciones/editar/<int:id_retroalimentacion>/', views.editar_retroalimentacion, name='editar_retroalimentacion'),
    path('retroalimentaciones/estado/<int:id_retroalimentacion>/', views.cambiar_estado_retroalimentacion, name='cambiar_estado_retroalimentacion'),
    #Evidencias
    path('evidencias/', views.lista_evidencias, name='lista_evidencias'),
    path('evidencias/crear/', views.crear_evidencia, name='crear_evidencia'),
    path('evidencias/editar/<int:id_evidencia>/', views.editar_evidencia, name='editar_evidencia'),
    path('evidencias/estado/<int:id_evidencia>/', views.cambiar_estado_evidencia, name='cambiar_estado_evidencia'),
    #Validaciones
    path('validaciones/', views.lista_validaciones, name='lista_validaciones'),
    path('validaciones/crear/', views.crear_validacion, name='crear_validacion'),
    path('validaciones/editar/<int:id_validacion>/', views.editar_validacion, name='editar_validacion'),
    path('validaciones/estado/<int:id_validacion>/', views.cambiar_estado_validacion, name='cambiar_estado_validacion'),
    path('actividad/<int:id_actividad>/gestiones/', views.lista_gestiones, name='lista_gestiones'),
    
    # Crear una nueva gestión para una actividad
    path('actividad/<int:id_actividad>/gestiones/crear/', views.crear_gestion, name='crear_gestion'),
    
    # Editar una gestión existente (recibe el ID de la gestión)
    path('gestion/<int:id_gestion>/editar/', views.editar_gestion, name='editar_gestion'),
    
    # Cambiar estado (Activar/Desactivar) de una gestión
    path('gestion/<int:id_gestion>/cambiar_estado/', views.cambiar_estado_gestion, name='cambiar_estado_gestion'),
    path('gestiones/todas/', views.lista_todas_gestiones, name='lista_todas_gestiones'),

    # Gestiones registradas por el profesional que inició sesión
    path('gestiones/mis-gestiones/', views.mis_gestiones, name='mis_gestiones'),

]