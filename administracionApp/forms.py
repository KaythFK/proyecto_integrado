import re
from django import forms
from django.contrib.auth.models import User, Group
from .models import Profesional, Delegacion, Cargo, Periodo, Vecino

class UsuarioSeguridadForm(forms.ModelForm):
    # 1. LISTA ESTRICTA DE ROLES: Solo estos aparecerán en el sistema.
    ROLES_OFICIALES = ['Administrador', 'Profesional', 'Coordinador', 'Delegado']

    rol = forms.ModelChoiceField(
        # Filtramos la consulta para ignorar roles antiguos o basura
        queryset=Group.objects.filter(name__in=ROLES_OFICIALES).order_by('name'),
        empty_label="Seleccione un rol en el sistema...",
        label="Rol / Nivel de Permisos",
        widget=forms.Select(attrs={'class': 'form-select', 'required': True})
    )

    class Meta:
        model = User
        fields = ['email']
        labels = {
            'email': 'Correo Electrónico Corporativo',
        }
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'ejemplo@laserena.cl',
                'required': True
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Nos aseguramos de que solo se creen los roles oficiales si es que no existen
        for nombre_rol in self.ROLES_OFICIALES:
            Group.objects.get_or_create(name=nombre_rol)
        
        self.fields['rol'].queryset = Group.objects.filter(name__in=self.ROLES_OFICIALES).order_by('name')

        if self.instance and self.instance.pk:
            grupo_actual = self.instance.groups.first()
            if grupo_actual:
                self.fields['rol'].initial = grupo_actual

    def clean_email(self):
        email = self.cleaned_data.get('email')
        qs = User.objects.filter(username=email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe una cuenta de usuario registrada con este correo.")
        return email


class ProfesionalForm(forms.ModelForm):
    class Meta:
        model = Profesional
        exclude = ['estado', 'usuario', 'correo']
        widgets = {
            'rut': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 12.345.678-9'}),
            'nombres': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombres...'}),
            'apellido_paterno': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellido paterno...'}),
            'apellido_materno': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellido materno...'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+569 1234 5678'}),
            'id_cargo': forms.Select(attrs={'class': 'form-select'}),
            'id_delegacion': forms.Select(attrs={'class': 'form-select'}),
        }

    # 2. VALIDACIÓN DEL RUT (Módulo 11 y Duplicidad)
    def clean_rut(self):
        rut_sucio = self.cleaned_data.get('rut', '')
        # Si viene vacío, lo dejamos pasar para que la validación 'required' del formulario haga su trabajo
        if not rut_sucio:
            return rut_sucio
            
        rut_limpio = rut_sucio.replace('.', '').replace('-', '').upper().strip()
        
        if not re.match(r'^\d{7,8}[0-9K]$', rut_limpio):
            raise forms.ValidationError("Formato inválido. Ingresa un RUT válido.")
        
        cuerpo = rut_limpio[:-1]
        dv_ingresado = rut_limpio[-1]
        
        # Algoritmo Módulo 11
        suma = 0
        multiplicador = 2
        for d in reversed(cuerpo):
            suma += int(d) * multiplicador
            multiplicador = multiplicador + 1 if multiplicador < 7 else 2
            
        dv_calculado = str(11 - (suma % 11))
        if dv_calculado == '11': dv_calculado = '0'
        if dv_calculado == '10': dv_calculado = 'K'
        
        if dv_ingresado != dv_calculado:
            raise forms.ValidationError("El RUT no es válido (dígito verificador incorrecto).")
            
        # 1. DAR FORMATO OFICIAL: Puntos para miles y guion
        cuerpo_con_puntos = f"{int(cuerpo):,}".replace(',', '.')
        rut_oficial = f"{cuerpo_con_puntos}-{dv_ingresado}"
            
        # 2. Validar duplicidad
        qs = Profesional.objects.filter(rut=rut_oficial)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
            
        if qs.exists():
            raise forms.ValidationError("Este RUT ya se encuentra registrado en el sistema.")
            
        # 3. Retornar el RUT oficial para guardarlo en la BD
        return rut_oficial

class DelegacionForm(forms.ModelForm):
    class Meta:
        model = Delegacion
        exclude = ['estado']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Delegación Centro',
                'minlength': '4'
            }),
            'territorio': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Sector Centro Histórico'
            }),
            'calle': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Arturo Prat'
            }),
            'numero_calle': forms.NumberInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: 451',
                'min': '1' 
            }),
            'responsable': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        qs = Delegacion.objects.filter(nombre__iexact=nombre)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe una delegación registrada con este nombre.")
        return nombre

    def clean_numero_calle(self):
        numero = self.cleaned_data.get('numero_calle')
        if numero is not None and numero <= 0:
            raise forms.ValidationError("El número de la dirección debe ser mayor a cero.")
        return numero


class CargoForm(forms.ModelForm):
    class Meta:
        model = Cargo
        exclude = ['estado']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Supervisor de Obras',
                'minlength': '3'
            }),
            'vigencia': forms.NumberInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: 12 (meses)',
                'min': '1'
            }),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        qs = Cargo.objects.filter(nombre__iexact=nombre)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un cargo registrado con este nombre.")
        return nombre

    def clean_vigencia(self):
        vigencia = self.cleaned_data.get('vigencia')
        if vigencia is not None and vigencia <= 0:
            raise forms.ValidationError("La vigencia (en meses) debe ser mayor a cero.")
        return vigencia


class PeriodoForm(forms.ModelForm):
    class Meta:
        model = Periodo
        exclude = ['estado']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Evaluación Semestre 1'}),
            'fecha_inicio': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_termino': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'dias_computables': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'umbral_regular': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0'}),
            'umbral_exelencia': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0'}),
            'version_parametros': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        qs = Periodo.objects.filter(nombre__iexact=nombre)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un periodo registrado con este nombre.")
        return nombre

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_termino = cleaned_data.get('fecha_termino')
        umbral_regular = cleaned_data.get('umbral_regular')
        umbral_exelencia = cleaned_data.get('umbral_exelencia')

        if fecha_inicio and fecha_termino:
            if fecha_termino <= fecha_inicio:
                self.add_error('fecha_termino', "La fecha de término debe ser posterior a la fecha de inicio.")

        if umbral_regular is not None and umbral_exelencia is not None:
            if umbral_regular >= umbral_exelencia:
                self.add_error('umbral_exelencia', "El umbral de excelencia debe ser mayor al umbral regular.")

        return cleaned_data


class VecinoForm(forms.ModelForm):
    class Meta:
        model = Vecino
        exclude = ['estado']
        widgets = {
            'rut': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 12345678-9', 'maxlength': '12'}),
            'nombres': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Juan Alberto'}),
            'apellido_paterno': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Pérez'}),
            'apellido_materno': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Silva'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: +56912345678'}),
            'correo': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ejemplo@correo.com'}),
        }

    def clean_rut(self):
        rut = self.cleaned_data.get('rut')
        qs = Vecino.objects.filter(rut=rut)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un vecino registrado con este RUT.")
        return rut

    def clean_correo(self):
        correo = self.cleaned_data.get('correo')
        qs = Vecino.objects.filter(correo=correo)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Este correo ya está en uso por otro vecino.")
        return correo