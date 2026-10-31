from django import forms
from .models import Meta

class MetaForm(forms.ModelForm):
    class Meta:
        model = Meta
        exclude = ['estado']
        widgets = {
            'valor_objetivo': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'min': '0.01',
                'placeholder': 'Ej: 100.00',
                'required': True
            }),
            'unidad': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Porcentaje, Cantidad, Horas...',
                'minlength': '2',
                'required': True
            }),
            'ponderador': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '1', 
                'min': '1', 
                'max': '100', 
                'placeholder': 'Ej: 25',
                'required': True
            }),
            'id_item': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'id_periodo': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'id_cargo': forms.Select(attrs={'class': 'form-select'}),
            'id_funcionario': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean_valor_objetivo(self):
        valor = self.cleaned_data.get('valor_objetivo')
        if valor is None:
            raise forms.ValidationError("El valor objetivo es obligatorio.")
        if valor <= 0:
            raise forms.ValidationError("El valor objetivo debe ser estrictamente mayor a cero.")
        return valor

    def clean_unidad(self):
        unidad = self.cleaned_data.get('unidad')
        if not unidad or unidad.strip() == '':
            raise forms.ValidationError("Debes especificar la unidad de medida.")
        if len(unidad.strip()) < 2:
            raise forms.ValidationError("El nombre de la unidad es demasiado corto.")
        return unidad

    def clean_ponderador(self):
        ponderador = self.cleaned_data.get('ponderador')
        if ponderador is None:
            raise forms.ValidationError("El porcentaje de ponderación es obligatorio.")
        if ponderador <= 0 or ponderador > 100:
            raise forms.ValidationError("La ponderación debe ser un valor entre 1 y 100.")
        return ponderador

    def clean(self):
        cleaned_data = super().clean()
        id_cargo = cleaned_data.get('id_cargo')
        id_funcionario = cleaned_data.get('id_funcionario')

        # 1. Validar que al menos uno esté seleccionado
        if not id_cargo and not id_funcionario:
            raise forms.ValidationError("Es obligatorio asignar la meta a un Cargo o a un Funcionario específico.")
            
        # 2. Validar que no se seleccionen ambos al mismo tiempo para evitar conflictos lógicos
        if id_cargo and id_funcionario:
            raise forms.ValidationError("Debes asignar la meta solo a un Cargo O a un Funcionario, pero no a ambos a la vez.")

        return cleaned_data