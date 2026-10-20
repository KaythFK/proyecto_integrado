from django.urls import path
from . import views

app_name = 'usuariosApp'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('mi-perfil/', views.mi_perfil, name='mi_perfil'),
]