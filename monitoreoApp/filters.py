import django_filters
from django import forms
from django.db.models import Q

from administracionApp.models import CatalagoItem, Delegacion, Periodo, Profesional
from .models import Meta

SELECT = {'class': 'form-select borde-guinda'}


class MetaFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='buscar_texto', label='Buscar',
        widget=forms.TextInput(attrs={'class': 'form-control borde-guinda', 'placeholder': 'Unidad o ítem'}))
    delegacion = django_filters.ModelChoiceFilter(
        field_name='id_funcionario__id_delegacion', label='Delegación', queryset=Delegacion.objects.none(),
        empty_label='Todas', widget=forms.Select(attrs=SELECT))
    funcionario = django_filters.ModelChoiceFilter(
        field_name='id_funcionario', label='Profesional', queryset=Profesional.objects.none(),
        empty_label='Todos', widget=forms.Select(attrs=SELECT))
    periodo = django_filters.ModelChoiceFilter(
        field_name='id_periodo', label='Período', queryset=Periodo.objects.order_by('-fecha_inicio'),
        empty_label='Todos', widget=forms.Select(attrs=SELECT))
    item = django_filters.ModelChoiceFilter(
        field_name='id_item', label='Ítem', queryset=CatalagoItem.objects.order_by('nombre'),
        empty_label='Todos', widget=forms.Select(attrs=SELECT))

    class Meta:
        model = Meta
        fields = []

    def __init__(self, *args, profesionales=None, ocultar=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.filters['delegacion'].queryset = Delegacion.objects.filter(estado=True).order_by('nombre')
        self.filters['funcionario'].queryset = (
            profesionales if profesionales is not None else Profesional.objects.filter(estado=True)
        ).order_by('nombres')
        for nombre in ocultar:
            self.filters.pop(nombre)

    def buscar_texto(self, queryset, name, value):
        return queryset.filter(Q(unidad__icontains=value) | Q(id_item__nombre__icontains=value)).distinct()
