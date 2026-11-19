from django.contrib import admin

from .models import Compromiso, HistorialIncumplimiento, ObservacionCompromiso


@admin.register(Compromiso)
class CompromisoAdmin(admin.ModelAdmin):
    def get_actions(self, request):
        acciones = super().get_actions(request)
        acciones.pop('delete_selected', None)
        return acciones

    def has_delete_permission(self, request, obj=None):
        if obj is not None and (obj.esta_vencido or HistorialIncumplimiento.objects.filter(compromiso=obj).exists()):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(HistorialIncumplimiento)
class HistorialIncumplimientoAdmin(admin.ModelAdmin):
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(ObservacionCompromiso)
