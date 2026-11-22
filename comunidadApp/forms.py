from django import forms
from django.core.exceptions import ValidationError as CoreValidationError
from .models import OrganizacionComunitaria, AfiliacionVecino, CargaFamiliar, VinculoFamiliar
from config.utils import (
    validar_y_formatear_rut,
    validar_texto_no_vacio,
    validar_fecha_no_futura,
    validar_campo_obligatorio_o_sin_datos,
    validar_rango_fechas_organizacion,
    validar_organizacion_matriz,
)
from datetime import date

class OrganizacionComunitariaForm(forms.ModelForm):
    class Meta:
        model = OrganizacionComunitaria
        exclude = ['estado']

        labels = {
            'nombre': 'Nombre de la Organización',
            'tipo': 'Clasificación Territorial / Funcional',
            'subtipo': 'Subtipo de Organización',
            'direccion': 'Domicilio',
            'territorio': 'Territorio',
            'socios_activos': 'Socios Activos',
            'fecha_formacion': 'Fecha de Formación',
            'fecha_inscripcion_reg_date': 'Fecha Inscripción Registro',
            'n_reg_pj': 'Número Registro Personalidad Jurídica',
            'n_reg_dir': 'Número Registro Directorio',
            'id_delegacion': 'Delegación Municipal',
            'organizacion_matriz': 'Junta de Vecinos Matriz (Opcional para Comités)',
        }

        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Junta de Vecinos La Pampa',
                'minlength': '2',
                'maxlength': '150',
                'required': True,
            }),
            'tipo': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'subtipo': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'direccion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Pasaje Los Aromos 123',
                'maxlength': '200',
                'required': True,
            }),
            'territorio': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Las Compañías',
                'maxlength': '45',
                'required': True,
            }),
            'socios_activos': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'required': True,
            }),
            'fecha_formacion': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': True,
            }),
            'fecha_inscripcion_reg_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': True,
            }),
            'n_reg_pj': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 3520 o 352-BIS',
                'maxlength': '50',
                'required': True,
            }),
            'n_reg_dir': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 9840',
                'maxlength': '50',
                'required': True,
            }),
            'id_delegacion': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'organizacion_matriz': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        delegacion = kwargs.pop('delegacion', None)
        super().__init__(*args, **kwargs)

        self.campos_faltantes_aviso = (
            self.instance.campos_sin_datos()
            if self.instance and self.instance.pk
            else []
        )

        if 'organizacion_matriz' in self.fields:
            self.fields['organizacion_matriz'].required = False
            qs_juntas = OrganizacionComunitaria.objects.filter(
                subtipo=OrganizacionComunitaria.SubtipoOrganizacion.JUNTA_VECINOS,
                estado=True,
            )
            if delegacion:
                qs_juntas = qs_juntas.filter(id_delegacion=delegacion)
            if self.instance and self.instance.pk:
                qs_juntas = qs_juntas.exclude(pk=self.instance.pk)
                if self.instance.organizacion_matriz_id:
                    qs_juntas = (
                        qs_juntas | OrganizacionComunitaria.objects.filter(pk=self.instance.organizacion_matriz_id)
                    ).distinct()
            self.fields['organizacion_matriz'].queryset = qs_juntas.order_by('nombre')

        if delegacion and 'id_delegacion' in self.fields:
            self.fields['id_delegacion'].queryset = self.fields['id_delegacion'].queryset.filter(pk=delegacion.pk)
            if not (self.instance and self.instance.pk and self.instance.id_delegacion_id):
                self.fields['id_delegacion'].initial = delegacion

    def clean_nombre(self):
        nombre = validar_texto_no_vacio(self.cleaned_data.get('nombre'), "El nombre de la organización")
        qs = OrganizacionComunitaria.objects.filter(nombre__iexact=nombre)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe una organización registrada con este nombre exacto.")
        return nombre

    def clean_direccion(self):
        return validar_campo_obligatorio_o_sin_datos(self.cleaned_data.get('direccion'), "El domicilio")

    def clean_territorio(self):
        return validar_campo_obligatorio_o_sin_datos(self.cleaned_data.get('territorio'), "El territorio")

    def clean_n_reg_pj(self):
        return validar_campo_obligatorio_o_sin_datos(
            self.cleaned_data.get('n_reg_pj'), "El número de registro de personalidad jurídica"
        )

    def clean_n_reg_dir(self):
        return validar_campo_obligatorio_o_sin_datos(
            self.cleaned_data.get('n_reg_dir'), "El número de registro de directorio"
        )

    def clean_socios_activos(self):
        socios = self.cleaned_data.get('socios_activos')
        if socios is None:
            raise forms.ValidationError("La cantidad de socios activos es obligatoria.")
        if socios < 0:
            raise forms.ValidationError("La cantidad de socios no puede ser un número negativo.")
        return socios

    def clean(self):
        cleaned_data = super().clean()

        errores_fechas = validar_rango_fechas_organizacion(
            cleaned_data.get('fecha_formacion'),
            cleaned_data.get('fecha_inscripcion_reg_date'),
        )
        for campo, msg in errores_fechas.items():
            self.add_error(campo, msg)

        try:
            validar_organizacion_matriz(self.instance, cleaned_data.get('organizacion_matriz'))
        except CoreValidationError as e:
            msg = str(e.message if hasattr(e, 'message') else e.messages[0])
            self.add_error('organizacion_matriz', msg)

        return cleaned_data

class AfiliacionVecinoForm(forms.ModelForm):
    class Meta:
        model = AfiliacionVecino
        exclude = ['estado']
        
        labels = {
            'vecino': 'Vecino / Ciudadano',
            'organizacion': 'Organización Comunitaria',
            'cargo_organizacion': 'Cargo en la Organización',
            'fecha_ingreso': 'Fecha de Ingreso',
        }
        
        widgets = {
            'vecino': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'organizacion': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'cargo_organizacion': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Socio, Presidente, Tesorero', 
                'maxlength': '100',
                'required': True
            }),
            'fecha_ingreso': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean_fecha_ingreso(self):
        fecha = self.cleaned_data.get('fecha_ingreso')
        if fecha and fecha > date.today():
            raise forms.ValidationError("La fecha de ingreso no puede ser en el futuro.")
        return fecha

    def clean(self):
        cleaned_data = super().clean()
        vecino = cleaned_data.get('vecino')
        organizacion = cleaned_data.get('organizacion')

        # Evitar duplicidad exacta: Un vecino no puede estar afiliado dos veces a la misma organización de forma activa
        if vecino and organizacion:
            qs = AfiliacionVecino.objects.filter(vecino=vecino, organizacion=organizacion, estado=True)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Este vecino ya se encuentra afiliado y activo en esta organización.")
                
        return cleaned_data





class CargaFamiliarForm(forms.ModelForm):
    class Meta:
        model = CargaFamiliar
        exclude = ['estado']
        
        labels = {
            'rut': 'RUT',
            'nombres': 'Nombres',
            'apellido_paterno': 'Apellido Paterno',
            'apellido_materno': 'Apellido Materno',
            'fecha_nacimiento': 'Fecha de Nacimiento',
        }
        
        widgets = {
            'rut': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 12345678-9', 'maxlength': '12', 'required': True}),
            'nombres': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombres de la carga', 'maxlength': '100', 'required': True}),
            'apellido_paterno': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellido paterno', 'maxlength': '60', 'required': True}),
            'apellido_materno': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellido materno (opcional)', 'maxlength': '60'}),
            'fecha_nacimiento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': True}),
        }

    def clean_rut(self):
        rut_ingresado = self.cleaned_data.get('rut')
        # 1. Validar y formatear por Módulo 11 usando utils global
        rut_formateado = validar_y_formatear_rut(rut_ingresado)
        
        # 2. Control de duplicidad estricta en la base de datos
        qs = CargaFamiliar.objects.filter(rut=rut_formateado)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Este RUT ya se encuentra registrado en el sistema como carga familiar.")
            
        return rut_formateado

    def clean_nombres(self):
        return validar_texto_no_vacio(self.cleaned_data.get('nombres'), "El nombre")

    def clean_apellido_paterno(self):
        return validar_texto_no_vacio(self.cleaned_data.get('apellido_paterno'), "El apellido paterno")

    def clean_fecha_nacimiento(self):
        fecha = self.cleaned_data.get('fecha_nacimiento')
        return validar_fecha_no_futura(fecha)



class VinculoFamiliarForm(forms.ModelForm):
    class Meta:
        model = VinculoFamiliar
        exclude = ['estado']
        
        labels = {
            'carga': 'Carga Familiar',
            'familiar': 'Vecino Titular',
            'parentesco': 'Parentesco',
            'padres_separados': '¿Padres Separados?',
            'vive_con_este_vecino': '¿Vive con este vecino?',
            'observacion_custodia': 'Observación de Custodia (Opcional)',
        }
        
        widgets = {
            'carga': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'familiar': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'parentesco': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Hijo/a, Cónyuge, Tutor', 'maxlength': '50', 'required': True}),
            'padres_separados': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'vive_con_este_vecino': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'observacion_custodia': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Detalle sobre régimen de visitas o custodia si aplica...'}),
        }

    def clean_parentesco(self):
        # Valida que el parentesco no contenga solo espacios en blanco
        return validar_texto_no_vacio(self.cleaned_data.get('parentesco'), "El parentesco")

    def clean(self):
        cleaned_data = super().clean()
        carga = cleaned_data.get('carga')
        familiar = cleaned_data.get('familiar')

        # Evitar duplicidad exacta de vínculo activo
        if carga and familiar:
            qs = VinculoFamiliar.objects.filter(carga=carga, familiar=familiar, estado=True)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Este vínculo familiar entre el titular y la carga ya se encuentra registrado y activo.")
                
        return cleaned_data