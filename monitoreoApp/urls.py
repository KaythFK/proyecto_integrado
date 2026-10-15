from django.urls import path
from . import views

app_name = 'monitoreoApp' 

urlpatterns = [
    path('dashboard/', views.dashboard_delegado, name='dashboard_delegado'),
    path('actividades/', views.actividades_delegacion, name='actividades_delegacion'),
]