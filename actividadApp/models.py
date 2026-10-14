from django.db import models

# Create your models here.

class Actividad(models.Model):

#Opciones para ENUM de estado_progreso
    OPCIONES_ESTADO_PROGRESO = [
        ('PENDIENTE', 'Pendiente'),
        ('EN_PROCESO', 'En proceso'),
        ('FINALIZADA', 'Finalizada'),
    ]

    id_actividad = models.AutoField(primary_key=True)
    fecha = models.DateTimeField(auto_now_add=True)
    solicitud_problema = models.TextField()
    accion = models.TextField()
    codigo_unico = models.CharField(max_length=100, unique=True)
    solicitante_profesional = models.ForeignKey('administracionApp.Profesional', blank=True, null=True, on_delete=models.DO_NOTHING, db_column='id_solicitante_profesional', related_name='solicitante_interno')
    solicitante_vecino = models.ForeignKey('administracionApp.Vecino', blank=True, null=True, on_delete=models.DO_NOTHING, db_column='id_solicitante_vecino')
    estado_progreso = models.CharField(max_length=20, choices=OPCIONES_ESTADO_PROGRESO, default='PENDIENTE')
    estado = models.BooleanField(default=True)
    en_tubo = models.BooleanField(default=False)
    id_profesional = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, db_column='id_funcionario')
    id_meta = models.ForeignKey('monitoreoApp.Meta', models.DO_NOTHING, db_column='id_meta')

    def __str__(self):
        return f"Actividad {self.codigo_unico} - {self.estado_progreso}"

    class Meta:
        db_table = 'actividad'
        verbose_name_plural = 'Actividades'

class Evidencia(models.Model):
    id_evidencia = models.AutoField(primary_key=True)
    archivo_vinculo = models.CharField(max_length=255)
    fecha = models.DateTimeField(auto_now_add=True)
    metadatos = models.JSONField()
    estado_revision = models.CharField(max_length=9)
    estado = models.BooleanField()
    id_actividad = models.ForeignKey('Actividad', models.DO_NOTHING, db_column='id_actividad')
    def __str__(self):
        return f"Evidencia {self.id_evidencia} ({self.estado_revision})"

    class Meta:
        db_table = 'evidencia'

class Validacion(models.Model):

#Opciones para ENUM de decision
    OPCIONES_DECISION = [
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado'),
        ('CON_OBSERVACIONES', 'Con Observaciones'),
    ]

    id_validacion = models.AutoField(primary_key=True)
    decision = models.CharField(max_length=20, choices=OPCIONES_DECISION, default='APROBADO')
    fecha = models.DateTimeField(auto_now_add=True)
    observacion = models.TextField(blank=True, null=True)
    resultado = models.CharField(max_length=100)
    version = models.IntegerField()
    estado = models.BooleanField()
    id_evidencia = models.ForeignKey('Evidencia', models.DO_NOTHING, db_column='id_evidencia')
    id_validador = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, db_column='id_validador')

    def __str__(self):
        return f"Validación {self.id_validacion} ({self.decision})"

    class Meta:
        db_table = 'validacion'
        verbose_name_plural = 'Validaciones'