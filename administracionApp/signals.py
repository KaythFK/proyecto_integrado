from django.core.exceptions import PermissionDenied
from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver

from config.usuario_actual import usuario_actual
from .models import Auditoria, Profesional

EVENTO_INTENTO = 'INTENTO_ALTERACION'


def registrar_intento_alteracion(usuario, registro_id, accion):
    """Deja constancia de quién intentó modificar o eliminar un registro de auditoría."""
    if usuario is None or not getattr(usuario, 'is_authenticated', False):
        return False
    profesional = Profesional.objects.filter(usuario=usuario).first()
    if profesional is None:
        return False
    Auditoria.objects.create(
        evento=EVENTO_INTENTO,
        entidad='Auditoria',
        identificador=registro_id or 0,
        valor_anterior=None,
        valor_nuevo={'accion': accion, 'usuario': usuario.get_username(),
                     'descripcion_legible': f'Intento de {accion} del registro de auditoría #{registro_id}'},
        funcionario_id_funcionario=profesional,
    )
    return True


@receiver(pre_save, sender=Auditoria)
def impedir_modificacion(sender, instance, **kwargs):
    if instance.pk and Auditoria.objects.filter(pk=instance.pk).exists():
        registrar_intento_alteracion(usuario_actual(), instance.pk, 'modificación')
        raise PermissionDenied('El historial de auditoría no se puede modificar.')


@receiver(pre_delete, sender=Auditoria)
def impedir_eliminacion(sender, instance, **kwargs):
    registrar_intento_alteracion(usuario_actual(), instance.pk, 'eliminación')
    raise PermissionDenied('El historial de auditoría no se puede eliminar.')
