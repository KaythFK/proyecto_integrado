from django import forms
from django.db.models import Q
from .models import Actividad, Evidencia, Validacion, Ausencia, Retroalimentacion, GestionActividad
from config.utils import (
    validar_texto_no_vacio, 
    validar_fecha_no_futura, 
    validar_profesionales_distintos, 
    validar_que_sea_delegado, 
    validar_entero_positivo, 
    limitar_a_opciones_activas,
    validar_imagen_evidencia,
    validar_datos_vecino_actividad, 
    validar_tope_diario_actividades,
    validar_cierre_semanal,
    validar_periodo_abierto,
    validar_rango_fechas
    # <-- Validador modular de imágenes
)
from datetime import date
from administracionApp.models import Profesional
from django.core.exceptions import ValidationError as CoreValidationError
from django.utils import timezone
from datetime import timedelta

class ActividadProfesionalForm(forms.ModelForm):
    class Meta:
        model = Actividad
        exclude = ['fecha_registro', 'codigo_unico', 'estado', 'id_profesional']

        widgets = {
            'fecha_finalizacion': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_comprometida': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'solicitud_problema': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Detalle la solicitud o problema...'}),
            'accion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Detalle la acción realizada...'}),
            'en_tubo': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
                'style': 'width: 3em; height: 1.5em; cursor: pointer;'
            }),
            'estado_progreso': forms.Select(attrs={'class': 'form-select'}),
            'solicitante_profesional': forms.Select(attrs={'class': 'form-select'}),
            'solicitante_vecino': forms.Select(attrs={'class': 'form-select'}),
            'id_meta': forms.Select(attrs={'class': 'form-select'}),
            'id_organizacion': forms.Select(attrs={'class': 'form-select'}),
        }

        labels = {
            'fecha_finalizacion': 'Fecha de Realización de la Gestión',
            'fecha_comprometida': 'Fecha Comprometida (Si pasa al Tubo)',
            'solicitante_vecino': 'Vecino Solicitante',
            'solicitante_profesional': 'Profesional Solicitante (Interno)',
            'id_meta': 'Meta Asociada',
            'id_organizacion': 'Organización Comunitaria',
            'solicitud_problema': 'Problema o Solicitud Inicial',
            'accion': 'Acción Realizada',
            'en_tubo': '¿Genera compromiso en el Tubo?',
            'estado_progreso': 'Estado de Progreso',
        }

    def __init__(self, *args, **kwargs):
        self.usuario_actual = kwargs.pop('usuario_actual', None)
        super().__init__(*args, **kwargs)

        self.profesional_real = getattr(self.usuario_actual, 'profesional', None) if self.usuario_actual else None
        if self.usuario_actual and not self.profesional_real:
            self.profesional_real = Profesional.objects.filter(usuario=self.usuario_actual).first()

        if self.profesional_real:
            if 'id_meta' in self.fields and getattr(self.profesional_real, 'id_cargo_id', None):
                filtro_meta = Q(
                    estado=True,
                    id_cargo_item__estado=True,
                    id_cargo_item__id_cargo=self.profesional_real.id_cargo_id
                )
                if self.instance and self.instance.pk and self.instance.id_meta_id:
                    filtro_meta |= Q(pk=self.instance.id_meta_id)
                self.fields['id_meta'].queryset = self.fields['id_meta'].queryset.filter(filtro_meta).distinct()

            if 'solicitante_profesional' in self.fields and getattr(self.profesional_real, 'id_delegacion_id', None):
                self.fields['solicitante_profesional'].queryset = Profesional.objects.filter(
                    id_delegacion=self.profesional_real.id_delegacion_id,
                    estado=True,
                    usuario__groups__name='Profesional'
                ).distinct().order_by('nombres')

        hoy = timezone.localdate()
        limite = hoy - timedelta(days=7 if hoy.weekday() == 0 else hoy.weekday())
        self.fields['fecha_finalizacion'].widget.attrs['min'] = limite.strftime('%Y-%m-%d')

    def _ejecutar_validacion(self, campo, fn, *args):
        try:
            fn(*args)
        except CoreValidationError as e:
            msg = str(e.message if hasattr(e, 'message') else e.messages[0])
            self.add_error(campo, msg)

    def clean(self):
        cleaned_data = super().clean()
        vecino = cleaned_data.get('solicitante_vecino')
        fecha_finalizacion = cleaned_data.get('fecha_finalizacion')
        fecha_comprometida = cleaned_data.get('fecha_comprometida')
        meta = cleaned_data.get('id_meta')
        en_tubo = cleaned_data.get('en_tubo')

        if meta:
            if (
                self.profesional_real
                and getattr(self.profesional_real, 'id_cargo_id', None)
                and getattr(meta.id_cargo_item, 'id_cargo_id', None) != self.profesional_real.id_cargo_id
            ):
                self.add_error('id_meta', "La meta seleccionada no corresponde a tu cargo.")
            self._ejecutar_validacion('id_meta', validar_periodo_abierto, meta)

        if vecino:
            self._ejecutar_validacion('solicitante_vecino', validar_datos_vecino_actividad, vecino)

        if self.usuario_actual:
            objetivo_tope = self.profesional_real or self.usuario_actual
            self._ejecutar_validacion(None, validar_tope_diario_actividades, objetivo_tope)

        if fecha_finalizacion:
            self._ejecutar_validacion('fecha_finalizacion', validar_cierre_semanal, fecha_finalizacion)

        if en_tubo and not fecha_comprometida:
            self.add_error('fecha_comprometida', "Si la actividad genera un compromiso en el Tubo, debe indicar una fecha comprometida.")

        if fecha_comprometida and fecha_finalizacion:
            self._ejecutar_validacion('fecha_comprometida', validar_rango_fechas, fecha_finalizacion, fecha_comprometida)

        return cleaned_data

    def save(self, commit=True):
        instancia = super().save(commit=False)
        if self.profesional_real:
            instancia.id_profesional = self.profesional_real
        if commit:
            instancia.save()
            self.save_m2m()
        return instancia

    
class ActividadForm(forms.ModelForm):
    class Meta:
        model = Actividad
        exclude = ['codigo_unico', 'estado']
        
        widgets = {
            'solicitud_problema': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe el problema o solicitud...'}),
            'accion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe la acción realizada o a tomar...'}),
            'solicitante_profesional': forms.Select(attrs={'class': 'form-select'}),
            'solicitante_vecino': forms.Select(attrs={'class': 'form-select'}),
            'estado_progreso': forms.Select(attrs={'class': 'form-select'}),
            'en_tubo': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'id_profesional': forms.Select(attrs={'class': 'form-select'}),
            'id_meta': forms.Select(attrs={'class': 'form-select'}),
            'id_organizacion': forms.Select(attrs={'class': 'form-select'}),

            'fecha_comprometida': forms.DateInput(
                format='%d-%m-%Y', 
                attrs={
                    'type': 'date', 
                    'class': 'form-control'
                }
            ),
            'fecha_finalizacion': forms.DateInput(
                format='%d-%m-%Y', 
                attrs={
                    'type': 'date', 
                    'class': 'form-control'
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = date.today()
        filtro = Q(id_periodo__estado=True, id_periodo__fecha_inicio__lte=hoy, id_periodo__fecha_termino__gte=hoy)
        if self.instance.pk and self.instance.id_meta_id:
            filtro |= Q(pk=self.instance.id_meta_id)
        self.fields['id_meta'].queryset = self.fields['id_meta'].queryset.filter(filtro)

    def clean_id_meta(self):
        meta = self.cleaned_data.get('id_meta')
        if meta and not meta.id_periodo.esta_vigente:
            raise forms.ValidationError(
                f'El período "{meta.id_periodo.nombre}" de esta meta no está vigente (cerrado o fuera de fecha). '
                'No se pueden registrar ni modificar actividades en él.'
            )
        return meta


class ActividadDelegadoForm(ActividadForm):
    def __init__(self, *args, **kwargs):
        delegacion = kwargs.pop('delegacion', None)
        super().__init__(*args, **kwargs)
        
        if delegacion:
            profesionales_equipo = Profesional.objects.filter(
                id_delegacion=delegacion,
                estado=True,
                usuario__groups__name='Profesional'
            ).distinct().order_by('nombres')
            
            if 'id_profesional' in self.fields:
                self.fields['id_profesional'].queryset = profesionales_equipo
            if 'solicitante_profesional' in self.fields:
                self.fields['solicitante_profesional'].queryset = profesionales_equipo



class AusenciaForm(forms.ModelForm):
    class Meta:
        model = Ausencia
        exclude = ['estado']
        
        labels = {
            'tipo_ausencia': 'Tipo de Ausencia / Permiso',
            'fecha_inicio': 'Fecha de Inicio',
            'fecha_termino': 'Fecha de Término',
            'dias_computables': 'Días Computables',
            'profesional_ausente': 'Profesional / Funcionario Ausente',
            'periodo_ausencia': 'Periodo Asociado',
        }
        
        widgets = {
            'tipo_ausencia': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Vacaciones, Licencia Médica', 'maxlength': '50', 'required': True}),
            'fecha_inicio': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': True}),
            'fecha_termino': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': True}),
            'dias_computables': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'required': True}),
            'profesional_ausente': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'periodo_ausencia': forms.Select(attrs={'class': 'form-select', 'required': True}),
        }

    def clean(self):
        cleaned_data = super().clean()
        f_inicio = cleaned_data.get('fecha_inicio')
        f_termino = cleaned_data.get('fecha_termino')

        if f_inicio and f_termino:
            if f_termino < f_inicio:
                self.add_error('fecha_termino', "La fecha de término no puede ser anterior a la fecha de inicio.")
                
        return cleaned_data



class RetroalimentacionForm(forms.ModelForm):
    class Meta:
        model = Retroalimentacion
        exclude = ['estado']
        
        labels = {
            'tipo': 'Tipo de Retroalimentación',
            'archivo_respaldo': 'Archivo o Enlace de Respaldo',
            'canal_recepcion': 'Canal de Recepción',
            'fecha': 'Fecha de Retroalimentación',
            'receptor': 'Delegado Receptor',
            'retroalimentado': 'Profesional Retroalimentado',
            'vecino': 'Vecino (Opcional)',
            'delegacion': 'Delegación (Opcional)',
            'meta': 'Meta Institucional (Opcional)',
        }
        
        widgets = {
            'tipo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Evaluación de desempeño', 'maxlength': '150', 'required': True}),
            'archivo_respaldo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ruta o enlace del documento de respaldo', 'maxlength': '255'}),
            'canal_recepcion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Presencial, Correo', 'maxlength': '100', 'required': True}),
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': True}),
            'receptor': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'retroalimentado': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'vecino': forms.Select(attrs={'class': 'form-select'}),
            'delegacion': forms.Select(attrs={'class': 'form-select'}),
            'meta': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['receptor'].queryset = Profesional.objects.filter(
            id_delegacion__isnull=False
        ).distinct()

    def clean_tipo(self):
        return validar_texto_no_vacio(self.cleaned_data.get('tipo'), "El tipo de retroalimentación")

    def clean_canal_recepcion(self):
        return validar_texto_no_vacio(self.cleaned_data.get('canal_recepcion'), "El canal de recepción")

    def clean_fecha(self):
        fecha = self.cleaned_data.get('fecha')
        return validar_fecha_no_futura(fecha)

    def clean_receptor(self):
        receptor = self.cleaned_data.get('receptor')
        return validar_que_sea_delegado(receptor)

    def clean(self):
        cleaned_data = super().clean()
        receptor = cleaned_data.get('receptor')
        retroalimentado = cleaned_data.get('retroalimentado')
        validar_profesionales_distintos(receptor, retroalimentado)
        return cleaned_data


class EvidenciaForm(forms.ModelForm):
    class Meta:
        model = Evidencia
        exclude = ['estado', 'metadatos', 'estado_revision', 'id_actividad']
        
        labels = {
            'archivo_foto': 'Fotografía de Evidencia',
            'id_actividad': 'Actividad Asociada',
        }
        
        widgets = {
            'archivo_foto': forms.ClearableFileInput(attrs={'class': 'form-control', 'required': True}),
            'id_actividad': forms.Select(attrs={'class': 'form-select', 'required': True}),
        }

    def clean_archivo_foto(self):
        archivo = self.cleaned_data.get('archivo_foto')
        return validar_imagen_evidencia(archivo)



class ValidacionForm(forms.ModelForm):
    class Meta:
        model = Validacion
        exclude = ['estado', 'resultado']
        
        labels = {
            'decision': 'Decisión de Validación',
            'observacion': 'Observaciones (Opcional)',
            'version': 'Versión',
            'id_evidencia': 'Evidencia Asociada',
            'id_validador': 'Profesional Validador',
        }
        
        widgets = {
            'decision': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'observacion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Detalles o comentarios de la validación...'}),
            'version': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'required': True}),
            # Los hacemos ocultos o de solo lectura para que se autocomlenen de forma segura
            'id_evidencia': forms.HiddenInput(),
            'id_validador': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['id_evidencia'].queryset = Evidencia.objects.select_related('id_actividad').all()
        self.fields['id_evidencia'].label_from_instance = lambda obj: f"Evidencia #{obj.pk} - {obj.id_actividad.codigo_unico}"

    def clean_version(self):
        version = self.cleaned_data.get('version')
        return validar_entero_positivo(version, "La versión")



class GestionActividadForm(forms.ModelForm):
    class Meta:
        model = GestionActividad
        fields = ['tipo_gestion', 'fecha_ejecucion', 'descripcion']
        
        widgets = {
            'tipo_gestion': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'fecha_ejecucion': forms.DateInput(attrs={
                'class': 'form-control', 
                'type': 'date'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 4, 
                'placeholder': 'Detalla las acciones realizadas durante esta gestión...'
            }),
        }
        
        labels = {
            'tipo_gestion': 'Tipo de Gestión (*)',
            'fecha_ejecucion': 'Fecha de Ejecución (Opcional)',
            'descripcion': 'Descripción Detallada (*)'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limitar_a_opciones_activas(self.fields['tipo_gestion'], self.instance.tipo_gestion_id)