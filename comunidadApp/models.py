
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class OrganizacionComunitaria(models.Model):

    SIN_DATO_TEXTO = 'SIN DATOS'

    class TipoOrganizacion(models.TextChoices):
        TERRITORIAL = 'TERRITORIAL', 'Territorial'
        FUNCIONAL = 'FUNCIONAL', 'Funcional'

    class SubtipoOrganizacion(models.TextChoices):
        JUNTA_VECINOS = 'JUNTA_VECINOS', 'Junta de Vecinos'
        UNION_COMUNAL = 'UNION_COMUNAL', 'Unión Comunal'
        CLUB_DEPORTIVO = 'CLUB_DEPORTIVO', 'Club Deportivo y Recreativo'
        ADULTO_MAYOR = 'ADULTO_MAYOR', 'Agrupación de Adulto Mayor'
        CENTRO_MADRES = 'CENTRO_MADRES', 'Centro de Madres y Vecinales'
        CULTURAL = 'CULTURAL', 'Agrupación Cultural o Artística'
        JUVENIL = 'JUVENIL', 'Agrupación Juvenil'
        COMITE_SEGURIDAD = 'COMITE_SEGURIDAD', 'Comité de Seguridad'
        COMITE_ALLEGADOS = 'COMITE_ALLEGADOS', 'Comité de Allegados'
        COMITE_VIVIENDA = 'COMITE_VIVIENDA', 'Comité de Vivienda'
        OTRO = 'OTRO', 'Otro Subtipo'

    id_organizacion = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=150, default=SIN_DATO_TEXTO)

    tipo = models.CharField(
        max_length=50,
        choices=TipoOrganizacion.choices,
        default=TipoOrganizacion.TERRITORIAL
    )

    subtipo = models.CharField(
        max_length=100,
        choices=SubtipoOrganizacion.choices,
        default=SubtipoOrganizacion.JUNTA_VECINOS
    )

    direccion = models.CharField(max_length=200, default=SIN_DATO_TEXTO)
    territorio = models.CharField(max_length=45, default=SIN_DATO_TEXTO)
    socios_activos = models.IntegerField(default=0)
    fecha_formacion = models.DateField(blank=True, null=True)
    fecha_inscripcion_reg_date = models.DateField(blank=True, null=True)
    n_reg_pj = models.CharField(max_length=50, default=SIN_DATO_TEXTO)
    n_reg_dir = models.CharField(max_length=50, default=SIN_DATO_TEXTO)

    id_delegacion = models.ForeignKey(
        'administracionApp.Delegacion',
        models.DO_NOTHING,
        db_column='id_delegacion',
        blank=True,
        null=True
    )
    # Único campo opcional real: un comité puede o no depender de una JJ.VV. matriz (CA2 / KAN-342)
    organizacion_matriz = models.ForeignKey(
        'self',
        models.DO_NOTHING,
        db_column='id_organizacion_matriz',
        blank=True,
        null=True
    )
    estado = models.BooleanField(default=True)

    def __str__(self):
        return str(self.nombre)

    def campos_sin_datos(self):
        """Retorna las etiquetas de campos que siguen en 'SIN DATOS' o sin completar."""
        faltantes = []
        campos_texto = [
            ('nombre', 'Nombre de la Organización'),
            ('direccion', 'Domicilio'),
            ('territorio', 'Territorio'),
            ('n_reg_pj', 'N° Registro Personalidad Jurídica'),
            ('n_reg_dir', 'N° Registro Directorio'),
        ]
        for attr, etiqueta in campos_texto:
            valor = (getattr(self, attr, '') or '').strip().upper()
            if not valor or valor in ('SIN DATOS', 'S/INF.', 'S/INF', 'SIN INF.'):
                faltantes.append(etiqueta)

        if self.fecha_formacion is None:
            faltantes.append('Fecha de Formación')
        if self.fecha_inscripcion_reg_date is None:
            faltantes.append('Fecha de Inscripción Registro')
        if self.id_delegacion_id is None:
            faltantes.append('Delegación Municipal')

        return faltantes

    @property
    def tiene_datos_incompletos(self):
        return bool(self.campos_sin_datos())
        
        
class AfiliacionVecino(models.Model):
    id_afiliacion = models.AutoField(primary_key=True)
    vecino = models.ForeignKey('administracionApp.Vecino', models.DO_NOTHING, db_column='id_vecino')
    organizacion = models.ForeignKey('OrganizacionComunitaria', models.DO_NOTHING, db_column='id_organizacion')
    cargo_organizacion = models.CharField(max_length=100)
    fecha_ingreso = models.DateField(blank=True, null=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = 'afiliacion_vecino'
        verbose_name_plural = 'Afiliaciones Vecinos'
        constraints = [
            models.UniqueConstraint(
                fields=['vecino', 'organizacion'],
                condition=Q(estado=True),
                name='uq_afiliacion_vecino_org_activa',
            )
        ]

    def __str__(self):
        return f"Afiliación: {self.vecino} - {self.organizacion}"

    def clean(self):
        super().clean()
        if self.organizacion_id and not self.organizacion.estado:
            raise ValidationError({
                'organizacion': 'No se puede afiliar a una organización comunitaria inactiva.'
            })

        # CA2: Si la organización es funcional, se omite cualquier restricción
        # de coincidencia territorial con el vecino.
        if self.organizacion_id and self.organizacion.tipo == OrganizacionComunitaria.TipoOrganizacion.FUNCIONAL:
            return

class CargaFamiliar(models.Model):
    id_carga = models.AutoField(primary_key=True)
    rut = models.CharField(unique=True, max_length=12)
    nombres = models.CharField(max_length=100)
    apellido_paterno = models.CharField(max_length=60)
    apellido_materno = models.CharField(max_length=60, blank=True, null=True)
    fecha_nacimiento = models.DateField()
    genero = models.CharField(max_length=10, choices=[('M', 'Masculino'), ('F', 'Femenino'), ('O', 'Otro')])
    padres_separados = models.BooleanField(default=False)
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombres} {self.apellido_paterno}"

    class Meta:
        db_table = 'carga_familiar'
        verbose_name_plural = 'Cargas Familiares'


class VinculoFamiliar(models.Model):
    id_vinculo = models.AutoField(primary_key=True)
    carga = models.ForeignKey('CargaFamiliar', models.DO_NOTHING, db_column='id_carga', related_name='vinculos')
    familiar = models.ForeignKey('administracionApp.Vecino', models.DO_NOTHING, related_name='vinculos_como_familiar', db_column='id_familiar')
    parentesco = models.CharField(max_length=50)
    vive_con_este_vecino = models.BooleanField(default=True)
    observacion_custodia = models.CharField(max_length=255, blank=True, null=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = 'vinculo_familiar'
        verbose_name_plural = 'Vínculos Familiares'
        constraints = [
            models.UniqueConstraint(
                fields=['familiar', 'carga'],
                condition=Q(estado=True),
                name='uq_vinculo_familiar_carga_activo',
            )
        ]

    def __str__(self):
        return f"Vínculo: {self.carga} ({self.parentesco})"

    def clean(self):
        super().clean()
        if self.carga_id and not self.carga.estado:
            raise ValidationError({
                'carga': 'No se puede vincular una carga familiar inactiva.'
            })
        if self.familiar_id and not self.familiar.estado:
            raise ValidationError({
                'familiar': 'No se puede vincular a un vecino inactivo.'
            })

# ==========================================
# MÓDULOS DE CELEBRACIONES Y EVENTOS MASIVOS
# ==========================================

class CatalogoCelebracion(models.Model):
    id_catcel = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, unique=True)
    estado = models.BooleanField(default=True)

    def __str__(self):
        return str(self.nombre)
        
    class Meta:
        db_table = 'catalogo_celebracion'
        verbose_name_plural = 'Catálogo de Celebraciones'


class Celebracion(models.Model):
    id_celebracion = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=200) 
    tipo = models.ForeignKey('CatalogoCelebracion', on_delete=models.DO_NOTHING, db_column='id_catalogo')
    descripcion = models.TextField(blank=True, null=True)
    fecha_tentativa = models.DateField()
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} ({self.tipo.nombre})"
    
    class Meta:
        db_table = 'celebracion_global'
        verbose_name_plural = 'Celebraciones Globales'


class CelebracionDelegacion(models.Model):
    id_cel_delegacion = models.AutoField(primary_key=True)
    celebracion = models.ForeignKey('Celebracion', on_delete=models.CASCADE, db_column='id_celebracion')
    delegacion = models.ForeignKey('administracionApp.Delegacion', on_delete=models.DO_NOTHING, db_column='id_delegacion')
    
    activa = models.BooleanField(default=False) 
    fecha_ejecucion = models.DateField(blank=True, null=True) 
    lugar = models.CharField(max_length=200, blank=True, null=True)
    
    def __str__(self):
        return f"{self.delegacion} - {self.celebracion.nombre}"
        
    class Meta:
        db_table = 'celebracion_delegacion'
        verbose_name_plural = 'Celebraciones por Delegación'
        constraints = [
            models.UniqueConstraint(
                fields=['celebracion', 'delegacion'],
                name='uq_celebracion_delegacion',
            )
        ]


class BeneficiarioCelebracion(models.Model):
    id_beneficiario_cel = models.AutoField(primary_key=True)
    celebracion_delegacion = models.ForeignKey('CelebracionDelegacion', on_delete=models.CASCADE, db_column='id_cel_delegacion')
    
    vecino = models.ForeignKey('administracionApp.Vecino', on_delete=models.DO_NOTHING, db_column='id_vecino', blank=True, null=True)
    carga_familiar = models.ForeignKey('CargaFamiliar', on_delete=models.DO_NOTHING, db_column='id_carga', blank=True, null=True)
    
    beneficio_entregado = models.BooleanField(default=False) 
    fecha_entrega = models.DateTimeField(blank=True, null=True) 
    observacion = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        if self.carga_familiar:
            return f"Carga: {self.carga_familiar} (Delegación: {self.celebracion_delegacion.delegacion})"
        return f"Vecino: {self.vecino} (Delegación: {self.celebracion_delegacion.delegacion})"

    class Meta:
        db_table = 'beneficiario_celebracion'
        verbose_name_plural = 'Beneficiarios de Celebraciones'
        constraints = [
            models.UniqueConstraint(
                fields=['celebracion_delegacion', 'vecino'],
                condition=Q(vecino__isnull=False),
                name='uq_beneficiario_vecino_evento',
            ),
            models.UniqueConstraint(
                fields=['celebracion_delegacion', 'carga_familiar'],
                condition=Q(carga_familiar__isnull=False),
                name='uq_beneficiario_carga_evento',
            ),
        ]

    def clean(self):
        super().clean()
        if bool(self.vecino_id) == bool(self.carga_familiar_id):
            raise ValidationError(
                'Debes asociar exactamente un Vecino o una Carga Familiar.'
            )