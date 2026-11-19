import django_filters
from django import forms
from django.db.models import Q

from administracionApp.models import Cargo, CatalagoItem, Periodo
from .models import Meta

SELECT = {'class': 'form-select borde-guinda'}


class MetaFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='buscar_texto', label='Buscar',
        widget=forms.TextInput(attrs={'class': 'form-control borde-guinda', 'placeholder': 'Unidad, ítem o cargo'}))
    cargo = django_filters.ModelChoiceFilter(
        field_name='id_cargo_item__id_cargo', label='Cargo', queryset=Cargo.objects.none(),
        empty_label='Todos', widget=forms.Select(attrs=SELECT))
    periodo = django_filters.ModelChoiceFilter(
        field_name='id_periodo', label='Período', queryset=Periodo.objects.order_by('-fecha_inicio'),
        empty_label='Todos', widget=forms.Select(attrs=SELECT))
    item = django_filters.ModelChoiceFilter(
        field_name='id_cargo_item__id_item', label='Ítem', queryset=CatalagoItem.objects.order_by('nombre'),
        empty_label='Todos', widget=forms.Select(attrs=SELECT))

    class Meta:
        model = Meta
        fields = []

    def __init__(self, *args, cargos=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters['cargo'].queryset = (cargos if cargos is not None else Cargo.objects.filter(estado=True)).order_by('nombre')

    def buscar_texto(self, queryset, name, value):
        return queryset.filter(Q(unidad__icontains=value)
            | Q(id_cargo_item__id_item__nombre__icontains=value)
            | Q(id_cargo_item__id_cargo__nombre__icontains=value)).distinct()
