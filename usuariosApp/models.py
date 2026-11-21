from django.conf import settings
from django.db import models


class ClaveTemporal(models.Model):
    """Marca a los usuarios que siguen con la contraseña temporal entregada al crear su cuenta."""
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='clave_temporal')
    fecha_asignacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'clave_temporal'
        verbose_name = 'Clave temporal pendiente'
        verbose_name_plural = 'Claves temporales pendientes'

    def __str__(self):
        return f'{self.usuario.get_username()} debe cambiar su contraseña'
