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
    path('metas/editar/<int:id_meta>/', views.editar_meta, name='editar_meta'),
    path('metas/estado/<int:id_meta>/', views.cambiar_estado_meta, name='cambiar_estado_meta'),
]