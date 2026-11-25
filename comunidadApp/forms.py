from django import forms
from django.core.exceptions import ValidationError as CoreValidationError
from .models import OrganizacionComunitaria, AfiliacionVecino, CargaFamiliar, VinculoFamiliar, CelebracionDelegacion, BeneficiarioCelebracion
from config.utils import (
    validar_y_formatear_rut,
    validar_texto_no_vacio,
    validar_fecha_no_futura,
    validar_campo_obligatorio_o_sin_datos,
    validar_rango_fechas_organizacion,
    validar_organizacion_matriz,
    validar_fecha_no_pasada,
    limitar_a_opciones_activas,
    configurar_campo_responsable,
)
from datetime import date
from django.core.exceptions import ValidationError
from administracionApp.models import Vecino, Profesional
from django import forms
from django.core.exceptions import ValidationError
from .models import CatalogoCelebracion, Celebracion
from django.db.models import Q



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
            'cargo_organizacion': 'Cargo o Rol en la Organización',
            'fecha_ingreso': 'Fecha de Ingreso',
        }

        widgets = {
            'vecino': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'organizacion': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'cargo_organizacion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Socio, Presidente, Tesorero, Delegado de enlace',
                'maxlength': '100',
                'required': True,
            }),
            'fecha_ingreso': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        vecino_fijo = kwargs.pop('vecino', None)
        delegacion = kwargs.pop('delegacion', None)
        super().__init__(*args, **kwargs)

        if 'organizacion' in self.fields:
            # CA2: Permitir cualquier organización funcional activa de la comuna,
            # más organizaciones territoriales activas (filtradas por delegación si aplica).
            qs_funcionales = OrganizacionComunitaria.objects.filter(
                estado=True,
                tipo=OrganizacionComunitaria.TipoOrganizacion.FUNCIONAL,
            )
            qs_territoriales = OrganizacionComunitaria.objects.filter(
                estado=True,
                tipo=OrganizacionComunitaria.TipoOrganizacion.TERRITORIAL,
            )
            if delegacion:
                qs_territoriales = qs_territoriales.filter(id_delegacion=delegacion)

            qs_orgs = (qs_funcionales | qs_territoriales).distinct()

            if self.instance and self.instance.pk and self.instance.organizacion_id:
                qs_orgs = (
                    qs_orgs | OrganizacionComunitaria.objects.filter(pk=self.instance.organizacion_id)
                ).distinct()

            self.fields['organizacion'].queryset = qs_orgs.order_by('nombre')

        if vecino_fijo and 'vecino' in self.fields:
            self.fields['vecino'].initial = vecino_fijo
            self.fields['vecino'].widget = forms.HiddenInput()

    def clean_cargo_organizacion(self):
        return validar_texto_no_vacio(
            self.cleaned_data.get('cargo_organizacion'),
            "El cargo o rol en la organización",
        )

    def clean_fecha_ingreso(self):
        fecha = self.cleaned_data.get('fecha_ingreso')
        if fecha and fecha > date.today():
            raise forms.ValidationError("La fecha de ingreso no puede ser en el futuro.")
        return fecha

    def clean(self):
        cleaned_data = super().clean()
        vecino = cleaned_data.get('vecino')
        organizacion = cleaned_data.get('organizacion')

        if vecino and organizacion:
            qs = AfiliacionVecino.objects.filter(vecino=vecino, organizacion=organizacion, estado=True)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    "Este vecino ya se encuentra afiliado y activo en esta organización."
                )

        if vecino and organizacion:
            instancia_temp = AfiliacionVecino(
                pk=self.instance.pk if self.instance else None,
                vecino=vecino,
                organizacion=organizacion,
                cargo_organizacion=cleaned_data.get('cargo_organizacion', ''),
                fecha_ingreso=cleaned_data.get('fecha_ingreso'),
                estado=True,
            )
            try:
                instancia_temp.clean()
            except CoreValidationError as e:
                if hasattr(e, 'message_dict'):
                    for campo, errores in e.message_dict.items():
                        campo_form = campo if campo in self.fields else None
                        for msg in errores:
                            self.add_error(campo_form, msg)
                else:
                    raise forms.ValidationError(e.messages)

        return cleaned_data


class CargaFamiliarForm(forms.ModelForm):
    class Meta:
        model = CargaFamiliar
        fields = [
            'rut',
            'nombres',
            'apellido_paterno',
            'apellido_materno',
            'fecha_nacimiento',
            'genero',
            'padres_separados',
        ]
        labels = {
            'rut': 'RUT de la Carga',
            'nombres': 'Nombres',
            'apellido_paterno': 'Apellido Paterno',
            'apellido_materno': 'Apellido Materno',
            'fecha_nacimiento': 'Fecha de Nacimiento',
            'genero': 'Género',
            'padres_separados': 'Padres separados',
        }
        widgets = {
            'rut': forms.TextInput(attrs={
                'class': 'form-control borde-guinda',
                'placeholder': 'Ej: 22.333.444-5',
                'id': 'id_rut_carga',
                'autocomplete': 'off',
            }),
            'nombres': forms.TextInput(attrs={
                'class': 'form-control borde-guinda',
                'id': 'id_nombres_carga',
            }),
            'apellido_paterno': forms.TextInput(attrs={
                'class': 'form-control borde-guinda',
                'id': 'id_apellido_paterno_carga',
            }),
            'apellido_materno': forms.TextInput(attrs={
                'class': 'form-control borde-guinda',
                'id': 'id_apellido_materno_carga',
            }),
            'fecha_nacimiento': forms.DateInput(
                format='%Y-%m-%d',
                attrs={
                    'class': 'form-control borde-guinda',
                    'type': 'date',
                    'id': 'id_fecha_nacimiento_carga',
                },
            ),
            'genero': forms.Select(attrs={
                'class': 'form-select borde-guinda',
                'id': 'id_genero_carga',
            }),
            'padres_separados': forms.CheckboxInput(attrs={
                'class': 'form-check-input switch-estado-sgr',
                'role': 'switch',
                'id': 'id_padres_separados_carga',
            }),
        }

    def __init__(self, *args, carga_existente=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.carga_existente = carga_existente

    def clean_rut(self):
        rut_formateado = validar_y_formatear_rut(self.cleaned_data.get('rut'))
        if self.carga_existente is not None:
            return rut_formateado
        qs = CargaFamiliar.objects.filter(rut__iexact=rut_formateado)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                'Ya existe una carga registrada con este RUT.'
            )
        return rut_formateado

    def clean_nombres(self):
        return validar_texto_no_vacio(self.cleaned_data.get('nombres'), 'Los nombres')

    def clean_apellido_paterno(self):
        return validar_texto_no_vacio(self.cleaned_data.get('apellido_paterno'), 'El apellido paterno')

    def clean_fecha_nacimiento(self):
        return validar_fecha_no_futura(self.cleaned_data.get('fecha_nacimiento'))


class VincularCargaForm(forms.ModelForm):
    class Meta:
        model = VinculoFamiliar
        fields = [
            'familiar',
            'parentesco',
            'vive_con_este_vecino',
            'observacion_custodia',
        ]
        labels = {
            'familiar': 'Vecino / Progenitor',
            'parentesco': 'Parentesco',
            'vive_con_este_vecino': 'Vive con este vecino',
            'observacion_custodia': 'Observación de custodia / convivencia',
        }
        widgets = {
            'familiar': forms.Select(attrs={
                'class': 'form-select borde-guinda',
                'id': 'id_familiar_vinculo',
            }),
            'parentesco': forms.TextInput(attrs={
                'class': 'form-control borde-guinda',
                'placeholder': 'Ej: Madre, Padre, Hijo/a, Tutor/a',
                'id': 'id_parentesco_vinculo',
            }),
            'vive_con_este_vecino': forms.CheckboxInput(attrs={
                'class': 'form-check-input switch-estado-sgr',
                'role': 'switch',
                'id': 'id_vive_con_este_vecino_vinculo',
            }),
            'observacion_custodia': forms.TextInput(attrs={
                'class': 'form-control borde-guinda',
                'placeholder': 'Ej: Domicilio principal, fines de semana, custodia compartida...',
                'id': 'id_observacion_custodia_vinculo',
            }),
        }

    def __init__(self, *args, carga_existente=None, vecino_fijo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.carga_existente = carga_existente
        self.vecino_fijo = vecino_fijo

        self.fields['familiar'].queryset = Vecino.objects.filter(estado=True).order_by(
            'nombres', 'apellido_paterno'
        )

        if vecino_fijo is not None:
            self.fields['familiar'].initial = vecino_fijo.pk
            self.fields['familiar'].widget = forms.HiddenInput()

    def clean_parentesco(self):
        return validar_texto_no_vacio(self.cleaned_data.get('parentesco'), 'El parentesco')

    def clean(self):
        cleaned_data = super().clean()
        familiar = self.vecino_fijo or cleaned_data.get('familiar')
        if familiar and self.carga_existente:
            duplicado = VinculoFamiliar.objects.filter(
                familiar=familiar,
                carga=self.carga_existente,
                estado=True,
            )
            if self.instance and self.instance.pk:
                duplicado = duplicado.exclude(pk=self.instance.pk)
            if duplicado.exists():
                raise ValidationError(
                    f'"{familiar}" ya tiene un vínculo activo registrado con la carga "{self.carga_existente}".'
                )
        return cleaned_data


class CatalogoCelebracionForm(forms.ModelForm):
    class Meta:
        model = CatalogoCelebracion
        fields = ['nombre']
        labels = {
            'nombre': 'Nombre del Tipo de Celebración',
        }
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control borde-guinda',
                'placeholder': 'Ej: Navidad, Día del Niño, Fiestas Patrias...',
            }),
        }

    def clean_nombre(self):
        nombre = validar_texto_no_vacio(self.cleaned_data.get('nombre'), 'El nombre')
        qs = CatalogoCelebracion.objects.filter(nombre__iexact=nombre)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('Ya existe un tipo de celebración con ese nombre.')
        return nombre


class CelebracionForm(forms.ModelForm):
    class Meta:
        model = Celebracion
        fields = ['tipo', 'nombre', 'fecha_tentativa', 'descripcion']
        labels = {
            'tipo': 'Tipo de Celebración (Catálogo)',
            'nombre': 'Nombre de la Celebración Global',
            'fecha_tentativa': 'Fecha Tentativa',
            'descripcion': 'Descripción',
        }
        widgets = {
            'tipo': forms.Select(attrs={
                'class': 'form-select borde-guinda',
            }),
            'nombre': forms.TextInput(attrs={
                'class': 'form-control borde-guinda',
                'placeholder': 'Ej: Navidad 2026',
            }),
            'fecha_tentativa': forms.DateInput(
                format='%Y-%m-%d',
                attrs={
                    'class': 'form-control borde-guinda',
                    'type': 'date',
                },
            ),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control borde-guinda',
                'rows': 3,
                'placeholder': 'Lineamientos generales o descripción de la festividad comunal...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        valor_actual = self.instance.tipo_id if (self.instance and self.instance.pk) else None
        limitar_a_opciones_activas(self.fields['tipo'], valor_actual=valor_actual)

    def clean_fecha_tentativa(self):
        fecha = self.cleaned_data.get('fecha_tentativa')
        if fecha and (not self.instance.pk or fecha != self.instance.fecha_tentativa):
            return validar_fecha_no_pasada(fecha, 'La fecha tentativa')
        return fecha


class CelebracionDelegacionForm(forms.ModelForm):
    class Meta:
        model = CelebracionDelegacion
        fields = ['activa', 'fecha_ejecucion', 'lugar']
        labels = {
            'activa': 'Participación activa en esta delegación',
            'fecha_ejecucion': 'Fecha de Ejecución Local',
            'lugar': 'Lugar / Recinto del Evento',
        }
        widgets = {
            'activa': forms.CheckboxInput(attrs={
                'class': 'form-check-input switch-estado-sgr',
                'role': 'switch',
            }),
            'fecha_ejecucion': forms.DateInput(
                format='%Y-%m-%d',
                attrs={
                    'class': 'form-control borde-guinda',
                    'type': 'date',
                },
            ),
            'lugar': forms.TextInput(attrs={
                'class': 'form-control borde-guinda',
                'placeholder': 'Ej: Plaza de Armas, Sede Vecinal Sector 3...',
            }),
        }

    def clean_lugar(self):
        lugar = self.cleaned_data.get('lugar')
        if lugar:
            return validar_texto_no_vacio(lugar, 'El lugar del evento')
        return lugar

    def clean_fecha_ejecucion(self):
        fecha = self.cleaned_data.get('fecha_ejecucion')
        if fecha and (not self.instance.pk or fecha != self.instance.fecha_ejecucion):
            return validar_fecha_no_pasada(fecha, 'La fecha de ejecución local')
        return fecha

    def clean(self):
        cleaned_data = super().clean()
        activa = cleaned_data.get('activa')
        fecha_ejecucion = cleaned_data.get('fecha_ejecucion')
        lugar = cleaned_data.get('lugar')

        if activa and not fecha_ejecucion:
            self.add_error('fecha_ejecucion', 'Debes indicar la fecha de ejecución local para activar el evento en la delegación.')
        if activa and not lugar:
            self.add_error('lugar', 'Debes indicar el lugar o recinto donde se realizará el evento.')

        return cleaned_data



class InscribirBeneficiariosForm(forms.Form):
    vecinos = forms.ModelMultipleChoiceField(
        queryset=Vecino.objects.none(),
        required=False,
        label='Vecinos a Inscribir',
        widget=forms.SelectMultiple(attrs={
            'class': 'form-select borde-guinda',
            'size': '7',
        }),
    )
    cargas_familiares = forms.ModelMultipleChoiceField(
        queryset=CargaFamiliar.objects.none(),
        required=False,
        label='Cargas Familiares a Inscribir',
        widget=forms.SelectMultiple(attrs={
            'class': 'form-select borde-guinda',
            'size': '7',
        }),
    )
    observacion = forms.CharField(
        required=False,
        max_length=255,
        label='Observación General de Inscripción',
        widget=forms.TextInput(attrs={
            'class': 'form-control borde-guinda',
            'placeholder': 'Ej: Inscrito para entrega de regalo navideño...',
        }),
    )

    def __init__(self, *args, celebracion_delegacion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.celebracion_delegacion = celebracion_delegacion

        vecinos_qs = Vecino.objects.filter(estado=True).order_by('nombres', 'apellido_paterno')
        cargas_qs = CargaFamiliar.objects.filter(estado=True).order_by('nombres', 'apellido_paterno')

        self.fields['vecinos'].queryset = vecinos_qs
        self.fields['cargas_familiares'].queryset = cargas_qs
        self.fields['vecinos'].label_from_instance = lambda v: (
            f"{v.nombres} {v.apellido_paterno} {v.apellido_materno or ''} — RUT: {v.rut or 'S/R'}".strip()
        )
        self.fields['cargas_familiares'].label_from_instance = lambda c: (
            f"{c.nombres} {c.apellido_paterno} {c.apellido_materno or ''} — RUT: {c.rut}".strip()
        )

    def clean(self):
        cleaned_data = super().clean()
        vecinos = cleaned_data.get('vecinos')
        cargas = cleaned_data.get('cargas_familiares')
        if not vecinos and not cargas:
            raise ValidationError(
                'Debes seleccionar al menos un vecino o una carga familiar para inscribir.'
            )
        return cleaned_data