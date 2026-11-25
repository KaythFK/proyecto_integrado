import re
from datetime import date
from django import forms
from administracionApp.models import Profesional
from config.utils import EtiquetaFuncionarioMixin
from .models import CartaTubo, ObservacionCompromiso

class ObservacionRegistroForm(forms.ModelForm):
    class Meta:
        model = ObservacionCompromiso
        fields = ['texto']
        widgets = {
            'texto': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3, 
                'placeholder': 'Escriba su consulta u observación aquí...'
            }),
        }
        labels = {
            'texto': '',
        }


class CartaTuboForm(EtiquetaFuncionarioMixin, forms.ModelForm):
    class Meta:
        model = CartaTubo
        fields = [
            'delegacion', 'fecha_recepcion', 'numero_oficina_partes', 'destinatario', 'remitente', 'telefono_contacto',
            'tema', 'fecha_actividad', 'encargado', 'estado_carta', 'pronunciamiento', 'derivada_a', 'observacion',
        ]
        widgets = {
            'delegacion': forms.Select(attrs={'class': 'form-select'}),
            'fecha_recepcion': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'numero_oficina_partes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 10093'}),
            'destinatario': forms.Select(attrs={'class': 'form-select'}),
            'remitente': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Persona u organización que envía la carta'}),
            'telefono_contacto': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 912345678'}),
            'tema': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Actividad o tema de la carta'}),
            'fecha_actividad': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'encargado': forms.Select(attrs={'class': 'form-select'}),
            'estado_carta': forms.Select(attrs={'class': 'form-select'}),
            'pronunciamiento': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Delegado, No aplica'}),
            'derivada_a': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Unidad o persona a la que se deriva'}),
            'observacion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'delegacion': 'Delegación',
            'fecha_recepcion': 'Fecha de recepción',
            'numero_oficina_partes': 'N° Oficina de Partes',
            'destinatario': 'Dirigida a',
            'remitente': 'Remitente',
            'telefono_contacto': 'Teléfono de contacto',
            'tema': 'Actividad o tema',
            'fecha_actividad': 'Fecha de la actividad',
            'encargado': 'Encargado de seguimiento',
            'estado_carta': 'Estado',
            'pronunciamiento': 'Pronunciamiento',
            'derivada_a': 'Derivada a',
            'observacion': 'Observación',
        }

    def __init__(self, *args, delegacion=None, puede_aprobar=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.delegacion = delegacion
        encargados = Profesional.objects.filter(estado=True)
        if delegacion is not None:
            del self.fields['delegacion']
            encargados = encargados.filter(id_delegacion=delegacion)
        else:
            self.fields['delegacion'].queryset = self.fields['delegacion'].queryset.filter(estado=True).order_by('nombre')
        if self.instance.pk and self.instance.encargado_id:
            encargados = encargados | Profesional.objects.filter(pk=self.instance.encargado_id)
        self.fields['encargado'].queryset = encargados.distinct().order_by('nombres', 'apellido_paterno')
        if not puede_aprobar:
            self.fields['estado_carta'].choices = [o for o in CartaTubo.OPCIONES_ESTADO if o[0] != 'APROBADA']

    def clean_fecha_recepcion(self):
        fecha = self.cleaned_data.get('fecha_recepcion')
        if fecha and fecha > date.today():
            raise forms.ValidationError('La fecha de recepción no puede ser futura.')
        return fecha

    def clean_telefono_contacto(self):
        telefono = (self.cleaned_data.get('telefono_contacto') or '').strip()
        if telefono and not re.fullmatch(r'\+?[\d ]{8,15}', telefono):
            raise forms.ValidationError('Ingresa un teléfono válido: solo números, entre 8 y 15 dígitos.')
        return telefono

    def clean(self):
        cleaned_data = super().clean()
        delegacion = self.delegacion or cleaned_data.get('delegacion')
        encargado = cleaned_data.get('encargado')
        if delegacion and encargado and encargado.id_delegacion_id != delegacion.pk:
            self.add_error('encargado', 'El encargado debe pertenecer a la delegación de la carta.')
        recepcion, actividad = cleaned_data.get('fecha_recepcion'), cleaned_data.get('fecha_actividad')
        if recepcion and actividad and actividad < recepcion:
            self.add_error('fecha_actividad', 'La fecha de la actividad no puede ser anterior a la recepción de la carta.')
        return cleaned_data
