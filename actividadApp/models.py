from datetime import date
from django.db import models
from datetime import datetime
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys
from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid
# Create your models here.


def tiene_transparencia(img):
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        return img.convert('RGBA').getchannel('A').getextrema()[0] < 255
    return False


def optimizar_imagen(archivo, nombre_base, max_ancho=1280):
    """
    Achica la imagen a max_ancho y la comprime. Si tiene zonas transparentes se guarda como PNG para conservarlas;
    si no, como JPEG al 85 %, que pesa mucho menos. Devuelve el archivo listo para asignar al campo.
    """
    img = Image.open(archivo)
    transparente = tiene_transparencia(img)
    img = img.convert('RGBA' if transparente else 'RGB')
    if img.width > max_ancho:
        img = img.resize((max_ancho, int(max_ancho / img.width * img.height)), Image.Resampling.LANCZOS)
    salida = BytesIO()
    if transparente:
        img.save(salida, format='PNG', optimize=True)
        extension, tipo = 'png', 'image/png'
    else:
        img.save(salida, format='JPEG', quality=85, optimize=True)
        extension, tipo = 'jpg', 'image/jpeg'
    salida.seek(0)
    return InMemoryUploadedFile(salida, 'ImageField', f'{nombre_base}.{extension}', tipo, salida.getbuffer().nbytes, None)

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
    es_coordinacion_preparatoria = models.BooleanField(
        default=False,
        verbose_name='¿Es una coordinación preparatoria?',
        help_text='Se registra, pero no suma al avance de la meta.',
    )
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
        Guarda y optimiza imágenes con Pillow, o renombra conservando la extensión
        si se trata de un documento PDF.
        """
        if self.archivo_foto:
            nombre_original = (getattr(self.archivo_foto, 'name', '') or '').lower()
            es_pdf = nombre_original.endswith('.pdf')

            if es_pdf:
                codigo_actividad = self.id_actividad.codigo_unico if self.id_actividad else "general"
                fecha_actual = datetime.now().strftime('%Y%m%d_%H%M%S')
                sufijo_unico = uuid.uuid4().hex[:8]
                self.archivo_foto.name = f"{codigo_actividad}_{fecha_actual}_{sufijo_unico}.pdf"
            else:
                try:
                    img = Image.open(self.archivo_foto)

                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')

                    max_ancho = 1280
                    if img.width > max_ancho:
                        output_alto = int((max_ancho / img.width) * img.height)
                        img = img.resize((max_ancho, output_alto), Image.Resampling.LANCZOS)

                    output = BytesIO()
                    img.save(output, format='JPEG', quality=85, optimize=True)
                    output.seek(0)

                    codigo_actividad = self.id_actividad.codigo_unico if self.id_actividad else "general"
                    fecha_actual = datetime.now().strftime('%Y%m%d_%H%M%S')
                    sufijo_unico = uuid.uuid4().hex[:8]
                    nombre_archivo = f"{codigo_actividad}_{fecha_actual}_{sufijo_unico}.jpg"

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
    OPCIONES_TIPO = [
        ('FELICITACION', 'Felicitación'),
        ('RECLAMO', 'Reclamo'),
    ]

    id_retroalimentacion = models.AutoField(primary_key=True)
    tipo = models.CharField(max_length=20, choices=OPCIONES_TIPO)
    porcentaje_impacto = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('30.00'))]
    )
    archivo_respaldo = models.ImageField(upload_to='retroalimentaciones/', blank=True, null=True)
    canal_recepcion = models.CharField(max_length=100)
    fecha = models.DateField()
    estado = models.BooleanField(default=True)
    receptor = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, related_name='retro_recibidas', db_column='id_receptor')
    retroalimentado = models.ForeignKey('administracionApp.Profesional', models.DO_NOTHING, related_name='retro_realizadas', db_column='id_retroalimentado')
    vecino = models.ForeignKey('administracionApp.Vecino', models.DO_NOTHING, db_column='id_vecino', blank=True, null=True)
    delegacion = models.ForeignKey('administracionApp.Delegacion', models.DO_NOTHING, db_column='id_delegacion', blank=True, null=True)
    meta = models.ForeignKey('monitoreoApp.Meta', models.DO_NOTHING, db_column='id_meta', blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.archivo_respaldo and not self.archivo_respaldo._committed:
            try:
                tipo_slug = (self.tipo or 'retro').lower()
                self.archivo_respaldo = optimizar_imagen(self.archivo_respaldo, f"{tipo_slug}_{datetime.now():%Y%m%d_%H%M%S}")
            except Exception as e:
                print(f"No se pudo optimizar la imagen de respaldo: {e}")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Retroalimentación {self.id_retroalimentacion} - {self.get_tipo_display()}"

    class Meta:
        db_table = 'retroalimentacion'
        verbose_name_plural = 'Retroalimentaciones'

class Ausencia(models.Model):
    OPCIONES_TIPO = [
        ('VACACIONES', 'Vacaciones'),
        ('DIAS_ADMINISTRATIVOS', 'Días administrativos'),
        ('DIAS_LIBRES', 'Días libres'),
        ('LICENCIA_MEDICA', 'Licencia médica'),
    ]

    id_ausencia = models.AutoField(primary_key=True)
    tipo_ausencia = models.CharField(max_length=50, choices=OPCIONES_TIPO)
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