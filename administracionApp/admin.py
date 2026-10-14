from django.contrib import admin
from .models import (
    Profesional, Delegacion, Cargo, CargoServicio, 
    CatalagoServicio, CatalogoRoles, CatalagoItem, 
    Periodo, Vecino, Auditoria, CatalagoAreaApoyo
)

# Registramos todos los modelos
admin.site.register(Profesional)
admin.site.register(Delegacion)
admin.site.register(Cargo)
admin.site.register(CatalagoServicio)
admin.site.register(CatalogoRoles)
admin.site.register(CatalagoItem)
admin.site.register(Periodo)
admin.site.register(Vecino)
admin.site.register(Auditoria)
admin.site.register(CatalagoAreaApoyo)