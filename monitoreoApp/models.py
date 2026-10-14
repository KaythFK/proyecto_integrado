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

    def __str__(self):
        return f"Indicador {self.id_indicador} - {self.semaforo}"
    
    class Meta:
        db_table = 'indicador'
        verbose_name = 'Indicador'
        verbose_name_plural = 'Indicadores'

class Meta(models.Model):
    id_meta = models.AutoField(primary_key=True)
    valor_objetivo = models.DecimalField(max_digits=10, decimal_places=2)
    unidad = models.CharField(max_length=50)
    ponderador = models.DecimalField(max_digits=5, decimal_places=2)
    id_item = models.ForeignKey('administracionApp.CatalagoItem', models.DO_NOTHING, db_column='id_item')
    id_periodo = models.ForeignKey('administracionApp.Periodo', models.DO_NOTHING, db_column='id_periodo')
    id_cargo = models.ForeignKey('administracionApp.Cargo', models.DO_NOTHING, db_column='id_cargo')
    id_funcionario = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, db_column='id_funcionario')
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f"Meta {self.id_meta} ({self.valor_objetivo} {self.unidad})"

    class Meta:
        db_table = 'meta'


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

