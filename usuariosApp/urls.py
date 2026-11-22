from django.urls import path
from . import views

app_name = 'usuariosApp'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('mi-perfil/', views.mi_perfil, name='mi_perfil'),
    path('cambiar-clave/', views.cambiar_clave_inicial, name='cambiar_clave_inicial'),
    path('recuperar-clave/', views.recuperar_clave, name='recuperar_clave'),
    path('restablecer-clave/<uidb64>/<token>/', views.restablecer_clave, name='restablecer_clave'),
    path('roles/', views.lista_roles, name='lista_roles'),
    path('roles/crear/', views.crear_rol, name='crear_rol'),
    path('roles/<int:id_rol>/editar/', views.editar_rol, name='editar_rol'),
    path('roles/<int:id_rol>/estado/', views.cambiar_estado_rol, name='cambiar_estado_rol'),
]