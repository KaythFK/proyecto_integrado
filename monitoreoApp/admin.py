from django.contrib import admin
from .models import Indicador, Meta, Alerta

# Registramos los modelos para que aparezcan en el panel de Django
admin.site.register(Indicador)
admin.site.register(Meta)
admin.site.register(Alerta)