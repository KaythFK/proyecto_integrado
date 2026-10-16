from django.urls import path
from . import views

app_name = 'monitoreoApp' 

urlpatterns = [
    path('delegado/dashboard/', views.dashboard_delegado, name='dashboard_delegado'),
    path('delegado/actividades/', views.actividades_delegacion, name='actividades_delegacion'),
]