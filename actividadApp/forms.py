from django import forms
from django.db.models import Q
from .models import Actividad, Evidencia, Validacion, Ausencia, Retroalimentacion, GestionActividad
from config.utils import (
    validar_texto_no_vacio, 
    validar_fecha_no_futura, 
    validar_profesionales_distintos, 
    validar_que_sea_delegado, 
    validar_entero_positivo, 
    limitar_a_opciones_activas,
    validar_imagen_evidencia,
    validar_datos_vecino_actividad, 
    validar_tope_diario_actividades,
    validar_cierre_semanal,
    validar_periodo_abierto,
    validar_rango_fechas,
    validar_meta_corresponde_a_profesional
    # <-- Validador modular de imágenes
)
from datetime import date
from administracionApp.models import Periodo, Profesional
from django.core.exceptions import ObjectDoesNotExist, ValidationError as CoreValidationError
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from monitoreoApp.models import Meta
from config.utils import EtiquetaFuncionarioMixin, etiquetar_funcionarios
from config.utils import configurar_campo_responsable

def etiqueta_meta(meta):
    try:
        item = meta.id_cargo_item.id_item.nombre
    except ObjectDoesNotExist:
        item = f'Meta #{meta.pk}'
    return f"{item} — {meta.valor_objetivo} {meta.unidad} ({meta.id_periodo.nombre})"

MENSAJE_TUBO_SIN_ORGANIZACION = 'Para generar un compromiso en el Tubo, selecciona la organización comunitaria.'


class ActividadProfesionalForm(EtiquetaFuncionarioMixin, forms.ModelForm):
    class Meta:
        model = Actividad
        exclude = ['fecha_registro', 'codigo_unico', 'estado', 'id_profesional']

        widgets = {
            'fecha_finalizacion': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_comprometida': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'solicitud_problema': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Detalle la solicitud o problema...'}),
            'accion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Detalle la acción realizada...'}),
            'es_coordinacion_preparatoria': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
                'style': 'width: 3em; height: 1.5em; cursor: pointer;'
            }),
            'en_tubo': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
                'style': 'width: 3em; height: 1.5em; cursor: pointer;'
            }),
            'estado_progreso': forms.Select(attrs={'class': 'form-select'}),
            'solicitante_profesional': forms.Select(attrs={'class': 'form-select'}),
            'solicitante_vecino': forms.Select(attrs={'class': 'form-select'}),
            'id_meta': forms.Select(attrs={'class': 'form-select'}),
            'id_organizacion': forms.Select(attrs={'class': 'form-select'}),
        }

        labels = {
            'fecha_finalizacion': 'Fecha de Realización de la Gestión',
            'fecha_comprometida': 'Fecha Comprometida (Si pasa al Tubo)',
            'solicitante_vecino': 'Vecino Solicitante',
            'solicitante_profesional': 'Profesional Solicitante (Interno)',
            'id_meta': 'Meta Asociada',
            'id_organizacion': 'Organización Comunitaria',
            'solicitud_problema': 'Problema o Solicitud Inicial',
            'accion': 'Acción Realizada',
            'en_tubo': '¿Genera compromiso en el Tubo?',
            'estado_progreso': 'Estado de Progreso',
        }

    def __init__(self, *args, **kwargs):
        self.usuario_actual = kwargs.pop('usuario_actual', None)
        super().__init__(*args, **kwargs)
        self.profesional_real = getattr(self.usuario_actual, 'profesional', None) if self.usuario_actual else None
        if self.usuario_actual and not self.profesional_real:
            self.profesional_real = Profesional.objects.filter(usuario=self.usuario_actual).first()

        if 'id_meta' in self.fields:
            self.fields['id_meta'].label_from_instance = etiqueta_meta

        if self.profesional_real:
            if 'id_meta' in self.fields and getattr(self.profesional_real, 'id_cargo_id', None):
                filtro_meta = Q(
                    estado=True,
                    id_cargo_item__estado=True,
                    id_cargo_item__id_cargo=self.profesional_real.id_cargo_id
                )
                if self.instance and self.instance.pk and self.instance.id_meta_id:
                    filtro_meta |= Q(pk=self.instance.id_meta_id)
                self.fields['id_meta'].queryset = (
                    self.fields['id_meta'].queryset
                    .filter(filtro_meta)
                    .select_related('id_cargo_item__id_item', 'id_periodo')
                    .distinct()
                )

            if 'solicitante_profesional' in self.fields and getattr(self.profesional_real, 'id_delegacion_id', None):
                self.fields['solicitante_profesional'].queryset = Profesional.objects.filter(
                    id_delegacion=self.profesional_real.id_delegacion_id,
                    estado=True,
                    usuario__groups__name='Profesional'
                ).distinct().order_by('nombres')

        if 'id_organizacion' in self.fields:
            valor_actual_org = (
                self.instance.id_organizacion_id
                if self.instance and self.instance.pk and self.instance.id_organizacion_id
                else None
            )
            limitar_a_opciones_activas(self.fields['id_organizacion'], valor_actual_org)
            if self.profesional_real and getattr(self.profesional_real, 'id_delegacion_id', None):
                filtro_org = Q(estado=True, id_delegacion_id=self.profesional_real.id_delegacion_id)
                if valor_actual_org is not None:
                    filtro_org |= Q(pk=valor_actual_org)
                self.fields['id_organizacion'].queryset = (
                    self.fields['id_organizacion'].queryset.filter(filtro_org).distinct().order_by('nombre')
                )

        hoy = timezone.localdate()
        limite = hoy - timedelta(days=7 if hoy.weekday() == 0 else hoy.weekday())
        self.fields['fecha_finalizacion'].widget.attrs['min'] = limite.strftime('%Y-%m-%d')

    def _ejecutar_validacion(self, campo, fn, *args):
        try:
            fn(*args)
        except CoreValidationError as e:
            msg = str(e.message if hasattr(e, 'message') else e.messages[0])
            self.add_error(campo, msg)

    def clean_id_organizacion(self):
        org = self.cleaned_data.get('id_organizacion')
        if org and not org.estado:
            es_misma_instancia = (
                self.instance and self.instance.pk and self.instance.id_organizacion_id == org.pk
            )
            if not es_misma_instancia:
                raise forms.ValidationError("No puedes seleccionar una organización comunitaria inactiva.")
        return org

    def clean(self):
        cleaned_data = super().clean()
        vecino = cleaned_data.get('solicitante_vecino')
        fecha_finalizacion = cleaned_data.get('fecha_finalizacion')
        fecha_comprometida = cleaned_data.get('fecha_comprometida')
        meta = cleaned_data.get('id_meta')
        en_tubo = cleaned_data.get('en_tubo')

        if meta:
            if (
                self.profesional_real
                and getattr(self.profesional_real, 'id_cargo_id', None)
                and getattr(meta.id_cargo_item, 'id_cargo_id', None) != self.profesional_real.id_cargo_id
            ):
                self.add_error('id_meta', "La meta seleccionada no corresponde a tu cargo.")
            self._ejecutar_validacion('id_meta', validar_periodo_abierto, meta)

        if vecino:
            self._ejecutar_validacion('solicitante_vecino', validar_datos_vecino_actividad, vecino)

        if self.usuario_actual:
            objetivo_tope = self.profesional_real or self.usuario_actual
            self._ejecutar_validacion(None, validar_tope_diario_actividades, objetivo_tope)

        if fecha_finalizacion:
            self._ejecutar_validacion('fecha_finalizacion', validar_cierre_semanal, fecha_finalizacion)

        if en_tubo and not fecha_comprometida:
            self.add_error('fecha_comprometida', "Si la actividad genera un compromiso en el Tubo, debe indicar una fecha comprometida.")

        if en_tubo and not cleaned_data.get('id_organizacion'):
            self.add_error('id_organizacion', MENSAJE_TUBO_SIN_ORGANIZACION)

        if fecha_comprometida and fecha_finalizacion:
            self._ejecutar_validacion('fecha_comprometida', validar_rango_fechas, fecha_finalizacion, fecha_comprometida)

        return cleaned_data

    def save(self, commit=True):
        instancia = super().save(commit=False)
        if self.profesional_real:
            instancia.id_profesional = self.profesional_real
        if commit:
            instancia.save()
            self.save_m2m()
        return instancia


    
class ActividadForm(EtiquetaFuncionarioMixin, forms.ModelForm):
    class Meta:
        model = Actividad
        exclude = ['codigo_unico', 'estado']

        widgets = {
            'solicitud_problema': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe el problema o solicitud...'}),
            'accion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe la acción realizada o a tomar...'}),
            'solicitante_profesional': forms.Select(attrs={'class': 'form-select'}),
            'solicitante_vecino': forms.Select(attrs={'class': 'form-select'}),
            'estado_progreso': forms.Select(attrs={'class': 'form-select'}),
            'es_coordinacion_preparatoria': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'en_tubo': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'id_profesional': forms.Select(attrs={'class': 'form-select'}),
            'id_meta': forms.Select(attrs={'class': 'form-select'}),
            'id_organizacion': forms.Select(attrs={'class': 'form-select'}),

            'fecha_comprometida': forms.DateInput(
                format='%d-%m-%Y',
                attrs={
                    'type': 'date',
                    'class': 'form-control'
                }
            ),
            'fecha_finalizacion': forms.DateInput(
                format='%d-%m-%Y',
                attrs={
                    'type': 'date',
                    'class': 'form-control'
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = date.today()
        filtro = Q(id_periodo__estado=True, id_periodo__fecha_inicio__lte=hoy, id_periodo__fecha_termino__gte=hoy)
        if self.instance.pk and self.instance.id_meta_id:
            filtro |= Q(pk=self.instance.id_meta_id)
        self.fields['id_meta'].queryset = self.fields['id_meta'].queryset.filter(filtro)
        self.fields['id_meta'].label_from_instance = etiqueta_meta

        if 'id_organizacion' in self.fields:
            valor_actual_org = (
                self.instance.id_organizacion_id
                if self.instance and self.instance.pk and self.instance.id_organizacion_id
                else None
            )
            limitar_a_opciones_activas(self.fields['id_organizacion'], valor_actual_org)

        if 'id_profesional' in self.fields:
            configurar_campo_responsable(self.fields['id_profesional'])

    def clean_id_meta(self):
        meta = self.cleaned_data.get('id_meta')
        if meta and not meta.id_periodo.esta_vigente:
            raise forms.ValidationError(
                f'El período "{meta.id_periodo.nombre}" de esta meta no está vigente (cerrado o fuera de fecha). '
                'No se pueden registrar ni modificar actividades en él.'
            )
        return meta

    def clean_id_organizacion(self):
        org = self.cleaned_data.get('id_organizacion')
        if org and not org.estado:
            es_misma_instancia = (
                self.instance and self.instance.pk and self.instance.id_organizacion_id == org.pk
            )
            if not es_misma_instancia:
                raise forms.ValidationError("No puedes seleccionar una organización comunitaria inactiva.")
        return org

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('en_tubo') and not cleaned_data.get('id_organizacion') and 'id_organizacion' not in self.errors:
            self.add_error('id_organizacion', MENSAJE_TUBO_SIN_ORGANIZACION)
        return cleaned_data

    
class ActividadForm(EtiquetaFuncionarioMixin, forms.ModelForm):
    class Meta:
        model = Actividad
        exclude = ['codigo_unico', 'estado']

        widgets = {
            'solicitud_problema': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe el problema o solicitud...'}),
            'accion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe la acción realizada o a tomar...'}),
            'solicitante_profesional': forms.Select(attrs={'class': 'form-select'}),
            'solicitante_vecino': forms.Select(attrs={'class': 'form-select'}),
            'estado_progreso': forms.Select(attrs={'class': 'form-select'}),
            'es_coordinacion_preparatoria': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'en_tubo': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'id_profesional': forms.Select(attrs={'class': 'form-select'}),
            'id_meta': forms.Select(attrs={'class': 'form-select'}),
            'id_organizacion': forms.Select(attrs={'class': 'form-select'}),
            'fecha_comprometida': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'fecha_finalizacion': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date', 'class': 'form-control'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = date.today()
        filtro = Q(
            estado=True,
            id_cargo_item__estado=True,
            id_periodo__estado=True,
            id_periodo__fecha_inicio__lte=hoy,
            id_periodo__fecha_termino__gte=hoy,
        )
        if self.instance.pk and self.instance.id_meta_id:
            filtro |= Q(pk=self.instance.id_meta_id)
        self.fields['id_meta'].queryset = (
            self.fields['id_meta'].queryset
            .filter(filtro)
            .select_related('id_cargo_item__id_item', 'id_periodo')
            .distinct()
        )
        self.fields['id_meta'].label_from_instance = etiqueta_meta

        if 'id_organizacion' in self.fields:
            valor_actual_org = (
                self.instance.id_organizacion_id
                if self.instance and self.instance.pk and self.instance.id_organizacion_id
                else None
            )
            limitar_a_opciones_activas(self.fields['id_organizacion'], valor_actual_org)

        if 'id_profesional' in self.fields:
            configurar_campo_responsable(self.fields['id_profesional'])

    def clean_id_meta(self):
        meta = self.cleaned_data.get('id_meta')
        if meta and not meta.id_periodo.esta_vigente:
            raise forms.ValidationError(
                f'El período "{meta.id_periodo.nombre}" de esta meta no está vigente (cerrado o fuera de fecha). '
                'No se pueden registrar ni modificar actividades en él.'
            )
        return meta

    def clean_id_organizacion(self):
        org = self.cleaned_data.get('id_organizacion')
        if org and not org.estado:
            es_misma_instancia = (
                self.instance and self.instance.pk and self.instance.id_organizacion_id == org.pk
            )
            if not es_misma_instancia:
                raise forms.ValidationError("No puedes seleccionar una organización comunitaria inactiva.")
        return org

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('en_tubo') and not cleaned_data.get('id_organizacion') and 'id_organizacion' not in self.errors:
            self.add_error('id_organizacion', MENSAJE_TUBO_SIN_ORGANIZACION)

        try:
            validar_meta_corresponde_a_profesional(
                cleaned_data.get('id_profesional'),
                cleaned_data.get('id_meta'),
            )
        except CoreValidationError as e:
            msg = str(e.message if hasattr(e, 'message') else e.messages[0])
            self.add_error('id_meta', msg)

        return cleaned_data


class ActividadDelegadoForm(ActividadForm):
    def __init__(self, *args, **kwargs):
        delegacion = kwargs.pop('delegacion', None)
        super().__init__(*args, **kwargs)

        if delegacion:
            profesionales_equipo = Profesional.objects.filter(
                id_delegacion=delegacion,
                estado=True,
                usuario__groups__name='Profesional'
            ).distinct().order_by('nombres')

            if 'id_profesional' in self.fields:
                self.fields['id_profesional'].queryset = profesionales_equipo
                configurar_campo_responsable(self.fields['id_profesional'])
            if 'solicitante_profesional' in self.fields:
                self.fields['solicitante_profesional'].queryset = profesionales_equipo

            if 'id_organizacion' in self.fields:
                valor_actual_org = (
                    self.instance.id_organizacion_id
                    if self.instance and self.instance.pk and self.instance.id_organizacion_id
                    else None
                )
                filtro_org = Q(estado=True, id_delegacion_id=delegacion.pk if hasattr(delegacion, 'pk') else delegacion)
                if valor_actual_org is not None:
                    filtro_org |= Q(pk=valor_actual_org)
                self.fields['id_organizacion'].queryset = (
                    self.fields['id_organizacion'].queryset.filter(filtro_org).distinct().order_by('nombre')
                )

    def datos_filtro_metas(self):
        """Entrega el mapa profesional->cargo y meta->cargo para filtrar en el navegador."""
        profesionales_cargo = {
            str(p.pk): p.id_cargo_id
            for p in self.fields['id_profesional'].queryset
        }
        metas_cargo = {
            str(m.pk): m.id_cargo_item.id_cargo_id
            for m in self.fields['id_meta'].queryset
            if m.id_cargo_item_id
        }
        return {
            'profesionales_cargo': profesionales_cargo,
            'metas_cargo': metas_cargo,
        }
    
class AusenciaForm(EtiquetaFuncionarioMixin, forms.ModelForm):
    class Meta:
        model = Ausencia
        fields = ['profesional_ausente', 'periodo_ausencia', 'tipo_ausencia', 'fecha_inicio', 'fecha_termino', 'dias_computables']

        labels = {
            'tipo_ausencia': 'Tipo de Ausencia / Permiso',
            'fecha_inicio': 'Fecha de Inicio',
            'fecha_termino': 'Fecha de Término',
            'dias_computables': 'Días hábiles de ausencia',
            'profesional_ausente': 'Profesional / Funcionario Ausente',
            'periodo_ausencia': 'Periodo Asociado',
        }

        widgets = {
            'tipo_ausencia': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'fecha_inicio': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date', 'required': True}),
            'fecha_termino': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date', 'required': True}),
            'dias_computables': forms.NumberInput(attrs={'class': 'form-control bg-light text-muted fw-bold', 'readonly': 'readonly', 'style': 'cursor: not-allowed;'}),
            'profesional_ausente': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'periodo_ausencia': forms.Select(attrs={'class': 'form-select', 'required': True}),
        }

    def __init__(self, *args, delegacion=None, **kwargs):
        super().__init__(*args, **kwargs)
        profesionales = Profesional.objects.filter(estado=True)
        if delegacion is not None:
            profesionales = profesionales.filter(id_delegacion=delegacion)
        self.fields['profesional_ausente'].queryset = profesionales.order_by('nombres', 'apellido_paterno')
        etiquetar_funcionarios(self.fields)
        abiertos = [p.pk for p in Periodo.objects.filter(estado=True) if p.esta_abierto]
        self.fields['periodo_ausencia'].queryset = Periodo.objects.filter(pk__in=abiertos).order_by('-fecha_inicio')
        self.fields['tipo_ausencia'].choices = [('', 'Seleccione el tipo de ausencia')] + Ausencia.OPCIONES_TIPO
        self.fields['dias_computables'].required = False
        self.fields['dias_computables'].disabled = True
        self.fields['dias_computables'].help_text = 'Se calcula automáticamente con los días hábiles del rango.'

    @staticmethod
    def se_superpone(ausencia):
        otras = Ausencia.objects.filter(
            profesional_ausente=ausencia.profesional_ausente, estado=True,
            fecha_inicio__lte=ausencia.fecha_termino, fecha_termino__gte=ausencia.fecha_inicio,
        )
        if ausencia.pk:
            otras = otras.exclude(pk=ausencia.pk)
        return otras.exists()

    def clean(self):
        cleaned_data = super().clean()
        f_inicio = cleaned_data.get('fecha_inicio')
        f_termino = cleaned_data.get('fecha_termino')
        periodo = cleaned_data.get('periodo_ausencia')
        profesional = cleaned_data.get('profesional_ausente')

        if not (f_inicio and f_termino):
            return cleaned_data
        if f_termino < f_inicio:
            self.add_error('fecha_termino', "La fecha de término no puede ser anterior a la fecha de inicio.")
            return cleaned_data
        if periodo and (f_inicio < periodo.fecha_inicio or f_termino > periodo.fecha_termino):
            self.add_error('fecha_termino', f"Las fechas deben estar dentro del período {periodo.nombre} "
                                            f"({periodo.fecha_inicio:%d/%m/%Y} al {periodo.fecha_termino:%d/%m/%Y}).")
            return cleaned_data
        dias = Periodo.calcular_dias_computables(f_inicio, f_termino)
        if dias == 0:
            self.add_error('fecha_termino', "El rango seleccionado no incluye días hábiles.")
            return cleaned_data
        if profesional:
            candidata = Ausencia(pk=self.instance.pk, profesional_ausente=profesional, fecha_inicio=f_inicio, fecha_termino=f_termino)
            if self.se_superpone(candidata):
                self.add_error('fecha_inicio', "El funcionario ya tiene otra ausencia activa que se cruza con estas fechas.")
        cleaned_data['dias_computables'] = dias
        self.instance.dias_computables = dias
        return cleaned_data



class RetroalimentacionForm(EtiquetaFuncionarioMixin, forms.ModelForm):
    class Meta:
        model = Retroalimentacion
        exclude = ['estado', 'receptor']

        labels = {
            'tipo': 'Tipo de Registro',
            'porcentaje_impacto': 'Porcentaje de Impacto en Indicador (%)',
            'canal_recepcion': 'Canal de Recepción',
            'fecha': 'Fecha de Recepción',
            'retroalimentado': 'Profesional del Equipo',
            'vecino': 'Vecino Solicitante (Opcional)',
            'delegacion': 'Delegación',
            'meta': 'Meta Asociada',
            'archivo_respaldo': 'Respaldo Formal (Imagen)',
        }

        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'porcentaje_impacto': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'max': '30.00',
                'placeholder': 'Ej: 10.00',
                'required': True,
            }),
            'canal_recepcion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Oficina de Partes / Carta / Presencial en delegación',
                'maxlength': '100',
                'required': True,
            }),
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': True}),
            'retroalimentado': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'vecino': forms.Select(attrs={'class': 'form-select'}),
            'delegacion': forms.Select(attrs={'class': 'form-select'}),
            'meta': forms.Select(attrs={'class': 'form-select'}),
            'archivo_respaldo': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/jpeg,image/png,image/webp',
                'required': True,
            }),
        }

    def __init__(self, *args, **kwargs):
        delegacion = kwargs.pop('delegacion', None)
        super().__init__(*args, **kwargs)
        self.fields['archivo_respaldo'].required = True
        self.fields['meta'].label_from_instance = etiqueta_meta

        qs_profesionales = Profesional.objects.filter(estado=True)
        if delegacion:
            qs_profesionales = qs_profesionales.filter(id_delegacion=delegacion)
            self.fields['delegacion'].initial = delegacion
        self.fields['retroalimentado'].queryset = qs_profesionales.order_by('nombres', 'apellido_paterno')

        prof_id = (
            self.data.get(self.add_prefix('retroalimentado'))
            if self.is_bound
            else getattr(self.instance, 'retroalimentado_id', None) or self.initial.get('retroalimentado')
        )

        qs_metas = Meta.objects.filter(
            estado=True,
            id_cargo_item__estado=True,
        ).select_related('id_cargo_item__id_cargo', 'id_cargo_item__id_item', 'id_periodo')

        if prof_id and str(prof_id).isdigit():
            prof_obj = qs_profesionales.filter(pk=int(prof_id)).first()
            if prof_obj and prof_obj.id_cargo_id:
                filtro_meta = Q(id_cargo_item__id_cargo_id=prof_obj.id_cargo_id)
                if self.instance and self.instance.pk and self.instance.meta_id:
                    filtro_meta |= Q(pk=self.instance.meta_id)
                qs_metas = qs_metas.filter(filtro_meta).distinct()

        self.fields['meta'].queryset = qs_metas.order_by('-id_meta')
        etiquetar_funcionarios(self.fields)

    def clean(self):
        cleaned_data = super().clean()
        try:
            validar_meta_corresponde_a_profesional(
                cleaned_data.get('retroalimentado'),
                cleaned_data.get('meta'),
            )
        except CoreValidationError as e:
            msg = str(e.message if hasattr(e, 'message') else e.messages[0])
            self.add_error('meta', msg)
        return cleaned_data

    def clean_porcentaje_impacto(self):
        valor = self.cleaned_data.get('porcentaje_impacto')
        if valor is None or valor <= Decimal('0.00'):
            raise forms.ValidationError("Debe indicar un porcentaje de impacto mayor a 0%.")
        if valor > Decimal('30.00'):
            raise forms.ValidationError("El porcentaje de impacto no puede superar el 30%.")
        return valor

    def clean_canal_recepcion(self):
        return validar_texto_no_vacio(self.cleaned_data.get('canal_recepcion'), "El canal de recepción")

    def clean_fecha(self):
        return validar_fecha_no_futura(self.cleaned_data.get('fecha'))

    def clean_archivo_respaldo(self):
        archivo = self.cleaned_data.get('archivo_respaldo')
        if not archivo:
            raise forms.ValidationError("Debe adjuntar una imagen de respaldo formal.")
        return validar_imagen_evidencia(archivo)
    def clean_porcentaje_impacto(self):
        valor = self.cleaned_data.get('porcentaje_impacto')
        if valor is None or valor <= Decimal('0.00'):
            raise forms.ValidationError("Debe indicar un porcentaje de impacto mayor a 0%.")
        if valor > Decimal('30.00'):
            raise forms.ValidationError("El porcentaje de impacto no puede superar el 30%.")
        return valor

    def clean_canal_recepcion(self):
        return validar_texto_no_vacio(self.cleaned_data.get('canal_recepcion'), "El canal de recepción")

    def clean_fecha(self):
        return validar_fecha_no_futura(self.cleaned_data.get('fecha'))

    def clean_archivo_respaldo(self):
        archivo = self.cleaned_data.get('archivo_respaldo')
        if not archivo:
            raise forms.ValidationError("Debe adjuntar una imagen de respaldo formal.")
        return validar_imagen_evidencia(archivo)
    
class EvidenciaForm(forms.ModelForm):
    class Meta:
        model = Evidencia
        exclude = ['estado', 'metadatos', 'estado_revision', 'id_actividad']
        
        labels = {
            'archivo_foto': 'Fotografía de Evidencia',
            'id_actividad': 'Actividad Asociada',
        }
        
        widgets = {
            'archivo_foto': forms.ClearableFileInput(attrs={'class': 'form-control', 'required': True}),
            'id_actividad': forms.Select(attrs={'class': 'form-select', 'required': True}),
        }

    def clean_archivo_foto(self):
        archivo = self.cleaned_data.get('archivo_foto')
        return validar_imagen_evidencia(archivo)



class ValidacionForm(EtiquetaFuncionarioMixin, forms.ModelForm):
    class Meta:
        model = Validacion
        exclude = ['estado', 'resultado']
        
        labels = {
            'decision': 'Decisión de Validación',
            'observacion': 'Observaciones (Opcional)',
            'version': 'Versión',
            'id_evidencia': 'Evidencia Asociada',
            'id_validador': 'Profesional Validador',
        }
        
        widgets = {
            'decision': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'observacion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Detalles o comentarios de la validación...'}),
            'version': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'required': True}),
            # Los hacemos ocultos o de solo lectura para que se autocomlenen de forma segura
            'id_evidencia': forms.HiddenInput(),
            'id_validador': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['id_evidencia'].queryset = Evidencia.objects.select_related('id_actividad').all()
        self.fields['id_evidencia'].label_from_instance = lambda obj: f"Evidencia #{obj.pk} - {obj.id_actividad.codigo_unico}"

    def clean_version(self):
        version = self.cleaned_data.get('version')
        return validar_entero_positivo(version, "La versión")



class GestionActividadForm(forms.ModelForm):
    class Meta:
        model = GestionActividad
        fields = ['tipo_gestion', 'subtipo_gestion', 'fecha_ejecucion', 'descripcion']
        
        widgets = {
            'tipo_gestion': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'subtipo_gestion': forms.Select(attrs={'class': 'form-select'}),
            'fecha_ejecucion': forms.DateInput(attrs={
                'class': 'form-control', 
                'type': 'date'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 4, 
                'placeholder': 'Detalla las acciones realizadas durante esta gestión...'
            }),
        }
        
        labels = {
            'tipo_gestion': 'Tipo de Gestión (*)',
            'subtipo_gestion': 'Subtipo de Gestión',
            'fecha_ejecucion': 'Fecha de Ejecución (Opcional)',
            'descripcion': 'Descripción Detallada (*)'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limitar_a_opciones_activas(self.fields['tipo_gestion'], self.instance.tipo_gestion_id)
        limitar_a_opciones_activas(self.fields['subtipo_gestion'], self.instance.subtipo_gestion_id)
        self.fields['subtipo_gestion'].queryset = self.fields['subtipo_gestion'].queryset.select_related('tipo_gestion')
        self.fields['subtipo_gestion'].empty_label = 'Sin subtipo'

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo_gestion')
        subtipo = cleaned_data.get('subtipo_gestion')
        if tipo and subtipo and subtipo.tipo_gestion_id != tipo.pk:
            self.add_error('subtipo_gestion', f'El subtipo "{subtipo.nombre}" no pertenece al tipo de gestión "{tipo.nombre}".')
        return cleaned_data