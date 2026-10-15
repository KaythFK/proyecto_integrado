from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Actividad
from .forms import ActividadForm


#@login_required
def listar_actividades(request):
    actividades = Actividad.objects.filter(estado=True)
    return render(request, 'funcionario/actividades/listar_actividades.html', {'actividades': actividades})


#@login_required
def crear_actividad(request):
    if request.method == 'POST':
        form = ActividadForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Actividad creada con éxito.')
            return redirect('listar_actividades')
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
            return redirect('listar_actividades')
    else:
        form = ActividadForm(instance=actividad)
        
    return render(request, 'funcionario/actividades/form_actividad.html', {'form': form, 'titulo': 'Editar Actividad'})


#@login_required
def desactivar_actividad(request, id_actividad):
    actividad = get_object_or_404(Actividad, pk=id_actividad)
    
    if request.method == 'POST':
        # Regla estricta: NO usamos actividad.delete(), solo apagamos el switch
        actividad.estado = False
        actividad.save()
        messages.success(request, f'La actividad {actividad.codigo_unico} fue desactivada del sistema.')
        return redirect('listar_actividades')
        
    return render(request, 'funcionario/actividades/confirmar_desactivar.html', {'actividad': actividad})

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
            return redirect('listar_actividades')
    else:
        form = ActividadForm()
        
    return render(request, 'funcionario/actividades/form_actividad.html', {'form': form, 'titulo': 'Crear Actividad'})