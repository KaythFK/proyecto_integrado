import re
from datetime import date
from django import forms
from .models import OrganizacionComunitaria, AfiliacionVecino, CargaFamiliar, VinculoFamiliar
from config.utils import validar_y_formatear_rut, validar_texto_no_vacio, validar_fecha_no_futura

# --- FUNCIONES AUXILIARES ---
class OrganizacionComunitariaForm(forms.ModelForm):
    class Meta:
        model = OrganizacionComunitaria
        exclude = ['estado']
        
        labels = {
            'nombre': 'Organizaciones',
            'tipo_marco': 'Clasificación Territorial/Funcional',
            'subtipo': 'Subtipo de Organización',
            'direccion': 'Domicilio',
            'territorio': 'Territorio',
            'socios_activos': 'Socios Activos',
            'fecha_formacion': 'Fecha Creacion',
            'fecha_inscripcion_reg_date': 'Fecha Inscripción Registro',
            'n_reg_pj': 'Numero Registro Personalidad Jurídica',
            'n_reg_dir': 'Numero Registro Directorio',
            'id_delegacion': 'Delegación Municipal (Opcional)',
            'organizacion_matriz': 'Organización Matriz (Solo para Comités)',
        }
        
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Junta de Vecinos La Pampa', 
                'minlength': '4', 
                'maxlength': '150',
                'required': True
            }),
            'tipo_marco': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'subtipo': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Club de Adulto Mayor (Opcional)',
                'maxlength': '100'
            }),
            
            # --- TODO LO DEMÁS ES OPCIONAL (Sin required=True) ---
            'direccion': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '150'}),
            'territorio': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '45'}),
            'socios_activos': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'fecha_formacion': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_inscripcion_reg_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'n_reg_pj': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'n_reg_dir': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'id_delegacion': forms.Select(attrs={'class': 'form-select'}),
            'organizacion_matriz': forms.Select(attrs={'class': 'form-select'}),
        }

    # Hacemos que todos los campos del modelo que eran blank=True sean opcionales en el formulario
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        campos_opcionales = [
            'direccion', 'territorio', 'socios_activos', 
            'fecha_formacion', 'fecha_inscripcion_reg_date', 'n_reg_pj', 
            'n_reg_dir', 'id_delegacion', 'organizacion_matriz'
        ]
        for campo in campos_opcionales:
            self.fields[campo].required = False

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre', '').strip()
        if not nombre:
            raise forms.ValidationError("El nombre de la organización es obligatorio.")
            
        qs = OrganizacionComunitaria.objects.filter(nombre__iexact=nombre)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe una organización registrada con este nombre exacto.")
        return nombre

    def clean_socios_activos(self):
        socios = self.cleaned_data.get('socios_activos')
        if socios is not None and socios < 0:
            raise forms.ValidationError("La cantidad de socios no puede ser un número negativo.")
        return socios

    def clean(self):
        cleaned_data = super().clean()
        fecha_form = cleaned_data.get('fecha_formacion')
        fecha_insc = cleaned_data.get('fecha_inscripcion_reg_date')
        hoy = date.today()

        if fecha_form and fecha_form > hoy:
            self.add_error('fecha_formacion', "La fecha de formación no puede ser en el futuro.")
        
        if fecha_insc and fecha_insc > hoy:
            self.add_error('fecha_inscripcion_reg_date', "La fecha de inscripción no puede ser en el futuro.")
            
        if fecha_form and fecha_insc and fecha_form > fecha_insc:
            self.add_error('fecha_inscripcion_reg_date', "La fecha de inscripción no puede ser anterior a la formación.")
            
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