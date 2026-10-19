from django.urls import path
from . import views

app_name = 'tuboApp'

urlpatterns = [
    path('', views.agenda, name='tubo'),
    path('dashboard/', views.dashboard_coordinador, name='dashboard_coordinador'),
    path('actividades-globales/', views.listar_todas_actividades, name='listar_todas'),
]