from datetime import timedelta

import django_filters
from django import forms
from django.db.models import Q

from config.utils import inicio_del_dia
from .models import Auditoria, Profesional
from config.utils import EtiquetaFuncionarioFiltroMixin

SELECT = {'class': 'form-select borde-guinda'}
FECHA = {'class': 'form-control borde-guinda', 'type': 'date'}


class AuditoriaFilter(EtiquetaFuncionarioFiltroMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='buscar_texto', label='Buscar',
        widget=forms.TextInput(attrs={'class': 'form-control borde-guinda', 'placeholder': 'Evento, entidad o registro'}))
    evento = django_filters.ChoiceFilter(field_name='evento', label='Evento', empty_label='Todos',
                                         widget=forms.Select(attrs=SELECT))
    entidad = django_filters.ChoiceFilter(field_name='entidad', label='Entidad', empty_label='Todas',
                                          widget=forms.Select(attrs=SELECT))
    funcionario = django_filters.ModelChoiceFilter(
        field_name='funcionario_id_funcionario', label='Funcionario', queryset=Profesional.objects.none(),
        empty_label='Todos', widget=forms.Select(attrs=SELECT))
    desde = django_filters.DateFilter(method='filtrar_desde', label='Desde', widget=forms.DateInput(attrs=FECHA))
    hasta = django_filters.DateFilter(method='filtrar_hasta', label='Hasta', widget=forms.DateInput(attrs=FECHA))

    class Meta:
        model = Auditoria
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        todos = Auditoria.objects.order_by()
        self.filters['evento'].extra['choices'] = [(e, e) for e in todos.values_list('evento', flat=True).distinct().order_by('evento')]
        self.filters['entidad'].extra['choices'] = [(e, e) for e in todos.values_list('entidad', flat=True).distinct().order_by('entidad')]
        self.filters['funcionario'].queryset = Profesional.objects.filter(
            pk__in=todos.values('funcionario_id_funcionario')).order_by('nombres', 'apellido_paterno')

    def filtrar_desde(self, queryset, name, value):
        return queryset.filter(fecha__gte=inicio_del_dia(value))

    def filtrar_hasta(self, queryset, name, value):
        return queryset.filter(fecha__lt=inicio_del_dia(value + timedelta(days=1)))

    def buscar_texto(self, queryset, name, value):
        filtro = Q(evento__icontains=value) | Q(entidad__icontains=value) | Q(valor_nuevo__icontains=value)
        if value.isdigit():
            filtro |= Q(identificador=int(value))
        return queryset.filter(filtro)
