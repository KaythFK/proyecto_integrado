from django.contrib import admin
from django.core.exceptions import PermissionDenied
from .signals import registrar_intento_alteracion
from .models import (
    Profesional, Delegacion, Cargo, CargoServicio, 
    CatalagoServicio, CatalagoItem, 
    Periodo, Vecino, Auditoria, CatalagoAreaApoyo
)

# Registramos todos los modelos
admin.site.register(Profesional)
admin.site.register(Delegacion)
admin.site.register(Cargo)
admin.site.register(CatalagoServicio)
admin.site.register(CatalagoItem)
admin.site.register(Periodo)
admin.site.register(Vecino)
admin.site.register(CatalagoAreaApoyo)

@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    list_display = ('id_auditoria', 'fecha', 'evento', 'entidad', 'identificador', 'funcionario_id_funcionario')
    list_filter = ('evento', 'entidad')
    search_fields = ('evento', 'entidad')

    def get_readonly_fields(self, request, obj=None):
        return [campo.name for campo in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if request.method == 'POST':
            registrar_intento_alteracion(request.user, object_id, 'modificación')
            raise PermissionDenied('El historial de auditoría no se puede modificar.')
        return super().changeform_view(request, object_id, form_url, extra_context)

    def delete_view(self, request, object_id, extra_context=None):
        registrar_intento_alteracion(request.user, object_id, 'eliminación')
        raise PermissionDenied('El historial de auditoría no se puede eliminar.')
