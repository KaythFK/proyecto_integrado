from datetime import date

import django_filters
from django import forms

from administracionApp.models import Profesional
from .models import Compromiso


class CompromisoFilter(django_filters.FilterSet):
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

    class Meta:
        model = Compromiso
        fields = []

    def filtrar_vencidos(self, queryset, name, value):
        if value:
            return queryset.filter(fecha_comprometida__lt=date.today()).exclude(estado_progreso='REALIZADO')
        return queryset

    def __init__(self, *args, responsables=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters['responsable'].queryset = responsables if responsables is not None else Profesional.objects.order_by('nombres')
