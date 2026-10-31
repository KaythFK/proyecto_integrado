from django import forms
from .models import Actividad, Evidencia, Validacion
from administracionApp.models import Profesional 
class ActividadForm(forms.ModelForm):
    class Meta:
        model = Actividad
        exclude = ['codigo_unico', 'estado']
        

        widgets = {
            'solicitud_problema': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe el problema o solicitud...'}),
            'accion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe la acción realizada o a tomar...'}),
            'codigo_unico': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: ACT-2026-001'}),
            'solicitante_profesional': forms.Select(attrs={'class': 'form-select'}),
            'solicitante_vecino': forms.Select(attrs={'class': 'form-select'}),
            'estado_progreso': forms.Select(attrs={'class': 'form-select'}),
            'en_tubo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'id_profesional': forms.Select(attrs={'class': 'form-select'}),
            'id_meta': forms.Select(attrs={'class': 'form-select'}),
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