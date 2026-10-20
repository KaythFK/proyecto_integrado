from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from datetime import datetime, date, timedelta
import uuid
from usuariosApp.decorators import role_required
from .models import Actividad, Evidencia
from .forms import ActividadForm
from administracionApp.models import Profesional
from monitoreoApp.models import Meta
from tuboApp.models import Compromiso



@login_required
@role_required('Profesional')

def dashboard_profesional(request):
    profesional_actual = None 

    try:
        if request.user.is_authenticated:
            profesional_actual = Profesional.objects.filter(usuario=request.user).first()
            
        if profesional_actual:
            actividades_asignadas = Actividad.objects.filter(id_profesional=profesional_actual).order_by('-fecha')
            compromisos_tubo = Compromiso.objects.filter(id_funcionario=profesional_actual).order_by('fecha_comprometida')
        else:
            actividades_asignadas = Actividad.objects.all().order_by('-fecha')
            compromisos_tubo = Compromiso.objects.all().order_by('fecha_comprometida')
    except Exception:
        actividades_asignadas = Actividad.objects.all().order_by('-fecha')
        compromisos_tubo = Compromiso.objects.none()
    total_asignadas = actividades_asignadas.count()
    evidencias_registradas = Evidencia.objects.filter(id_actividad__in=actividades_asignadas).count()

    evidencias_aprobadas = Evidencia.objects.filter(
        id_actividad__in=actividades_asignadas, 
        estado_revision='APROBADO'
    ).count()

    if total_asignadas > 0:
        porcentaje_avance = int((evidencias_aprobadas / total_asignadas) * 100)
    else:
        porcentaje_avance = 0

    if porcentaje_avance >= 80:
        semaforo = 'VERDE'
    elif porcentaje_avance >= 50:
        semaforo = 'AMBAR'
    else:
        semaforo = 'ROJO'

    for actividad in actividades_asignadas:
        evidencia = Evidencia.objects.filter(id_actividad=actividad).first()
        if evidencia:
            actividad.estado_evidencia = evidencia.estado_revision
        else:
            actividad.estado_evidencia = 'SIN_EVIDENCIA'

    limite_vencimiento = date.today() + timedelta(days=3)
    total_proximos = compromisos_tubo.filter(
        fecha_comprometida__lte=limite_vencimiento
    ).exclude(estado_progreso='REALIZADO').count()

    context = {
        'total_asignadas': total_asignadas,
        'evidencias_registradas': evidencias_registradas,
        'actividades_asignadas': actividades_asignadas,
        'semaforo': semaforo, 
        'porcentaje_avance': porcentaje_avance,
        'compromisos_tubo': compromisos_tubo,
        'total_proximos_vencer': total_proximos,
        'profesional_actual': profesional_actual
    }
    return render(request, 'profesional/dashboard_profesional.html', context)

@login_required
@role_required('Profesional')
def listar_actividades(request):
    query = request.GET.get('q')
    actividades = Actividad.objects.all().order_by('-id_actividad') 
    
    if query:
        actividades = actividades.filter(
            Q(codigo_unico__icontains=query) |
            Q(solicitud_problema__icontains=query) |
            Q(accion__icontains=query)
        ).distinct()
        
    return render(request, 'profesional/listar_actividades.html', {
        'actividades': actividades,
        'query': query  
    })
    

@login_required
@role_required('Profesional')
def registrar_actividad(request, actividad_id=None):
    if request.method == 'POST':
        form = ActividadForm(request.POST) 
        if form.is_valid():
            nueva_actividad = form.save(commit=False)
            año_actual = datetime.now().year
            codigo_random = str(uuid.uuid4()).split('-')[0][:6].upper() 
            nueva_actividad.codigo_unico = f"ACT-{año_actual}-{codigo_random}"
            nueva_actividad.estado = True
            nueva_actividad.save()
            if nueva_actividad.en_tubo:
                Compromiso.objects.create(
                    territorio="Por asignar", 
                    fecha_comprometida=date.today() + timedelta(days=7), 
                    estado_progreso='INGRESADO',
                    estado=True,
                    id_funcionario=nueva_actividad.id_profesional,
                    id_actividad=nueva_actividad
                )
                messages.success(request, f'¡Actividad registrada! Se ha creado un compromiso en el Tubo asociado al código {nueva_actividad.codigo_unico}.')
            else:
                messages.success(request, f'¡Actividad registrada con éxito! Código: {nueva_actividad.codigo_unico}')
            
            return redirect('actividadApp:dashboard_profesional') 
    else:
        form = ActividadForm() 

    context = {
        'form': form,
        'titulo': 'Nueva Intervención Profesional'
    }
    return render(request, 'profesional/registrar_actividad.html', context)

@login_required
@role_required('Profesional')
def editar_actividad(request, id_actividad):
    actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
    if request.method == 'POST':
        form = ActividadForm(request.POST, instance=actividad)
        if form.is_valid():
            form.save()
            messages.success(request, 'Actividad actualizada correctamente.')
            return redirect('actividadApp:listar_actividades')
    else:
        form = ActividadForm(instance=actividad)
    return render(request, 'profesional/registrar_actividad.html', {
        'form': form, 
        'titulo': f'Editar Actividad: {actividad.codigo_unico}'
    })


@login_required
@role_required('Profesional')
def registrar_evidencia(request, actividad_id):
    actividad = get_object_or_404(Actividad, id_actividad=actividad_id)
    
    if request.method == 'POST':
        archivo_vinculo = request.POST.get('archivo_vinculo', 'evidencia_adjunta.pdf')
        anotaciones = request.POST.get('anotaciones', '')
        autor_nombre = request.user.username if request.user.is_authenticated else 'Profesional'

        metadatos_dict = {
            "codigo_actividad": actividad.codigo_unico,
            "autor": autor_nombre,
            "observacion": anotaciones,
            "origen": "Panel Profesional"
        }
        
        Evidencia.objects.create(
            archivo_vinculo=archivo_vinculo,
            metadatos=metadatos_dict,
            estado_revision='PENDIENTE',
            estado=True,
            id_actividad=actividad
        )
        
        messages.success(request, f'Evidencia vinculada correctamente al código {actividad.codigo_unico}.')
        return redirect('actividadApp:dashboard_profesional')

    context = {
        'actividad': actividad,
    }
    return render(request, 'profesional/registrar_evidencia.html', context)


@login_required
@role_required('Profesional')
def desactivar_actividad(request, codigo_unico):
    actividad = get_object_or_404(Actividad, codigo_unico=codigo_unico)
    actividad.estado = not actividad.estado 
    actividad.save()
    
    messages.success(request, 'Estado de la actividad actualizado.')
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
@role_required('Profesional')
def actualizar_estado_tubo(request, id_compromiso):
    if request.method == 'POST':
        compromiso = get_object_or_404(Compromiso, id_compromiso=id_compromiso)
        nuevo_estado = request.POST.get('estado_progreso')
        estados_validos = dict(Compromiso.OPCIONES_ESTADO_PROGRESO).keys()
        if nuevo_estado in estados_validos:
            compromiso.estado_progreso = nuevo_estado
            if nuevo_estado == 'REALIZADO':
                compromiso.fecha_termino = date.today()
            compromiso.save()
            messages.success(request, f'El compromiso en {compromiso.territorio} se ha actualizado a: {compromiso.get_estado_progreso_display()}')
        else:
            messages.error(request, 'Error: El estado seleccionado no es válido.')
    return redirect('actividadApp:dashboard_profesional')