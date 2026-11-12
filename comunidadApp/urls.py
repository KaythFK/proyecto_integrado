from django.urls import path
from . import views

app_name = 'comunidadApp'

urlpatterns = [
    # Organizaciones
    path('organizaciones/', views.lista_organizaciones, name='lista_organizaciones'),
    path('organizaciones/crear/', views.crear_organizacion, name='crear_organizacion'),
    path('organizaciones/editar/<int:id_organizacion>/', views.editar_organizacion, name='editar_organizacion'),
    path('organizaciones/estado/<int:id_organizacion>/', views.cambiar_estado_organizacion, name='cambiar_estado_organizacion'),

    # Afiliaciones
    path('afiliaciones/', views.lista_afiliaciones, name='lista_afiliaciones'),
    path('afiliaciones/crear/', views.crear_afiliacion, name='crear_afiliacion'),
    path('afiliaciones/editar/<int:id_afiliacion>/', views.editar_afiliacion, name='editar_afiliacion'),
    path('afiliaciones/estado/<int:id_afiliacion>/', views.cambiar_estado_afiliacion, name='cambiar_estado_afiliacion'),

    # Cargas Familiares
    path('cargas/', views.lista_cargas, name='lista_cargas'),
    path('cargas/crear/', views.crear_carga, name='crear_carga'),
    path('cargas/editar/<int:id_carga>/', views.editar_carga, name='editar_carga'),
    path('cargas/estado/<int:id_carga>/', views.cambiar_estado_carga, name='cambiar_estado_carga'),

    #Vinculos Familiares
    path('vinculos/', views.lista_vinculos, name='lista_vinculos'),
    path('vinculos/crear/', views.crear_vinculo, name='crear_vinculo'),
    path('vinculos/editar/<int:id_vinculo>/', views.editar_vinculo, name='editar_vinculo'),
    path('vinculos/estado/<int:id_vinculo>/', views.cambiar_estado_vinculo, name='cambiar_estado_vinculo'),
]