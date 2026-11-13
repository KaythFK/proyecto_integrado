from django import forms
from .models import Actividad, Evidencia, Validacion, Ausencia, Retroalimentacion, GestionActividad
from config.utils import validar_texto_no_vacio, validar_fecha_no_futura, validar_profesionales_distintos, validar_que_sea_delegado, validar_entero_positivo, limitar_a_opciones_activas
from datetime import date
from administracionApp.models import Profesional

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
            'en_tubo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'id_profesional': forms.Select(attrs={'class': 'form-select'}),
            'id_meta': forms.Select(attrs={'class': 'form-select'}),
            'id_organizacion': forms.Select(attrs={'class': 'form-select'}),

            # Nuevos campos de fecha con formato DD-MM-AAAA y selector de calendario
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

class ActividadDelegadoForm(ActividadForm):
    def __init__(self, *args, **kwargs):
        # Extraemos la delegación de forma segura
        delegacion = kwargs.pop('delegacion', None)
        # Inicializamos el formulario padre
        super().__init__(*args, **kwargs)
        
        # Filtramos los selectores solo si se pasó una delegación
        if delegacion:
            profesionales_equipo = Profesional.objects.filter(id_delegacion=delegacion, estado=True)
            self.fields['id_profesional'].queryset = profesionales_equipo
            self.fields['solicitante_profesional'].queryset = profesionales_equipo



class AusenciaForm(forms.ModelForm):
    class Meta:
        model = Ausencia
        exclude = ['estado'] # Permitimos que el sistema controle el estado por defecto al crear
        
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
        # Opcional: Filtrar el queryset del receptor para que solo liste profesionales que son delegados
        # (Ajusta la consulta según cómo identifiques a los delegados en tu base de datos)
        self.fields['receptor'].queryset = Profesional.objects.filter(
            id_delegacion__isnull=False # O el filtro equivalente en tu modelo
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
        
        # Validar que no se autorretroalimente
        validar_profesionales_distintos(receptor, retroalimentado)
        
        return cleaned_data


class EvidenciaForm(forms.ModelForm):
    class Meta:
        model = Evidencia
        exclude = ['estado', 'metadatos'] # Excluimos metadatos para generarlo automático atrás
        
        labels = {
            'archivo_vinculo': 'Archivo o Enlace de Evidencia',
            'estado_revision': 'Estado de Revisión',
            'id_actividad': 'Actividad Asociada',
        }
        
        widgets = {
            'archivo_vinculo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: /media/evidencias/doc.pdf', 'required': True}),
            'estado_revision': forms.Select(attrs={'class': 'form-select', 'required': True}), # <--- Ahora es un Select limpio gracias al ENUM
            'id_actividad': forms.Select(attrs={'class': 'form-select', 'required': True}),
        }

    def clean_archivo_vinculo(self):
        return validar_texto_no_vacio(self.cleaned_data.get('archivo_vinculo'), "El archivo o vínculo")




class ValidacionForm(forms.ModelForm):
    class Meta:
        model = Validacion
        exclude = ['estado', 'resultado'] # Excluimos lo que ya borramos
        
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
            'id_evidencia': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'id_validador': forms.Select(attrs={'class': 'form-select', 'required': True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['id_evidencia'].queryset = Evidencia.objects.select_related('id_actividad').all()
        
        # Muestra solo la evidencia y el código único de la actividad
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
        # Solo tipos de gestión activos; al editar se conserva el que ya tenía el registro
        limitar_a_opciones_activas(self.fields['tipo_gestion'], self.instance.tipo_gestion_id)
