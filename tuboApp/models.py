from django.db import models
from datetime import date 

class Compromiso(models.Model):

    OPCIONES_ESTADO_PROGRESO= [
        ('INGRESADO', 'Ingresado'),
        ('PENDIENTE', 'Pendiente'),
        ('EN_PROCESO', 'En Proceso'),
        ('REALIZADO', 'Realizado'),
    ]

    id_compromiso = models.AutoField(primary_key=True)
    territorio = models.CharField(max_length=100)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_comprometida = models.DateField()
    fecha_termino = models.DateField(blank=True, null=True)
    apoyo = models.ForeignKey('administracionApp.CatalagoAreaApoyo', models.DO_NOTHING, db_column='id_apoyo', blank=True, null=True)
    estado = models.BooleanField(default=True)
    estado_progreso = models.CharField(max_length=20, choices=OPCIONES_ESTADO_PROGRESO, default='INGRESADO')
    id_funcionario = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, db_column='id_funcionario')
    id_actividad = models.ForeignKey('actividadApp.Actividad', models.DO_NOTHING, db_column='id_actividad')
    organizacion = models.ForeignKey('comunidadApp.OrganizacionComunitaria', models.DO_NOTHING, db_column='id_organizacion')

    def __str__(self):
        return f"Compromiso {self.id_compromiso} (Ref. Actividad: {self.id_actividad.codigo_unico})"

    class Meta:
        db_table = 'compromiso'


    @property
    def esta_vencido(self):
        if self.estado_progreso == 'REALIZADO':
            return False
        if not self.fecha_comprometida:
            return False
        return date.today() > self.fecha_comprometida

    @property
    def descripcion(self):
        return self.id_actividad.solicitud_problema

    @property
    def solicitante(self):
        return self.id_actividad.solicitante_vecino or self.id_actividad.solicitante_profesional or "No especificado"

class ObservacionCompromiso(models.Model):
    id_observacioncomp = models.AutoField(primary_key=True)
    texto = models.TextField()
    fecha = models.DateTimeField()
    id_compromiso = models.ForeignKey('Compromiso', models.DO_NOTHING, db_column='id_compromiso')

    def __str__(self):
        return f"Observación {self.id_observacioncomp}"

    class Meta:
        db_table = 'observacion_compromiso'


class HistorialEstado(models.Model):
    id_historialestado = models.AutoField(primary_key=True)
    tubo = models.ForeignKey('Compromiso', models.DO_NOTHING, db_column='id_tubo', blank=True, null=True)
    actividad = models.ForeignKey('actividadApp.Actividad', models.DO_NOTHING, db_column='id_actividad', blank=True, null=True)
    estado_anterior = models.CharField(max_length=50)
    estado_nuevo = models.CharField(max_length=50)
    fecha_cambio = models.DateTimeField(auto_now_add=True)
    motivo = models.CharField(max_length=255) 
    observacion = models.CharField(max_length=255, blank=True, null=True) 
    autor = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, db_column='id_profesional')
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f"Historial Estado {self.id_historialestado}"

    class Meta:
        db_table = 'historial_estado'
        verbose_name_plural = 'Historiales de Estado'


class HistorialIncumplimiento(models.Model):
    id_historialincump = models.AutoField(primary_key=True)
    compromiso = models.ForeignKey('Compromiso', models.DO_NOTHING, db_column='id_compromiso', blank=True, null=True)
    actividad = models.ForeignKey('actividadApp.Actividad', models.DO_NOTHING, db_column='id_actividad', blank=True, null=True)
    profesional = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, db_column='id_profesional')
    fecha_vencimiento = models.DateField() 
    dias_retraso = models.IntegerField()
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f"Incumplimiento {self.id_historialincump}"

    class Meta:
        db_table = 'historial_incumplimiento'
        verbose_name_plural = 'Historiales de Incumplimiento'
