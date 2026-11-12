from django.db import models


class OrganizacionComunitaria(models.Model):
    
    class TipoMarco(models.TextChoices):
        TERRITORIAL = 'TERRITORIAL', 'Territorial'
        FUNCIONAL = 'FUNCIONAL', 'Funcional'

    id_organizacion = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=150) 
    tipo_marco = models.CharField(max_length=50, choices=TipoMarco.choices) 
    
    # Lo dejamos como texto libre y opcional
    subtipo = models.CharField(max_length=100, blank=True, null=True) 
    
    direccion = models.CharField(max_length=200, blank=True, null=True) 
    territorio = models.CharField(max_length=45, blank=True, null=True) 
    socios_activos = models.IntegerField(default=0, blank=True, null=True)
    fecha_formacion = models.DateField(blank=True, null=True)
    fecha_inscripcion_reg_date = models.DateField(blank=True, null=True)
    n_reg_pj = models.IntegerField(blank=True, null=True)
    n_reg_dir = models.IntegerField(blank=True, null=True)
    id_delegacion = models.ForeignKey('administracionApp.Delegacion', models.DO_NOTHING, db_column='id_delegacion', blank=True, null=True) 
    organizacion_matriz = models.ForeignKey('self', models.DO_NOTHING, db_column='id_organizacion_matriz', blank=True, null=True) 
    estado = models.BooleanField(default=True)

    def __str__(self):
        return str(self.nombre)
        
class AfiliacionVecino(models.Model):
    id_afiliacion = models.AutoField(primary_key=True) 
    vecino = models.ForeignKey('administracionApp.Vecino', models.DO_NOTHING, db_column='id_vecino')
    organizacion = models.ForeignKey('OrganizacionComunitaria', models.DO_NOTHING, db_column='id_organizacion')
    cargo_organizacion = models.CharField(max_length=100)
    fecha_ingreso = models.DateField(blank=True, null=True)
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f"Afiliación: {self.vecino} - {self.organizacion}"

    class Meta:
        db_table = 'afiliacion_vecino'
        verbose_name_plural = 'Afiliaciones Vecinos'


class CargaFamiliar(models.Model):
    id_carga = models.AutoField(primary_key=True)
    rut = models.CharField(unique=True, max_length=12)
    nombres = models.CharField(max_length=100)
    apellido_paterno = models.CharField(max_length=60)
    apellido_materno = models.CharField(max_length=60, blank=True, null=True)
    fecha_nacimiento = models.DateField()
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombres} {self.apellido_paterno}"

    class Meta:
        db_table = 'carga_familiar'
        verbose_name_plural = 'Cargas Familiares'


class VinculoFamiliar(models.Model):
    id_vinculo = models.AutoField(primary_key=True)
    carga = models.ForeignKey('CargaFamiliar', models.DO_NOTHING, db_column='id_carga')
    familiar = models.ForeignKey('administracionApp.Vecino', models.DO_NOTHING, related_name='vinculos_como_familiar', db_column='id_familiar')
    parentesco = models.CharField(max_length=50)
    padres_separados = models.BooleanField(default=False) 
    vive_con_este_vecino = models.BooleanField(default=True) 
    observacion_custodia = models.CharField(max_length=255, blank=True, null=True) 
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f"Vínculo: {self.carga} ({self.parentesco})"

    class Meta:
        db_table = 'vinculo_familiar'
        verbose_name_plural = 'Vínculos Familiares'


