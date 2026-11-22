import re

from django import forms
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.models import Group

from .models import PERFILES_BASE, RolSistema


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


class CambioClaveInicialForm(RestablecerClaveForm):

    def clean_new_password1(self):
        clave = super().clean_new_password1()
        if self.user.check_password(clave):
            raise forms.ValidationError('La nueva contraseña debe ser distinta de la contraseña temporal.')
        return clave


class RolForm(forms.ModelForm):
    field_order = ['nombre', 'perfil_base', 'descripcion']
    nombre = forms.CharField(
        label='Nombre del rol', max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Técnico de terreno'}),
    )

    class Meta:
        model = RolSistema
        fields = ['perfil_base', 'descripcion']
        labels = {
            'perfil_base': 'Perfil de acceso base',
            'descripcion': 'Descripción',
        }
        widgets = {
            'perfil_base': forms.Select(attrs={'class': 'form-select'}),
            'descripcion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Qué hace este rol en el sistema'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['perfil_base'].help_text = 'El rol tendrá los mismos accesos que este perfil.'
        self.fields['perfil_base'].choices = [('', 'Seleccione un perfil...')] + RolSistema.OPCIONES_PERFIL
        if self.instance.pk:
            self.fields['nombre'].initial = self.instance.grupo.name
            if self.instance.es_base:
                for campo in ('nombre', 'perfil_base'):
                    self.fields[campo].disabled = True
                self.fields['perfil_base'].help_text = 'Es un perfil base del sistema: su nombre y accesos no se modifican.'

    def clean_nombre(self):
        if self.instance.pk and self.instance.es_base:
            return self.instance.grupo.name
        nombre = ' '.join((self.cleaned_data.get('nombre') or '').split())
        if len(nombre) < 3:
            raise forms.ValidationError('El nombre debe tener al menos 3 caracteres.')
        if nombre.lower() in (perfil.lower() for perfil in PERFILES_BASE):
            raise forms.ValidationError('Ese nombre corresponde a un perfil base del sistema.')
        otros = Group.objects.exclude(pk=self.instance.grupo_id) if self.instance.pk else Group.objects.all()
        if any(nombre.casefold() == existente.casefold() for existente in otros.values_list('name', flat=True)):
            raise forms.ValidationError('Ya existe un rol con ese nombre.')
        return nombre

    def clean_descripcion(self):
        descripcion = ' '.join((self.cleaned_data.get('descripcion') or '').split())
        if len(descripcion) < 10:
            raise forms.ValidationError('Describe el rol en al menos 10 caracteres.')
        return descripcion

    def save(self, commit=True):
        rol = super().save(commit=False)
        nombre = self.cleaned_data['nombre']
        if rol.pk:
            if rol.grupo.name != nombre:
                rol.grupo.name = nombre
                rol.grupo.save(update_fields=['name'])
        else:
            rol.grupo = Group.objects.create(name=nombre)
            rol.es_base = False
            rol.estado = True
        if commit:
            rol.save()
        return rol
