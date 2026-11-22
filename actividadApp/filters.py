from datetime import timedelta

import django_filters
from django import forms
from django.db.models import Q

from administracionApp.models import CatalagoItem, Delegacion, Periodo, Profesional
from config.utils import inicio_del_dia
from .models import Actividad
from config.utils import EtiquetaFuncionarioFiltroMixin

SELECT = {'class': 'form-select borde-guinda'}
FECHA = {'class': 'form-control borde-guinda', 'type': 'date'}


class ActividadFilter(EtiquetaFuncionarioFiltroMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='buscar_texto', label='Buscar',
        widget=forms.TextInput(attrs={'class': 'form-control borde-guinda', 'placeholder': 'Código, problema o acción'}))
    delegacion = django_filters.ModelChoiceFilter(
        field_name='id_profesional__id_delegacion', label='Delegación', queryset=Delegacion.objects.none(),
        empty_label='Todas', widget=forms.Select(attrs=SELECT))
    funcionario = django_filters.ModelChoiceFilter(
        field_name='id_profesional', label='Profesional', queryset=Profesional.objects.none(),
        empty_label='Todos', widget=forms.Select(attrs=SELECT))
    periodo = django_filters.ModelChoiceFilter(
        field_name='id_meta__id_periodo', label='Período', queryset=Periodo.objects.order_by('-fecha_inicio'),
        empty_label='Todos', widget=forms.Select(attrs=SELECT))
    item = django_filters.ModelChoiceFilter(
        field_name='id_meta__id_cargo_item__id_item', label='Ítem', queryset=CatalagoItem.objects.order_by('nombre'),
        empty_label='Todos', widget=forms.Select(attrs=SELECT))
    estado = django_filters.ChoiceFilter(
        field_name='estado_progreso', label='Estado', choices=Actividad.OPCIONES_ESTADO_PROGRESO,
        empty_label='Todos', widget=forms.Select(attrs=SELECT))
    desde = django_filters.DateFilter(
        method='filtrar_desde', label='Desde', widget=forms.DateInput(attrs=FECHA))
    hasta = django_filters.DateFilter(
        method='filtrar_hasta', label='Hasta', widget=forms.DateInput(attrs=FECHA))

    class Meta:
        model = Actividad
        fields = []

    def __init__(self, *args, profesionales=None, ocultar=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.filters['delegacion'].queryset = Delegacion.objects.filter(estado=True).order_by('nombre')
        self.filters['funcionario'].queryset = (
            profesionales if profesionales is not None else Profesional.objects.filter(estado=True)
        ).order_by('nombres')
        for nombre in ocultar:
            self.filters.pop(nombre)

    def filtrar_desde(self, queryset, name, value):
        return queryset.filter(fecha_registro__gte=inicio_del_dia(value))

    def filtrar_hasta(self, queryset, name, value):
        return queryset.filter(fecha_registro__lt=inicio_del_dia(value + timedelta(days=1)))

    def buscar_texto(self, queryset, name, value):
        return queryset.filter(
            Q(codigo_unico__icontains=value) | Q(solicitud_problema__icontains=value) | Q(accion__icontains=value)
        ).distinct()
