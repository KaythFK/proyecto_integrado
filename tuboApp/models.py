from django.db import models

# Create your models here.
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

    def __str__(self):
        return f"Compromiso {self.id_compromiso} (Ref. Actividad: {self.id_actividad.codigo_unico})"

    class Meta:
        db_table = 'compromiso'

class ObservacionCompromiso(models.Model):
    id_observacioncomp = models.AutoField(primary_key=True)
    texto = models.TextField()
    fecha = models.DateTimeField()
    id_compromiso = models.ForeignKey('Compromiso', models.DO_NOTHING, db_column='id_compromiso')

    def __str__(self):
        return f"Observación {self.id_observacioncomp}"

    class Meta:
        db_table = 'observacion_compromiso'