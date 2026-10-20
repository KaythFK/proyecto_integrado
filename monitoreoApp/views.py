from django.shortcuts import render
from actividadApp.models import Actividad
from django.db.models import Q

from usuariosApp.decorators import role_required
from django.contrib.auth.decorators import login_required

@login_required
@role_required('Delegado')
def dashboard_delegado(request):
    actividades_recientes = Actividad.objects.filter(estado=True).order_by('-fecha')[:5]
    total_actividades = Actividad.objects.filter(estado=True).count()
    en_proceso = Actividad.objects.filter(estado=True, estado_progreso='EN_PROCESO').count()
    finalizadas = Actividad.objects.filter(estado=True, estado_progreso='FINALIZADA').count()
    
    context = {
        'actividades': actividades_recientes,
        'total_actividades': total_actividades,
        'en_proceso': en_proceso,
        'finalizadas': finalizadas,
        'titulo': 'Panel de Monitoreo Territorial'
    }
    
    return render(request, 'delegado/dashboard_delegado.html', context)

@login_required
@role_required('Delegado')
def actividades_delegacion(request):
    query = request.GET.get('q')
    actividades = Actividad.objects.filter(estado=True).order_by('-fecha')

    if query:
        actividades = actividades.filter(
            Q(codigo_unico__icontains=query) |
            Q(solicitud_problema__icontains=query)
        ).distinct()
        
    context = {
        'actividades': actividades,
        'query': query,
    }
    
    return render(request, 'delegado/lista_actividades.html', context)