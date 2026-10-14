
from django.shortcuts import render
from .models import Actividad, Evidencia

def lista_actividades(request):
    actividades = Actividad.objects.all()
    evidencias = Evidencia.objects.all()
    
    context = {
        'actividades': actividades,
        'evidencias': evidencias,
    }
    return render(request, 'administrador/lista_actividades.html', context)