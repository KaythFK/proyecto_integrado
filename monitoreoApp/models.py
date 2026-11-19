from django.db import models

# Create your models here.
class Indicador(models.Model):

    OPCIONES_SEMAFORO = [
        ('ROJO', 'Rojo'),
        ('AMARILLO', 'Amarillo'),
        ('VERDE', 'Verde')
    ]

    id_indicador = models.AutoField(primary_key=True)
    avance = models.DecimalField(max_digits=10, decimal_places=2)
    cumplimiento = models.DecimalField(max_digits=5, decimal_places=2)
    ponderacion = models.DecimalField(max_digits=5, decimal_places=2)
    ajuste = models.DecimalField(max_digits=5, decimal_places=2)
    semaforo = models.CharField(max_length=8, choices=OPCIONES_SEMAFORO, default='AMARILLO')
    fecha_calculo = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)
    meta_id_meta = models.ForeignKey('Meta', models.DO_NOTHING, db_column='Meta_id_meta')
    
    # NUEVO: Aquí enganchamos el progreso individual
    id_funcionario = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, db_column='id_funcionario')

    class Meta:
        db_table = 'indicador'

class Meta(models.Model):
    id_meta = models.AutoField(primary_key=True)
    valor_objetivo = models.DecimalField(max_digits=10, decimal_places=2)
    unidad = models.CharField(max_length=50)

    # La ponderación específica para este período (CA1)
    ponderador = models.DecimalField(max_digits=5, decimal_places=2)

    # 1. Arquitectura: Conectamos directo a la matriz que ya armamos
    id_cargo_item = models.ForeignKey('administracionApp.CargoItem', on_delete=models.DO_NOTHING, db_column='id_cargo_item')
    id_periodo = models.ForeignKey('administracionApp.Periodo', on_delete=models.DO_NOTHING, db_column='id_periodo')

    # 2. Vigencia propia y versionado (CA1, CA3 y KAN-208)
    fecha_inicio = models.DateField()
    fecha_termino = models.DateField(null=True, blank=True)
    version = models.IntegerField(default=1)

    # 3. Trazabilidad de autoría y creación (KAN-209)
    autor = models.ForeignKey(
        'administracionApp.Profesional',
        on_delete=models.DO_NOTHING,
        db_column='id_autor',
        related_name='metas_creadas',
        null=True,
        blank=True,
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    estado = models.BooleanField(default=True)

    class Meta:
        db_table = 'meta'

    def __str__(self):
        return f"Meta #{self.id_meta}: {self.valor_objetivo} {self.unidad}"

    
class HistorialMeta(models.Model):
    id_historial = models.AutoField(primary_key=True)
    meta = models.ForeignKey(
        'Meta',
        on_delete=models.CASCADE,
        db_column='id_meta',
        related_name='historial_versiones',
    )
    version = models.IntegerField()
    autor = models.ForeignKey(
        'administracionApp.Profesional',
        on_delete=models.DO_NOTHING,
        db_column='id_autor',
        null=True,
        blank=True,
    )
    fecha_modificacion = models.DateTimeField(auto_now_add=True)
    id_periodo = models.ForeignKey(
        'administracionApp.Periodo',
        on_delete=models.DO_NOTHING,
        db_column='id_periodo',
    )

    class Meta:
        db_table = 'historial_meta'
        ordering = ['-fecha_modificacion', '-version']


class Alerta(models.Model):
    id_alerta = models.AutoField(primary_key=True)
    motivo = models.CharField(max_length=255)
    enlace_referencia = models.CharField(max_length=255, blank=True, null=True)
    fecha = models.DateTimeField(auto_now_add=True)
    revision = models.BooleanField(default=False)
    estado = models.BooleanField(default=True)
    # Nombre para buscar: funcionario.alertas_recibidas.all()
    id_destinatario = models.ForeignKey('administracionApp.Profesional', on_delete=models.DO_NOTHING, db_column='id_destinatario', related_name='alertas_recibidas') 
    #El funcionario sobre el cual TRATA la alerta (opcional, por si la alerta es general)
    # Nombre para buscar: funcionario.alertas_generadas.all()
    id_responsable = models.ForeignKey('administracionApp.Profesional', on_delete=models.DO_NOTHING, db_column='id_responsable',blank=True, null=True,related_name='alertas_generadas')
    #La delegación involucrada (opcional, por si la alerta es a nivel de área y no de persona)
    id_delegacion = models.ForeignKey('administracionApp.Delegacion', on_delete=models.DO_NOTHING, db_column='id_delegacion', blank=True, null=True)

    def __str__(self):
        return f"Alerta {self.id_alerta} - Destinatario: {self.id_destinatario}"
    
    class Meta:
        db_table = 'alerta'
        verbose_name = 'Alerta'
        verbose_name_plural = 'Alertas'

