from django.shortcuts import render
from django.db.models import Q
from actividadApp.models import Actividad



def dashboard_delegado(request):
    total_actividades = Actividad.objects.filter(estado=True).count()
    en_proceso = Actividad.objects.filter(estado=True, estado_progreso='EN_PROCESO').count()
    finalizadas = Actividad.objects.filter(estado=True, estado_progreso='FINALIZADA').count()
    
    context = {
        'total_actividades': total_actividades,
        'en_proceso': en_proceso,
        'finalizadas': finalizadas,
    }
    return render(request, 'delegado/dashboard_delegado.html', context)

def actividades_delegacion(request):
    query = request.GET.get('q')
    actividades = Actividad.objects.filter(estado=True).order_by('-fecha')
    
    if query:
        actividades = actividades.filter(
            Q(codigo_unico__icontains=query) |
            Q(solicitud_problema__icontains=query) |
            Q(accion__icontains=query)
        ).distinct()
        
    return render(request, 'delegado/lista_actividades.html', {
        'actividades': actividades,
        'query': query
    })