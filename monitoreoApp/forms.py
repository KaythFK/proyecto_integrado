from django import forms
from .models import Meta, Indicador
from config.utils import limitar_a_opciones_activas
from django.core.exceptions import ValidationError as CoreValidationError
from django.db.models import Q
from config.utils import (
    validar_texto_no_vacio,
    validar_periodo_abierto,
    validar_datos_meta,
    validar_fechas_meta_en_periodo,
)


class MetaForm(forms.ModelForm):
    class Meta:
        model = Meta
        exclude = ['estado', 'version', 'autor']
        widgets = {
            'valor_objetivo': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'placeholder': 'Ej: 100.00',
                'required': True,
            }),
            'unidad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Porcentaje, Cantidad, Horas...',
                'minlength': '2',
                'required': True,
            }),
            'ponderador': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'max': '100',
                'placeholder': 'Ej: 25',
                'required': True,
            }),
            'id_cargo_item': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'id_periodo': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'fecha_inicio': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': True}),
            'fecha_termino': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'id_cargo_item' in self.fields:
            filtro = Q(estado=True)
            if self.instance and self.instance.pk and self.instance.id_cargo_item_id:
                filtro |= Q(pk=self.instance.id_cargo_item_id)
            self.fields['id_cargo_item'].queryset = (
                self.fields['id_cargo_item'].queryset
                .filter(filtro)
                .select_related('id_cargo')
                .order_by('pk')
            )

    def clean_id_periodo(self):
        periodo = self.cleaned_data.get('id_periodo')
        if periodo:
            if not getattr(periodo, 'esta_abierto', True):
                raise forms.ValidationError(
                    f'El período "{periodo.nombre}" está cerrado. Debe reabrirse antes de crear o modificar sus metas.'
                )
            # Reutilizamos también validar_periodo_abierto simulando el vínculo id_periodo
            try:
                validar_periodo_abierto(type('TmpMeta', (), {'id_periodo': periodo})())
            except CoreValidationError as e:
                raise forms.ValidationError(e.message if hasattr(e, 'message') else e.messages[0])
        return periodo

    def clean_unidad(self):
        unidad = self.cleaned_data.get('unidad')
        try:
            unidad_limpia = validar_texto_no_vacio(unidad, "La unidad de medida")
        except CoreValidationError as e:
            raise forms.ValidationError(e.message if hasattr(e, 'message') else e.messages[0])
        if len(unidad_limpia) < 2:
            raise forms.ValidationError("El nombre de la unidad es demasiado corto.")
        return unidad_limpia

    def clean(self):
        cleaned_data = super().clean()
        valor_objetivo = cleaned_data.get('valor_objetivo')
        unidad = cleaned_data.get('unidad')
        ponderador = cleaned_data.get('ponderador')
        periodo = cleaned_data.get('id_periodo')
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_termino = cleaned_data.get('fecha_termino')

        if valor_objetivo is not None and unidad and ponderador is not None:
            try:
                validar_datos_meta(valor_objetivo, unidad, ponderador)
            except CoreValidationError as e:
                self.add_error(None, e.message if hasattr(e, 'message') else e.messages[0])

        try:
            validar_fechas_meta_en_periodo(fecha_inicio, fecha_termino, periodo)
        except CoreValidationError as e:
            self.add_error('fecha_termino' if fecha_termino else 'fecha_inicio', e.message if hasattr(e, 'message') else e.messages[0])

        return cleaned_data


class IndicadorForm(forms.ModelForm):
    class Meta:
        model = Indicador
        exclude = ['estado', 'fecha_calculo', 'avance']
        
        labels = {
            'avance': 'Avance Actual',
            'cumplimiento': 'Cumplimiento (%)',
            'ponderacion': 'Ponderación',
            'ajuste': 'Ajuste',
            'semaforo': 'Semáforo de Estado',
            'meta_id_meta': 'Meta Asociada',
        }
        
        widgets = {
            'avance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'Ej: 100.00'}),
            'cumplimiento': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '120', 'placeholder': 'Ej: 85.50'}),
            'ponderacion': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100', 'placeholder': 'Ej: 20.00'}),
            'ajuste': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Ej: 0.00'}),
            'semaforo': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'meta_id_meta': forms.Select(attrs={'class': 'form-select', 'required': True}),
        }

    def clean_avance(self):
        avance = self.cleaned_data.get('avance')
        if avance is not None and avance < 0:
            raise forms.ValidationError("El avance no puede ser un número negativo.")
        return avance

    def clean_cumplimiento(self):
        cumplimiento = self.cleaned_data.get('cumplimiento')
        if cumplimiento is not None and (cumplimiento < 0 or cumplimiento > 120):
            raise forms.ValidationError("El porcentaje de cumplimiento debe estar entre 0 y 100.")
        return cumplimiento

    def clean_ponderacion(self):
        ponderacion = self.cleaned_data.get('ponderacion')
        if ponderacion is not None and (ponderacion < 0 or ponderacion > 100):
            raise forms.ValidationError("La ponderación debe estar entre 0 y 100.")
        return ponderacion