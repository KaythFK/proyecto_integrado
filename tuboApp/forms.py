from django import forms
from .models import ObservacionCompromiso

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