from django.urls import path
from . import views

app_name = 'monitoreoApp' 

urlpatterns = [
    # Rutas actuales
    path('delegado/dashboard/', views.dashboard_delegado, name='dashboard_delegado'),
    path('tubo-equipo/', views.tubo_delegacion, name='tubo_delegacion'),
    
    # Rutas de Metas
    path('metas/', views.listar_metas, name='listar_metas'),
    path('metas/nueva/', views.crear_meta, name='crear_meta'),
    path('metas/editar/<int:meta_id>/', views.editar_meta, name='editar_meta'),
    path('metas/estado/<int:id_meta>/', views.cambiar_estado_meta, name='cambiar_estado_meta'),

    #Rutas de Indicadores
    path('indicadores/', views.lista_indicadores, name='lista_indicadores'),
    path('indicadores/crear/', views.crear_indicador, name='crear_indicador'),
    path('indicadores/editar/<int:id_indicador>/', views.editar_indicador, name='editar_indicador'),
    path('indicadores/estado/<int:id_indicador>/', views.cambiar_estado_indicador, name='cambiar_estado_indicador'),

    #Metas para Coordinador
    # Tablero de Metas del Coordinador
    path('metas/tablero/', views.tablero_metas_coordinador, name='tablero_metas_coordinador'),
    path('metas/<int:meta_id>/historial/', views.historial_meta, name='historial_meta'),
    path('metas/tablero/<int:id_meta>/estado/', views.cambiar_estado_meta_tablero, name='cambiar_estado_meta_tablero'),

    #Indicadores para Coordinador
    path('indicadores/tablero/', views.tablero_indicadores_coordinador, name='tablero_indicadores_coordinador'),
    path('indicadores/tablero/<int:id_indicador>/estado/', views.cambiar_estado_indicador_tablero, name='cambiar_estado_indicador_tablero'),

    path('alertas/', views.mis_alertas, name='mis_alertas'),
    path('alertas/<int:id_alerta>/revisar/', views.marcar_alerta_revisada, name='marcar_alerta_revisada'),
    path('alertas/reglas/', views.lista_reglas_alerta, name='lista_reglas_alerta'),
    path('alertas/reglas/<str:tipo>/editar/', views.editar_regla_alerta, name='editar_regla_alerta'),
]
