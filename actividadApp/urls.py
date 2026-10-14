from django.urls import path
from . import views

app_name = 'actividadApp'

urlpatterns = [
    path('', views.lista_actividades, name='actividades'),
]