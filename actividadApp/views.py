from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from datetime import datetime  
import uuid                    

from .models import Actividad
from .forms import ActividadForm

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
        
    return render(request, 'funcionario/actividades/listar_actividades.html', {
        'actividades': actividades,
        'query': query  
    })
    
#@login_required
def crear_actividad(request):
    if request.method == 'POST':
        form = ActividadForm(request.POST)
        if form.is_valid():
            actividad = form.save(commit=False)
            codigo_generado = f"ACT-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"
            actividad.codigo_unico = codigo_generado
            actividad.estado = True 
            actividad.save()
            messages.success(request, f'Actividad {codigo_generado} registrada exitosamente.')
            return redirect('actividadApp:listar_actividades')
    else:
        form = ActividadForm()
    return render(request, 'funcionario/actividades/form_actividad.html', {'form': form, 'titulo': 'Crear Actividad'})

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
        
    return render(request, 'funcionario/actividades/form_actividad.html', {'form': form, 'titulo': 'Editar Actividad'})

#@login_required
def desactivar_actividad(request, codigo_unico):
    actividad = get_object_or_404(Actividad, codigo_unico=codigo_unico)
    actividad.estado = not actividad.estado 
    actividad.save()
    
    messages.success(request, f'Estado de la actividad actualizado.')
    return redirect(request.META.get('HTTP_REFERER', '/')) 