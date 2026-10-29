import re

from django import forms
from django.contrib.auth.forms import SetPasswordForm


class RecuperarClaveForm(forms.Form):
    correo = forms.EmailField(
        label='Correo',
        max_length=150,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'}),
    )

    def clean_correo(self):
        return self.cleaned_data['correo'].lower().strip()


class RestablecerClaveForm(SetPasswordForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password1'].label = 'Nueva contraseña'
        self.fields['new_password2'].label = 'Confirmar contraseña'
        self.fields['new_password1'].help_text = (
            'Mínimo 8 caracteres, al menos una mayúscula y un carácter especial.'
        )
        for campo in self.fields.values():
            campo.widget.attrs['class'] = 'form-control'

    def clean_new_password1(self):
        clave = self.cleaned_data['new_password1']
        if len(clave) < 8 or not any(c.isupper() for c in clave) or not re.search(r"[!@#$%^&*(),.?\":{}|<>]", clave):
            raise forms.ValidationError('La contraseña no cumple con los requisitos.')
        return clave
