from django.shortcuts import render
from django.db.models import Count, Q
from actividadApp.models import Actividad 
from .models import Compromiso, ObservacionCompromiso

def agenda(request):
    compromisos = Compromiso.objects.all()
    observaciones = ObservacionCompromiso.objects.all()
    context = {
        'compromisos': compromisos,
        'observaciones': observaciones,
    }
    return render(request, 'administrador/lista_tubo.html', context)


#@login_required
def dashboard_coordinador(request):
    total_actividades = Actividad.objects.count()
    finalizadas = Actividad.objects.filter(estado_progreso='FINALIZADA').count()
    en_proceso = Actividad.objects.filter(estado_progreso='EN_PROCESO').count()
    pendientes = Actividad.objects.filter(estado_progreso='PENDIENTE').count() 

    context = {
        'total': total_actividades,
        'finalizadas': finalizadas,
        'en_proceso': en_proceso,
        'pendientes': pendientes,
    }
    return render(request, 'coordinador/dashboard_coordinador.html', context)

#@login_required
def listar_todas_actividades(request):
    query = request.GET.get('q')
    estado_filtro = request.GET.get('estado')
    
    actividades = Actividad.objects.all().order_by('-fecha')

    if query:
        actividades = actividades.filter(
            Q(codigo_unico__icontains=query) |
            Q(solicitud_problema__icontains=query)
        ).distinct()
        
    if estado_filtro:
        actividades = actividades.filter(estado_progreso=estado_filtro)

    context = {
        'actividades': actividades,
        'query': query,
        'estado_filtro': estado_filtro,
    }

    return render(request, 'coordinador/listar_todas.html', context)