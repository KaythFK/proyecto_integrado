from django.conf import settings
from django.contrib.auth.models import Group
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


PERFILES_BASE = ['Administrador', 'Coordinador', 'Delegado', 'Profesional']
DESCRIPCION_PERFIL = {
    'Administrador': 'Configura el sistema: usuarios, roles, delegaciones, cargos, catálogos, períodos, reglas de alerta y auditoría.',
    'Coordinador': 'Supervisa la gestión de todas las delegaciones: metas, indicadores, tendencias e informes.',
    'Delegado': 'Acompaña a su equipo: revisa evidencias, compromisos, metas y ausencias de su delegación.',
    'Profesional': 'Registra su trabajo en terreno: actividades, gestiones, evidencias y compromisos.',
}


class RolSistema(models.Model):
    """
    Rol de acceso. Cada rol hereda los permisos de un perfil base; los cuatro perfiles base son roles fijos
    del sistema. Un usuario con un rol creado por el Administrador queda también en el grupo de su perfil base.
    """
    OPCIONES_PERFIL = [(perfil, perfil) for perfil in PERFILES_BASE]

    grupo = models.OneToOneField(Group, on_delete=models.CASCADE, related_name='rol_sistema')
    perfil_base = models.CharField(max_length=20, choices=OPCIONES_PERFIL)
    descripcion = models.CharField(max_length=255)
    es_base = models.BooleanField(default=False)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = 'rol_sistema'
        verbose_name = 'Rol del sistema'
        verbose_name_plural = 'Roles del sistema'

    def __str__(self):
        return self.grupo.name

    @property
    def nombre(self):
        return self.grupo.name


def asegurar_roles_base():
    """Registra los cuatro perfiles base como roles fijos si todavía no existen."""
    for perfil in PERFILES_BASE:
        grupo, _ = Group.objects.get_or_create(name=perfil)
        RolSistema.objects.get_or_create(grupo=grupo, defaults={
            'perfil_base': perfil, 'descripcion': DESCRIPCION_PERFIL[perfil], 'es_base': True, 'estado': True})


def asignar_rol(usuario, grupo):
    """Deja al usuario solo con el rol indicado y, si no es un perfil base, también con el grupo de su perfil base."""
    grupos = [grupo]
    rol = RolSistema.objects.filter(grupo=grupo).first()
    if rol and not rol.es_base:
        grupos.append(Group.objects.get_or_create(name=rol.perfil_base)[0])
    usuario.groups.set(grupos)


def rol_principal(usuario):
    """El rol que se muestra del usuario: el creado por el Administrador si tiene uno, si no su perfil base."""
    grupos = list(usuario.groups.all())
    propios = [g for g in grupos if g.name not in PERFILES_BASE]
    return (propios or grupos or [None])[0]
