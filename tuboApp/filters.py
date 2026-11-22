import re
from datetime import date, timedelta

import django_filters
from django import forms
from django.db.models import F, Q, Value
from django.db.models.functions import Replace, Upper

from administracionApp.models import Profesional
from .models import Compromiso
from config.utils import EtiquetaFuncionarioFiltroMixin


class CompromisoFilter(EtiquetaFuncionarioFiltroMixin, django_filters.FilterSet):
    responsable = django_filters.ModelChoiceFilter(
        field_name='id_funcionario', queryset=Profesional.objects.none(), empty_label='Todos los responsables',
        widget=forms.Select(attrs={'class': 'form-select borde-guinda'}))
    estado = django_filters.ChoiceFilter(
        field_name='estado_progreso', choices=Compromiso.OPCIONES_ESTADO_PROGRESO, empty_label='Todos los estados',
        widget=forms.Select(attrs={'class': 'form-select borde-guinda'}))
    territorio = django_filters.CharFilter(
        field_name='territorio', lookup_expr='icontains',
        widget=forms.TextInput(attrs={'class': 'form-control borde-guinda', 'placeholder': 'Territorio'}))
    desde = django_filters.DateFilter(
        field_name='fecha_comprometida', lookup_expr='gte',
        widget=forms.DateInput(attrs={'class': 'form-control borde-guinda', 'type': 'date'}))
    hasta = django_filters.DateFilter(
        field_name='fecha_comprometida', lookup_expr='lte',
        widget=forms.DateInput(attrs={'class': 'form-control borde-guinda', 'type': 'date'}))
    vencidos = django_filters.BooleanFilter(method='filtrar_vencidos', widget=forms.HiddenInput)
    proximos = django_filters.BooleanFilter(method='filtrar_proximos', widget=forms.HiddenInput)

    class Meta:
        model = Compromiso
        fields = []

    def filtrar_vencidos(self, queryset, name, value):
        if value:
            return queryset.filter(fecha_comprometida__lt=date.today()).exclude(estado_progreso='REALIZADO')
        return queryset

    def filtrar_proximos(self, queryset, name, value):
        if value:
            from monitoreoApp.services import dias_aviso_vencimiento
            hoy = date.today()
            limite = hoy + timedelta(days=dias_aviso_vencimiento(hoy))
            return queryset.filter(fecha_comprometida__gte=hoy, fecha_comprometida__lte=limite).exclude(estado_progreso='REALIZADO')
        return queryset

    def __init__(self, *args, responsables=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters['responsable'].queryset = responsables if responsables is not None else Profesional.objects.order_by('nombres')


def _rut_limpio(campo):
    return Upper(Replace(Replace(F(campo), Value('.'), Value('')), Value('-'), Value('')))


def buscar_compromisos(queryset, texto):
    """Busca por código, problema, territorio, RUT (con o sin puntos y guion) o nombre del solicitante."""
    texto = (texto or '').strip()
    if not texto:
        return queryset
    filtro = (Q(id_actividad__codigo_unico__icontains=texto) | Q(id_actividad__solicitud_problema__icontains=texto)
              | Q(territorio__icontains=texto))
    rut = re.sub(r'[^0-9kK]', '', texto).upper()
    if len(rut) >= 3 and any(c.isdigit() for c in rut):
        queryset = queryset.annotate(rut_vecino=_rut_limpio('id_actividad__solicitante_vecino__rut'),
                                     rut_profesional=_rut_limpio('id_actividad__solicitante_profesional__rut'))
        filtro |= Q(rut_vecino__contains=rut) | Q(rut_profesional__contains=rut)
    nombre = Q()
    for palabra in texto.split():
        coincide = Q()
        for solicitante in ('solicitante_vecino', 'solicitante_profesional'):
            for campo in ('nombres', 'apellido_paterno', 'apellido_materno'):
                coincide |= Q(**{f'id_actividad__{solicitante}__{campo}__icontains': palabra})
        nombre &= coincide
    return queryset.filter(filtro | nombre).distinct()
