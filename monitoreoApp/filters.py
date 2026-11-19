import django_filters
from django import forms
from django.db.models import Q

from administracionApp.models import Cargo, CargoItem, CatalagoItem, Periodo
from .models import Meta

SELECT = {'class': 'form-select borde-guinda'}


class MetaFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='buscar_texto',
        label='Buscar',
        widget=forms.TextInput(attrs={
            'class': 'form-control borde-guinda',
            'placeholder': 'Unidad, cargo o ítem...',
        }),
    )
    periodo = django_filters.ModelChoiceFilter(
        field_name='id_periodo',
        label='Período',
        queryset=Periodo.objects.order_by('-fecha_inicio'),
        empty_label='Todos los períodos',
        widget=forms.Select(attrs=SELECT),
    )
    cargo = django_filters.ModelChoiceFilter(
        field_name='id_cargo_item__id_cargo',
        label='Cargo',
        queryset=Cargo.objects.filter(estado=True).order_by('nombre'),
        empty_label='Todos los cargos',
        widget=forms.Select(attrs=SELECT),
    )
    item = django_filters.ModelChoiceFilter(
        field_name='id_cargo_item__id_item',
        label='Ítem',
        queryset=CatalagoItem.objects.filter(estado=True).order_by('nombre'),
        empty_label='Todos los ítems',
        widget=forms.Select(attrs=SELECT),
    )

    class Meta:
        model = Meta
        fields = []

    def __init__(self, *args, ocultar=(), **kwargs):
        super().__init__(*args, **kwargs)
        for nombre in ocultar:
            if nombre in self.filters:
                self.filters.pop(nombre)

    def buscar_texto(self, queryset, name, value):
        return queryset.filter(
            Q(unidad__icontains=value)
            | Q(id_cargo_item__id_cargo__nombre__icontains=value)
            | Q(id_cargo_item__id_item__nombre__icontains=value)
        ).distinct()
