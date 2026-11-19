from datetime import date
from django.db import models
from datetime import datetime
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys

# Create your models here.

class Actividad(models.Model):

#Opciones para ENUM de estado_progreso
    OPCIONES_ESTADO_PROGRESO = [
        ('PENDIENTE', 'Pendiente'),
        ('EN_PROCESO', 'En proceso'),
        ('FINALIZADA', 'Finalizada'),
    ]

    id_actividad = models.AutoField(primary_key=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_comprometida = models.DateField(null=True, blank=True)
    fecha_finalizacion = models.DateField(null=True, blank=True)
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
    id_organizacion = models.ForeignKey('comunidadApp.OrganizacionComunitaria', models.DO_NOTHING, db_column='id_organizacion', blank=True, null=True)

    @property
    def esta_vencida(self):
        if self.fecha_comprometida:
            return date.today() > self.fecha_comprometida and self.estado_progreso != 'FINALIZADA'
        return False

    @property
    def tipos_gestion(self):
        # Nombres (sin repetir) de los tipos de gestión de sus gestiones activas.
        # Usar con prefetch_related('gestiones__tipo_gestion') para no hacer una consulta por fila.
        nombres = []
        for gestion in self.gestiones.all():
            if gestion.estado and gestion.tipo_gestion.nombre not in nombres:
                nombres.append(gestion.tipo_gestion.nombre)
        return nombres

    def __str__(self):
        return f"Actividad {self.codigo_unico} - {self.estado_progreso}"

    class Meta:
        db_table = 'actividad'
        verbose_name_plural = 'Actividades'


class CatalogoTipoGestion(models.Model):
    id_tipo_gestion = models.AutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=100)
    estado = models.BooleanField(default=True)

    def __str__(self):
        return str(self.nombre)

    class Meta:
        db_table = 'catalogo_tipo_gestion'
        verbose_name_plural = 'Catálogo Tipos de Gestión'

class GestionActividad(models.Model):

    id_gestion = models.AutoField(primary_key=True)
    # related_name='gestiones' permite consultar desde la actividad: mi_actividad.gestiones.all()
    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, db_column='id_actividad', related_name='gestiones')
    tipo_gestion = models.ForeignKey(CatalogoTipoGestion, models.DO_NOTHING, db_column='id_tipo_gestion')
    descripcion = models.TextField()
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_ejecucion = models.DateField(blank=True, null=True)
    profesional = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, db_column='id_profesional')
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f"Gestión: {self.get_tipo_gestion_display()} - Actividad {self.actividad.codigo_unico}"

    class Meta:
        db_table = 'gestion_actividad'
        verbose_name_plural = 'Gestiones de Actividades'

class Evidencia(models.Model):
    OPCIONES_ESTADO_REVISION = [
        ('PENDIENTE', 'Pendiente'),
        ('REVISADO', 'Revisado'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado'),
    ]

    id_evidencia = models.AutoField(primary_key=True)
    archivo_foto = models.ImageField(upload_to='evidencias/') 
    fecha = models.DateTimeField(auto_now_add=True)
    metadatos = models.JSONField(blank=True, null=True) 
    estado_revision = models.CharField(max_length=20, choices=OPCIONES_ESTADO_REVISION, default='PENDIENTE')
    estado = models.BooleanField(default=True)
    id_actividad = models.ForeignKey('Actividad', models.DO_NOTHING, db_column='id_actividad')

    def save(self, *args, **kwargs):
        """
        Sobrescribe el método save para:
        1. Comprimir y redimensionar la imagen automáticamente con Pillow.
        2. Nombrar el archivo combinando el código de la actividad y la fecha/hora actual.
        """
        if self.archivo_foto:
            try:
                # 1. Abrir la imagen con Pillow
                img = Image.open(self.archivo_foto)
                
                # Si la imagen tiene transparencia (como PNG), convertirla a RGB para evitar errores en JPG
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')

                # 2. Redimensionar si es muy ancha (máximo 1280px para mantener excelente calidad y bajo peso)
                max_ancho = 1280
                if img.width > max_ancho:
                    output_alto = int((max_ancho / img.width) * img.height)
                    img = img.resize((max_ancho, output_alto), Image.Resampling.LANCZOS)

                # 3. Guardar en memoria RAM optimizando la calidad al 85%
                output = BytesIO()
                img.save(output, format='JPEG', quality=85, optimize=True)
                output.seek(0)

                # 4. Generar el nombre estructurado: CODIGO_ACTIVIDAD_FECHA_HORA.jpg
                codigo_actividad = self.id_actividad.codigo_unico if self.id_actividad else "general"
                fecha_actual = datetime.now().strftime('%Y%m%d_%H%M%S')
                nombre_archivo = f"{codigo_actividad}_{fecha_actual}.jpg"

                # 5. Reemplazar el archivo original por la versión optimizada y renombrada
                self.archivo_foto = InMemoryUploadedFile(
                    output,
                    'ImageField',
                    nombre_archivo,
                    'image/jpeg',
                    sys.getsizeof(output),
                    None
                )
            except Exception as e:
                print(f"No se pudo optimizar la imagen: {e}")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Evidencia {self.id_evidencia} ({self.get_estado_revision_display()})"

    class Meta:
        db_table = 'evidencia'
        verbose_name_plural = 'Evidencias'

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
    version = models.IntegerField()
    estado = models.BooleanField()
    id_evidencia = models.ForeignKey('Evidencia', models.DO_NOTHING, db_column='id_evidencia')
    id_validador = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, db_column='id_validador')

    def __str__(self):
        return f"Validación {self.id_validacion} ({self.decision})"

    class Meta:
        db_table = 'validacion'
        verbose_name_plural = 'Validaciones'


class Retroalimentacion(models.Model):
    id_retroalimentacion = models.AutoField(primary_key=True)
    tipo = models.CharField(max_length=150) 
    archivo_respaldo = models.CharField(max_length=255, blank=True, null=True)
    canal_recepcion = models.CharField(max_length=100) 
    fecha = models.DateField()
    estado = models.BooleanField(default=True)
    receptor = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, related_name='retro_recibidas', db_column='id_receptor')
    retroalimentado = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, related_name='retro_realizadas', db_column='id_retroalimentado')
    vecino = models.ForeignKey('administracionApp.Vecino', models.DO_NOTHING, db_column='id_vecino', blank=True, null=True)
    delegacion = models.ForeignKey('administracionApp.Delegacion', models.DO_NOTHING, db_column='id_delegacion', blank=True, null=True) 
    meta = models.ForeignKey('monitoreoApp.Meta', models.DO_NOTHING, db_column='id_meta', blank=True, null=True) 

    def __str__(self):
        return f"Retroalimentación {self.id_retroalimentacion} - {self.tipo}"

    class Meta:
        db_table = 'retroalimentacion'
        verbose_name_plural = 'Retroalimentaciones'


class Ausencia(models.Model):
    id_ausencia = models.AutoField(primary_key=True)
    tipo_ausencia = models.CharField(max_length=50)
    fecha_inicio = models.DateField()
    fecha_termino = models.DateField()
    dias_computables = models.IntegerField() 
    profesional_ausente = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, db_column='id_profesional')
    periodo_ausencia = models.ForeignKey('administracionApp.Periodo', models.DO_NOTHING, db_column='id_periodo')
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f"Ausencia {self.id_ausencia} - {self.profesional_ausente}"

    class Meta:
        db_table = 'ausencia'
        verbose_name_plural = 'Ausencias'