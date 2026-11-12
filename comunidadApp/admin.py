from django.contrib import admin
from .models import (
    OrganizacionComunitaria, AfiliacionVecino, CargaFamiliar, VinculoFamiliar
)

admin.site.register(OrganizacionComunitaria)
admin.site.register(AfiliacionVecino)
admin.site.register(CargaFamiliar)
admin.site.register(VinculoFamiliar)