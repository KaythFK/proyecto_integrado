
from django.db import models
from django.contrib.auth.models import User

import os
from datetime import date, timedelta
from django.utils import timezone
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
import json

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

    @property
    def cerrado_por_fecha(self):
        return date.today() > self.fecha_termino

    @property
    def esta_abierto(self):
        return bool(self.estado) and not self.cerrado_por_fecha

    @property
    def esta_vigente(self):
        return self.esta_abierto and self.fecha_inicio <= date.today()

    @property
    def dias_habiles_totales(self):
        return self.calcular_dias_computables(self.fecha_inicio, self.fecha_termino)

    def dias_habiles_transcurridos(self, hoy=None):
        hoy = hoy or date.today()
        if hoy < self.fecha_inicio:
            return 0
        return self.calcular_dias_computables(self.fecha_inicio, min(hoy, self.fecha_termino))

    def porcentaje_esperado(self, hoy=None):
        total = self.dias_habiles_totales
        return round(self.dias_habiles_transcurridos(hoy) / total * 100, 1) if total else 0

    @staticmethod
    def calcular_dias_computables(fecha_inicio, fecha_termino):
        if not fecha_inicio or not fecha_termino or fecha_termino < fecha_inicio:
            return 0
        dias = 0
        dia = fecha_inicio
        while dia <= fecha_termino:
            if dia.weekday() < 5:
                dias += 1
            dia += timedelta(days=1)
        return dias

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
    correo = models.CharField(unique=True, max_length=150, null=True, blank=True)
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



# --- AUDITORÍA DE INICIOS DE SESIÓN ---
@receiver(user_logged_in)
def auditar_login(sender, request, user, **kwargs):
    try:
        from .models import Auditoria, Profesional
        
        profesional_actual = Profesional.objects.filter(usuario=user).first()
        ip_cliente = request.META.get('REMOTE_ADDR', 'Desconocida')
        
        datos_sesion = {
            "ip_conexion": ip_cliente,
            "metodo": "Autenticación web",
            "descripcion_legible": f"Inicio de sesión exitoso: {user.username}"
        }
        
        Auditoria.objects.create(
            evento="LOGIN",
            entidad="AccesoSistema",
            identificador=user.pk,
            valor_anterior=None,
            valor_nuevo=datos_sesion,
            funcionario_id_funcionario=profesional_actual
        )
    except Exception as e:
        print(f"Error al auditar el inicio de sesión: {e}")

@receiver(user_logged_out)
def auditar_logout(sender, request, user, **kwargs):
    try:
        from .models import Auditoria, Profesional
        
        if user:
            profesional_actual = Profesional.objects.filter(usuario=user).first()
            
            datos_sesion = {
                "descripcion_legible": f"Cierre de sesión: {user.username}"
            }
            
            Auditoria.objects.create(
                evento="LOGOUT",
                entidad="AccesoSistema",
                identificador=user.pk,
                valor_anterior=None,
                valor_nuevo=datos_sesion,
                funcionario_id_funcionario=profesional_actual
            )
    except Exception as e:
        print(f"Error al auditar el cierre de sesión: {e}")