
from django.db import models
from django.contrib.auth.models import User

import os
from django.utils import timezone

# Create your models here.
class Profesional(models.Model):
    id_profesional = models.AutoField(primary_key=True)
    rut = models.CharField(unique=True, max_length=12)
    nombres = models.CharField(max_length=100)
    apellido_paterno = models.CharField(max_length=60)
    apellido_materno = models.CharField(max_length=60, blank=True, null=True)
    estado = models.BooleanField(default=True)
    telefono = models.CharField(max_length=45, blank=True, null=True)
    correo = models.CharField(unique=True, max_length=150)
    id_cargo = models.ForeignKey('Cargo', models.DO_NOTHING, db_column='id_cargo')
    id_delegacion = models.ForeignKey('Delegacion', models.DO_NOTHING, db_column='id_delegacion')
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.nombres} {self.apellido_paterno}"
    class Meta:
        db_table = 'profesional'
        verbose_name_plural = 'Profesionales'

class Delegacion(models.Model):
    id_delegacion = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=55)
    estado = models.BooleanField(default=True)
    responsable = models.ForeignKey('Profesional', models.DO_NOTHING, db_column='responsable', blank=True, null=True)
    territorio = models.CharField(max_length=45)
    calle = models.CharField(max_length=60, blank=True, null=True)
    numero_calle = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return str(self.nombre)

    class Meta:
        db_table = 'delegacion'
        verbose_name_plural = 'Delegaciones'


class Cargo(models.Model):
    id_cargo = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=45, blank=True, null=True)
    vigencia = models.IntegerField(blank=True, null=True)
    estado = models.BooleanField(default=True)

    def __str__(self):
        return str(self.nombre)

    class Meta:
        db_table = 'cargo'


class CargoServicio(models.Model):
    pk = models.CompositePrimaryKey('id_servicios', 'id_cargo')
    id_servicios = models.ForeignKey('CatalagoServicio', models.DO_NOTHING, db_column='id_servicios')
    id_cargo = models.ForeignKey('Cargo', models.DO_NOTHING, db_column='id_cargo')
    estado = models.BooleanField(default=True)
    class Meta:
        db_table = 'cargo_servicio'





class CatalagoServicio(models.Model):
    id_servicios = models.AutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=45)
    estado = models.BooleanField(default=True)
    def __str__(self):
        return str(self.nombre)

    class Meta:
        db_table = 'catalago_servicio'
        verbose_name_plural = 'Catalogo Servicios'


class CatalogoRoles(models.Model):
    id_roles = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=80)
    estado = models.BooleanField(default=True)

    def __str__(self):
        return str(self.nombre)
    
    class Meta:
        db_table = 'catalogo_roles'
        verbose_name_plural = 'Catalogo Roles'


class CatalagoItem(models.Model):
    id_item = models.AutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=45)
    estado = models.BooleanField(default=True)

    def __str__(self):
        return str(self.nombre)

    class Meta:
        db_table = 'catalago_item'
        verbose_name_plural = 'Catalogo Items'

class Periodo(models.Model):
    id_periodo = models.AutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=50)
    fecha_inicio = models.DateField()
    fecha_termino = models.DateField()
    dias_computables = models.IntegerField()
    estado = models.BooleanField(default=True)
    umbral_regular = models.DecimalField(max_digits=5, decimal_places=2)
    umbral_exelencia = models.DecimalField(max_digits=5, decimal_places=2)
    version_parametros = models.IntegerField()

    def __str__(self):
        return str(self.nombre)

    class Meta:
        db_table = 'periodo'

class Vecino(models.Model):
    id_vecino = models.AutoField(primary_key=True)
    rut = models.CharField(unique=True, max_length=12)
    nombres = models.CharField(max_length=150)
    apellido_paterno = models.CharField(max_length=60)
    apellido_materno = models.CharField(max_length=60, blank=True, null=True)
    telefono = models.CharField(max_length=45, blank=True, null=True)
    correo = models.CharField(unique=True, max_length=150)
    estado = models.BooleanField(default=True)


    def __str__(self):
        return f"{self.nombres} {self.apellido_paterno}"
    class Meta:
        db_table = 'vecino'
        verbose_name_plural = 'Vecinos'

class Auditoria(models.Model):
    id_auditoria = models.BigAutoField(primary_key=True)
    evento = models.CharField(max_length=150)
    fecha = models.DateTimeField(auto_now_add=True)
    entidad = models.CharField(max_length=100)
    identificador = models.IntegerField()
    valor_anterior = models.JSONField(blank=True, null=True)
    valor_nuevo = models.JSONField(blank=True, null=True)
    funcionario_id_funcionario = models.ForeignKey('Profesional', models.DO_NOTHING, db_column='Funcionario_id_funcionario')  # Field name made lowercase.

    def __str__(self):
        return f"Auditoría {self.id_auditoria} - {self.evento}"
    
    class Meta:
        db_table = 'auditoria'

class CatalagoAreaApoyo(models.Model):
    id_area_apoyo = models.AutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=45)
    estado = models.BooleanField(default=True)

    def __str__(self):
        return str(self.nombre)

    class Meta:
        db_table = 'catalago_area_apoyo'
        verbose_name_plural = 'Catalogo Area Apoyo'


def generarNombreFoto(instance, filename):
    extension = os.path.splitext(filename)[1][1:]
    ruta = 'fotos_perfil'
    fecha = timezone.now().strftime("%d%m%Y_%H%M%S")
    return os.path.join(ruta, f"{fecha}.{extension}")

# Creamos una tablita exclusiva para las fotos de todos los usuarios
class FotoPerfil(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='foto_perfil')
    foto = models.ImageField(upload_to=generarNombreFoto, null=True, default='fotos_perfil/default.png')

    class Meta:
        db_table = 'administracionapp_fotoperfil'