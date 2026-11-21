from django.contrib import admin

from .models import ClaveTemporal


@admin.register(ClaveTemporal)
class ClaveTemporalAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'fecha_asignacion')
    search_fields = ('usuario__username',)
