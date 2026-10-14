from django.urls import path
from . import views

app_name = 'tuboApp'

urlpatterns = [
    path('', views.agenda, name='tubo'),
]