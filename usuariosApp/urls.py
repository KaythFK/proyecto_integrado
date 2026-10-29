from django.urls import path
from . import views

app_name = 'usuariosApp'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('mi-perfil/', views.mi_perfil, name='mi_perfil'),
    path('recuperar-clave/', views.recuperar_clave, name='recuperar_clave'),
    path('restablecer-clave/<uidb64>/<token>/', views.restablecer_clave, name='restablecer_clave'),
]