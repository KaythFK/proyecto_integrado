from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from datetime import datetime  
import uuid                    

from .models import Actividad
from .forms import ActividadForm

#@login_required
def dashboard_funcionario(request):
    mis_actividades = Actividad.objects.filter(estado=True)
    total = mis_actividades.count()
    pendientes = mis_actividades.filter(estado_progreso='Pendiente').count()
    en_proceso = mis_actividades.filter(estado_progreso='En Proceso').count()
    casos_en_tubo = mis_actividades.filter(en_tubo=True).count()
    sin_evidencia = mis_actividades.filter(evidencia__isnull=True).exclude(estado_progreso='Finalizada').count()
    tareas_prioritarias = mis_actividades.exclude(estado_progreso='Finalizada').order_by('-fecha')[:5]
    context = {
        'total': total,
        'pendientes': pendientes,
        'en_proceso': en_proceso,
        'casos_en_tubo': casos_en_tubo,
        'sin_evidencia': sin_evidencia,
        'tareas_prioritarias': tareas_prioritarias,
    }
    return render(request, 'funcionario/dashboard_funcionario.html', context)


#@login_required
def listar_actividades(request):
    query = request.GET.get('q')
    actividades = Actividad.objects.all().order_by('-id_actividad') 
    
    if query:
        actividades = actividades.filter(
            Q(codigo_unico__icontains=query) |
            Q(solicitud_problema__icontains=query) |
            Q(accion__icontains=query)
        ).distinct()
        
    return render(request, 'funcionario/listar_actividades.html', {
        'actividades': actividades,
        'query': query  
    })
    
#@login_required
def crear_actividad(request):
    if request.method == 'POST':
        form = ActividadForm(request.POST)
        if form.is_valid():
            nueva_actividad = form.save(commit=False)
            año_actual = datetime.now().year
            codigo_random = str(uuid.uuid4()).split('-')[0][:6].upper() 
            nueva_actividad.codigo_unico = f"ACT-{año_actual}-{codigo_random}"
            nueva_actividad.save()
            return redirect('actividadApp:listar_actividades') 
    else:
        form = ActividadForm()
    context = {
        'form': form,
        'titulo': 'Crear Nueva Actividad',
    }
    return render(request, 'funcionario/form_actividad.html', context)

#@login_required
def editar_actividad(request, id_actividad):
    actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
    if request.method == 'POST':
        form = ActividadForm(request.POST, instance=actividad)
        if form.is_valid():
            form.save()
            messages.success(request, 'Actividad actualizada.')
            return redirect('actividadApp:listar_actividades')
    else:
        form = ActividadForm(instance=actividad)
        
    return render(request, 'funcionario/form_actividad.html', {'form': form, 'titulo': 'Editar Actividad'})

#@login_required
def desactivar_actividad(request, codigo_unico):
    actividad = get_object_or_404(Actividad, codigo_unico=codigo_unico)
    actividad.estado = not actividad.estado 
    actividad.save()
    
    messages.success(request, f'Estado de la actividad actualizado.')
    return redirect(request.META.get('HTTP_REFERER', '/')) 

