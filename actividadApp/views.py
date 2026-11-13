from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from datetime import datetime, date, timedelta
import uuid
from usuariosApp.decorators import role_required
from .models import Actividad, Evidencia, Ausencia, Retroalimentacion, Validacion, GestionActividad
from .forms import ActividadForm, ActividadDelegadoForm, AusenciaForm, RetroalimentacionForm, EvidenciaForm, ValidacionForm, GestionActividadForm
from administracionApp.models import Profesional, Auditoria # <- Añadido Auditoria
from monitoreoApp.models import Meta, Indicador
from tuboApp.models import Compromiso
from django.db import transaction
from config.utils import validar_evidencia_no_duplicada
from django.core.exceptions import ValidationError
import json
from django.forms.models import model_to_dict

# --- FUNCIÓN AUXILIAR DE AUDITORÍA ---
def registrar_auditoria(request, evento, entidad, objeto_instancia, datos_anteriores=None):
    """
    Función centralizada para registrar auditoría con descripciones legibles.
    """
    try:
        profesional_actual = Profesional.objects.filter(usuario=request.user).first() if request.user.is_authenticated else None
        identificador = getattr(objeto_instancia, 'pk', 0)
        
        diccionario_nuevo = model_to_dict(objeto_instancia)
        datos_nuevos_limpios = {k: str(v) for k, v in diccionario_nuevo.items()}
        datos_nuevos_limpios['descripcion_legible'] = str(objeto_instancia)
        
        datos_anteriores_limpios = None
        if datos_anteriores:
            datos_anteriores_limpios = {k: str(v) for k, v in datos_anteriores.items()}
            datos_anteriores_limpios['descripcion_legible'] = str(objeto_instancia)

        Auditoria.objects.create(
            evento=evento,
            entidad=entidad,
            identificador=identificador,
            valor_anterior=datos_anteriores_limpios,
            valor_nuevo=datos_nuevos_limpios,
            funcionario_id_funcionario=profesional_actual
        )
    except Exception as e:
        print(f"Error interno registrando auditoría: {e}")
# ---------------------------------------

@login_required
@role_required('Profesional')
def dashboard_profesional(request):
    profesional_actual = None 

    try:
        if request.user.is_authenticated:
            profesional_actual = Profesional.objects.filter(usuario=request.user).first()
            
        if profesional_actual:
            actividades_asignadas = Actividad.objects.filter(id_profesional=profesional_actual).order_by('-fecha_registro')
            compromisos_tubo = Compromiso.objects.filter(id_funcionario=profesional_actual).order_by('fecha_comprometida')
        else:
            actividades_asignadas = Actividad.objects.all().order_by('-fecha_registro')
            compromisos_tubo = Compromiso.objects.all().order_by('fecha_comprometida')
    except Exception:
        actividades_asignadas = Actividad.objects.all().order_by('-fecha_registro')
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
    
    profesional_actual = request.user.profesional
    actividades = Actividad.objects.filter(id_profesional=profesional_actual).prefetch_related('gestiones__tipo_gestion').order_by('-fecha_registro')

    if query:
        actividades = actividades.filter(
            Q(codigo_unico__icontains=query) |
            Q(solicitud_problema__icontains=query)
        ).distinct()
        
    context = {
        'actividades': actividades,
        'query': query,
    }
    return render(request, 'profesional/listar_actividades.html', context)

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
            
            # AUDITORIA
            registrar_auditoria(request, "CREACION", "Actividad", nueva_actividad)
            
            if nueva_actividad.en_tubo:
                nuevo_compromiso = Compromiso.objects.create(
                    territorio="Por asignar", 
                    fecha_comprometida=date.today() + timedelta(days=7), 
                    estado_progreso='INGRESADO',
                    estado=True,
                    id_funcionario=nueva_actividad.id_profesional,
                    id_actividad=nueva_actividad,
                    organizacion=nueva_actividad.id_organizacion  # el compromiso exige organización
                )
                registrar_auditoria(request, "CREACION", "Compromiso", nuevo_compromiso)
                
                messages.success(request, f'¡Actividad registrada! Se ha creado un compromiso en el Tubo asociado al código {nueva_actividad.codigo_unico}.')
            else:
                messages.success(request, f'¡Actividad registrada con éxito! Código: {nueva_actividad.codigo_unico}')
            
            return redirect('actividadApp:dashboard_profesional') 
        else:
            messages.error(request, 'No se pudo guardar. Revisa los campos marcados en rojo.')
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
        datos_antiguos = model_to_dict(actividad)
        form = ActividadForm(request.POST, instance=actividad)
        if form.is_valid():
            actividad_guardada = form.save()
            registrar_auditoria(request, "EDICION", "Actividad", actividad_guardada, datos_antiguos)
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
        
        nueva_evidencia = Evidencia.objects.create(
            archivo_vinculo=archivo_vinculo,
            metadatos=metadatos_dict,
            estado_revision='PENDIENTE',
            estado=True,
            id_actividad=actividad
        )
        
        # AUDITORIA
        registrar_auditoria(request, "CREACION", "Evidencia", nueva_evidencia)
        
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
    datos_antiguos = model_to_dict(actividad)
    actividad.estado = not actividad.estado 
    actividad.save()
    
    registrar_auditoria(request, "CAMBIO_ESTADO", "Actividad", actividad, datos_antiguos)
    
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
            datos_antiguos = model_to_dict(compromiso)
            compromiso.estado_progreso = nuevo_estado
            if nuevo_estado == 'REALIZADO':
                compromiso.fecha_termino = date.today()
            compromiso.save()
            
            registrar_auditoria(request, "CAMBIO_PROGRESO", "Compromiso", compromiso, datos_antiguos)
            
            messages.success(request, f'El compromiso en {compromiso.territorio} se ha actualizado a: {compromiso.get_estado_progreso_display()}')
        else:
            messages.error(request, 'Error: El estado seleccionado no es válido.')
    return redirect('actividadApp:dashboard_profesional')

@login_required
@role_required('Delegado')
def actividades_delegacion(request):
    query = request.GET.get('q')
    delegacion_actual = request.user.profesional.id_delegacion
    
    actividades = Actividad.objects.filter(
        id_profesional__id_delegacion=delegacion_actual
    ).order_by('-fecha_registro')

    if query:
        actividades = actividades.filter(
            Q(codigo_unico__icontains=query) |
            Q(solicitud_problema__icontains=query)
        ).distinct()
        
    context = {
        'actividades': actividades,
        'query': query,
        'delegacion_nombre': delegacion_actual.nombre
    }
    return render(request, 'delegado/lista_actividades.html', context)

@login_required
@role_required('Delegado')
def registrar_actividad_delegado(request):
    if request.method == 'POST':
        form = ActividadDelegadoForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    nueva_actividad = form.save(commit=False)
                    año_actual = datetime.now().year
                    codigo_random = str(uuid.uuid4()).split('-')[0][:6].upper()
                    nueva_actividad.codigo_unico = f"ACT-{año_actual}-{codigo_random}"
                    nueva_actividad.estado = True
                    nueva_actividad.save()
                    
                    registrar_auditoria(request, "CREACION", "Actividad", nueva_actividad)
                    
                    if nueva_actividad.en_tubo:
                        nuevo_compromiso = Compromiso.objects.create(
                            territorio="Por asignar", 
                            fecha_comprometida=date.today() + timedelta(days=7), 
                            estado_progreso='INGRESADO',
                            estado=True,
                            id_funcionario=nueva_actividad.id_profesional,
                            id_actividad=nueva_actividad,
                            organizacion=nueva_actividad.id_organizacion  # el compromiso exige organización
                        )
                        registrar_auditoria(request, "CREACION", "Compromiso", nuevo_compromiso)
                        messages.success(request, f'¡Actividad registrada y derivada al Tubo! Código: {nueva_actividad.codigo_unico}.')
                    else:
                        messages.success(request, f'¡Actividad registrada con éxito! Código: {nueva_actividad.codigo_unico}')
                    
                    return redirect('actividadApp:actividades_delegacion')
            except Exception as e:
                messages.error(request, f'Error al registrar la actividad: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        form = ActividadForm()

    context = {
        'form': form,
        'titulo': 'Registrar Nueva Actividad'
    }
    return render(request, 'delegado/form_actividad.html', context)

@login_required
@role_required('Delegado')
def editar_actividad_delegado(request, id_actividad):
    delegacion_actual = request.user.profesional.id_delegacion
    actividad = get_object_or_404(Actividad, id_actividad=id_actividad, id_profesional__id_delegacion=delegacion_actual)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(actividad)
        form = ActividadDelegadoForm(request.POST, instance=actividad)
        if form.is_valid():
            try:
                with transaction.atomic():
                    actividad_guardada = form.save()
                    registrar_auditoria(request, "EDICION", "Actividad", actividad_guardada, datos_antiguos)
                    
                    if actividad_guardada.en_tubo:
                        compromiso, created = Compromiso.objects.get_or_create(
                            id_actividad=actividad_guardada,
                            defaults={
                                'territorio': 'Por asignar',
                                'fecha_comprometida': date.today() + timedelta(days=7),
                                'id_funcionario': actividad_guardada.id_profesional,
                                'estado_progreso': 'INGRESADO'
                            }
                        )
                        if created:
                            registrar_auditoria(request, "CREACION", "Compromiso", compromiso)
                            
                    messages.success(request, f'La actividad {actividad_guardada.codigo_unico} fue actualizada correctamente.')
                    return redirect('actividadApp:actividades_delegacion')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        form = ActividadDelegadoForm(instance=actividad)

    context = {
        'form': form,
        'titulo': f'Editar Actividad: {actividad.codigo_unico}'
    }
    return render(request, 'delegado/form_actividad.html', context)

@login_required
@role_required('Delegado')
def cambiar_estado_actividad_delegado(request, id_actividad):
    if request.method == 'POST':
        delegacion_actual = request.user.profesional.id_delegacion
        actividad = get_object_or_404(Actividad, id_actividad=id_actividad, id_profesional__id_delegacion=delegacion_actual)
        
        try:
            with transaction.atomic():
                datos_antiguos = model_to_dict(actividad)
                nuevo_estado = not actividad.estado
                actividad.estado = nuevo_estado
                actividad.save()
                
                registrar_auditoria(request, "CAMBIO_ESTADO", "Actividad", actividad, datos_antiguos)
                
                accion = "habilitada" if nuevo_estado else "inhabilitada"
                messages.success(request, f'La actividad {actividad.codigo_unico} fue {accion} correctamente.')
        except Exception as e:
            messages.error(request, f'Error al cambiar el estado: {str(e)}')
            
    return redirect('actividadApp:actividades_delegacion')

@login_required
def actualizar_progreso_actividad(request, id_actividad):
    if request.method == 'POST':
        actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
        nuevo_estado = request.POST.get('nuevo_estado')
        
        estados_validos = dict(Actividad.OPCIONES_ESTADO_PROGRESO).keys()
        
        if nuevo_estado in estados_validos:
            datos_antiguos = model_to_dict(actividad)
            actividad.estado_progreso = nuevo_estado
            
            if nuevo_estado == 'FINALIZADA':
                actividad.fecha_finalizacion = date.today()
            elif nuevo_estado != 'FINALIZADA' and actividad.fecha_finalizacion:
                actividad.fecha_finalizacion = None
                
            actividad.save()
            registrar_auditoria(request, "CAMBIO_PROGRESO", "Actividad", actividad, datos_antiguos)
            
            messages.success(request, f'La actividad {actividad.codigo_unico} cambió su estado a: {actividad.get_estado_progreso_display()}')
        else:
            messages.error(request, 'Error: El estado seleccionado no es válido.')
            
    return redirect(request.META.get('HTTP_REFERER', '/'))


@login_required
@role_required('Administrador', 'Coordinador')
def lista_ausencias(request):
    query = request.GET.get('q')
    ausencias = Ausencia.objects.all().select_related('profesional_ausente', 'periodo_ausencia').order_by('-id_ausencia')
    
    if query:
        ausencias = ausencias.filter(
            Q(profesional_ausente__nombres__icontains=query) |
            Q(profesional_ausente__apellido_paterno__icontains=query) |
            Q(tipo_ausencia__icontains=query)
        ).distinct()
        
    return render(request, 'administrador/ausencias/lista_ausencias.html', {
        'ausencias': ausencias,
        'query': query
    })

@login_required
@role_required('Administrador', 'Coordinador')
def crear_ausencia(request):
    if request.method == 'POST':
        form = AusenciaForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    ausencia = form.save(commit=False)
                    ausencia.estado = True
                    ausencia.save()
                    
                    registrar_auditoria(request, "CREACION", "Ausencia", ausencia)
                    
                messages.success(request, 'El registro de ausencia fue guardado con éxito.')
                return redirect('actividadApp:lista_ausencias')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = AusenciaForm()
        
    return render(request, 'administrador/ausencias/form_ausencia.html', {
        'form': form,
        'titulo': 'Registrar Ausencia o Permiso'
    })

@login_required
@role_required('Administrador', 'Coordinador')
def editar_ausencia(request, id_ausencia):
    ausencia = get_object_or_404(Ausencia, pk=id_ausencia)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(ausencia)
        form = AusenciaForm(request.POST, instance=ausencia)
        if form.is_valid():
            try:
                with transaction.atomic():
                    ausencia_guardada = form.save()
                    registrar_auditoria(request, "EDICION", "Ausencia", ausencia_guardada, datos_antiguos)
                messages.success(request, 'La ausencia fue actualizada correctamente.')
                return redirect('actividadApp:lista_ausencias')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = AusenciaForm(instance=ausencia)
        
    return render(request, 'administrador/ausencias/form_ausencia.html', {
        'form': form,
        'titulo': 'Editar Ausencia'
    })

@login_required
@role_required('Administrador', 'Coordinador')
def cambiar_estado_ausencia(request, id_ausencia):
    if request.method == 'POST':
        ausencia = get_object_or_404(Ausencia, pk=id_ausencia)
        
        with transaction.atomic():
            datos_antiguos = model_to_dict(ausencia)
            nuevo_estado = not ausencia.estado
            ausencia.estado = nuevo_estado
            ausencia.save()
            registrar_auditoria(request, "CAMBIO_ESTADO", "Ausencia", ausencia, datos_antiguos)
                
        accion_str = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'El registro de ausencia fue {accion_str} correctamente.')
        
    return redirect('actividadApp:lista_ausencias')



@login_required
@role_required('Administrador', 'Profesional')
def lista_retroalimentaciones(request):
    query = request.GET.get('q')
    retroalimentaciones = Retroalimentacion.objects.all().select_related(
        'receptor', 'retroalimentado', 'vecino', 'delegacion', 'meta'
    ).order_by('-id_retroalimentacion')
    
    if query:
        retroalimentaciones = retroalimentaciones.filter(
            Q(tipo__icontains=query) |
            Q(canal_recepcion__icontains=query) |
            Q(receptor__nombres__icontains=query) |
            Q(retroalimentado__nombres__icontains=query)
        ).distinct()
        
    return render(request, 'administrador/retroalimentaciones/lista_retroalimentaciones.html', {
        'retroalimentaciones': retroalimentaciones,
        'query': query
    })

@login_required
@role_required('Administrador', 'Profesional')
def crear_retroalimentacion(request):
    if request.method == 'POST':
        form = RetroalimentacionForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    retro = form.save(commit=False)
                    retro.estado = True
                    retro.save()
                    registrar_auditoria(request, "CREACION", "Retroalimentacion", retro)
                messages.success(request, 'La retroalimentación fue registrada con éxito.')
                return redirect('actividadApp:lista_retroalimentaciones')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = RetroalimentacionForm()
        
    return render(request, 'administrador/retroalimentaciones/form_retroalimentacion.html', {
        'form': form,
        'titulo': 'Registrar Retroalimentación'
    })

@login_required
@role_required('Administrador', 'Profesional')
def editar_retroalimentacion(request, id_retroalimentacion):
    retro = get_object_or_404(Retroalimentacion, pk=id_retroalimentacion)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(retro)
        form = RetroalimentacionForm(request.POST, instance=retro)
        if form.is_valid():
            try:
                with transaction.atomic():
                    retro_guardada = form.save()
                    registrar_auditoria(request, "EDICION", "Retroalimentacion", retro_guardada, datos_antiguos)
                messages.success(request, 'La retroalimentación fue actualizada correctamente.')
                return redirect('actividadApp:lista_retroalimentaciones')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = RetroalimentacionForm(instance=retro)
        
    return render(request, 'administrador/retroalimentaciones/form_retroalimentacion.html', {
        'form': form,
        'titulo': 'Editar Retroalimentación'
    })

@login_required
@role_required('Administrador', 'Profesional')
def cambiar_estado_retroalimentacion(request, id_retroalimentacion):
    if request.method == 'POST':
        retro = get_object_or_404(Retroalimentacion, pk=id_retroalimentacion)
        
        with transaction.atomic():
            datos_antiguos = model_to_dict(retro)
            nuevo_estado = not retro.estado
            retro.estado = nuevo_estado
            retro.save()
            registrar_auditoria(request, "CAMBIO_ESTADO", "Retroalimentacion", retro, datos_antiguos)
                
        accion_str = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'La retroalimentación fue {accion_str} correctamente.')
        
    return redirect('actividadApp:lista_retroalimentaciones')


@login_required
@role_required('Administrador', 'Profesional', 'Delegado')
def lista_evidencias(request):
    query = request.GET.get('q')
    profesional_actual = getattr(request.user, 'profesional', None)
    
    # 1. Obtenemos todas las evidencias como base
    evidencias = Evidencia.objects.all().select_related('id_actividad').order_by('-id_evidencia')
    
    # 2. FILTRO DE SEGURIDAD POR ROL
    if profesional_actual:
        if request.user.groups.filter(name='Administrador').exists():
            # El Administrador pasa directo y ve TODO
            pass 
        elif request.user.groups.filter(name='Delegado').exists():
            # El Delegado SOLO ve las evidencias de los profesionales de SU delegación
            delegacion_actual = profesional_actual.id_delegacion
            evidencias = evidencias.filter(id_actividad__id_profesional__id_delegacion=delegacion_actual)
        else:
            # El Profesional normal SOLO ve sus propias evidencias
            evidencias = evidencias.filter(id_actividad__id_profesional=profesional_actual)
    
    # 3. Lógica de búsqueda (barra de texto)
    if query:
        evidencias = evidencias.filter(
            Q(archivo_vinculo__icontains=query) |
            Q(estado_revision__icontains=query) |
            Q(id_actividad__codigo_unico__icontains=query)
        ).distinct()

    # 4. Armar el diccionario para el HTML
    evidencias_con_validacion = []
    for ev in evidencias:
        validacion = Validacion.objects.filter(id_evidencia=ev).first()
        evidencias_con_validacion.append({
            'evidencia': ev,
            'validacion': validacion
        })
        
    # Menú lateral según el rol (esta pantalla la usan Administrador, Delegado y Profesional)
    if request.user.groups.filter(name='Administrador').exists():
        rol_menu = 'administrador'
    elif request.user.groups.filter(name='Delegado').exists():
        rol_menu = 'delegado'
    else:
        rol_menu = 'profesional'

    return render(request, 'administrador/evidencias/lista_evidencias.html', {
        'evidencias_con_validacion': evidencias_con_validacion,
        'query': query,
        'rol_menu': rol_menu
    })

@login_required
@role_required('Administrador', 'Profesional')
def crear_evidencia(request):
    if request.method == 'POST':
        form = EvidenciaForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    evidencia = form.save(commit=False)
                    evidencia.estado = True
                    
                    evidencia.metadatos = {
                        "registrado_por": request.user.username,
                        "origen": "Plataforma Web Municipal",
                        "fecha_sistema": str(date.today())
                    }
                    
                    evidencia.save()
                    registrar_auditoria(request, "CREACION", "Evidencia", evidencia)
                    
                messages.success(request, 'La evidencia fue registrada con éxito.')
                return redirect('actividadApp:lista_evidencias')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = EvidenciaForm()
        
    return render(request, 'administrador/evidencias/form_evidencia.html', {
        'form': form,
        'titulo': 'Registrar Evidencia'
    })

@login_required
@role_required('Administrador', 'Profesional')
def editar_evidencia(request, id_evidencia):
    evidencia = get_object_or_404(Evidencia, pk=id_evidencia)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(evidencia)
        form = EvidenciaForm(request.POST, instance=evidencia)
        if form.is_valid():
            try:
                with transaction.atomic():
                    evidencia_guardada = form.save()
                    registrar_auditoria(request, "EDICION", "Evidencia", evidencia_guardada, datos_antiguos)
                messages.success(request, 'La evidencia fue actualizada correctamente.')
                return redirect('actividadApp:lista_evidencias')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = EvidenciaForm(instance=evidencia)
        
    return render(request, 'administrador/evidencias/form_evidencia.html', {
        'form': form,
        'titulo': 'Editar Evidencia'
    })

@login_required
@role_required('Administrador', 'Profesional')
def cambiar_estado_evidencia(request, id_evidencia):
    if request.method == 'POST':
        evidencia = get_object_or_404(Evidencia, pk=id_evidencia)
        
        with transaction.atomic():
            datos_antiguos = model_to_dict(evidencia)
            nuevo_estado = not evidencia.estado
            evidencia.estado = nuevo_estado
            evidencia.save()
            registrar_auditoria(request, "CAMBIO_ESTADO", "Evidencia", evidencia, datos_antiguos)
                
        accion_str = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'La evidencia fue {accion_str} correctamente.')
        
    return redirect('actividadApp:lista_evidencias')


def es_solo_delegado(user):
    # Las pantallas de validaciones las usan Delegado y Administrador: decide qué menú lateral mostrar
    return user.groups.filter(name='Delegado').exists() and not user.groups.filter(name='Administrador').exists()

@login_required
@role_required('Administrador', 'Delegado')
def lista_validaciones(request):
    query = request.GET.get('q')
    validaciones = Validacion.objects.all().select_related('id_evidencia', 'id_validador').order_by('-id_validacion')
    
    if query:
        validaciones = validaciones.filter(
            Q(resultado__icontains=query) |
            Q(decision__icontains=query) |
            Q(id_validador__nombres__icontains=query) |
            Q(id_evidencia__archivo_vinculo__icontains=query)
        ).distinct()
        
    return render(request, 'administrador/validaciones/lista_validaciones.html', {
        'validaciones': validaciones,
        'query': query,
        'es_delegado': es_solo_delegado(request.user)
    })

@login_required
@role_required('Administrador', 'Delegado')
def crear_validacion(request):
    evidencia_id = request.GET.get('evidencia')
    initial_data = {}
    
    if evidencia_id:
        evidencia_obj = get_object_or_404(Evidencia, pk=evidencia_id)
        initial_data['id_evidencia'] = evidencia_obj

    if request.method == 'POST':
        form = ValidacionForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    validacion = form.save(commit=False)
                    evidencia = validacion.id_evidencia
                    
                    # [KAN-170] ESCUDO: Bloqueo de suma duplicada
                    if validacion.decision == 'APROBADO':
                        validar_evidencia_no_duplicada(evidencia)
                    
                    validacion.estado = True
                    validacion.save()
                    
                    # [KAN-169] ACCIÓN: Sumar avance solo si está "Aprobada"
                    if validacion.decision == 'APROBADO':
                        # 1. Cambiamos el estado de la evidencia
                        evidencia.estado_revision = 'APROBADO'
                        evidencia.save()
                        
                        # 2. Buscamos el indicador asociado a la meta de esta actividad
                        actividad = evidencia.id_actividad
                        meta = actividad.id_meta
                        indicador = Indicador.objects.filter(meta_id_meta=meta).first()
                        
                        if indicador:
                            indicador.avance += 1 
                            indicador.save()
                            
                            registrar_auditoria(request, "ACTUALIZACION_AVANCE", "Indicador", indicador)

                    registrar_auditoria(request, "CREACION", "Validacion", validacion)
                    
                messages.success(request, 'La validación fue registrada con éxito y el avance ha sido actualizado.')
                return redirect('actividadApp:lista_validaciones')
                
            except ValidationError as e:
                # Si el escudo detecta duplicado, muestra el mensaje de error en rojo
                messages.error(request, str(e.message if hasattr(e, 'message') else e.messages[0]))
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = ValidacionForm(initial=initial_data)
        
    return render(request, 'administrador/validaciones/form_validacion.html', {
        'form': form,
        'titulo': 'Registrar Validación de Evidencia',
        'es_delegado': es_solo_delegado(request.user)
    })

@login_required
@role_required('Administrador', 'Delegado')
def editar_validacion(request, id_validacion):
    validacion = get_object_or_404(Validacion, pk=id_validacion)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(validacion)
        form = ValidacionForm(request.POST, instance=validacion)
        if form.is_valid():
            try:
                with transaction.atomic():
                    validacion_guardada = form.save()
                    registrar_auditoria(request, "EDICION", "Validacion", validacion_guardada, datos_antiguos)
                messages.success(request, 'La validación fue actualizada correctamente.')
                return redirect('actividadApp:lista_validaciones')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = ValidacionForm(instance=validacion)
        
    return render(request, 'administrador/validaciones/form_validacion.html', {
        'form': form,
        'titulo': 'Editar Validación',
        'es_delegado': es_solo_delegado(request.user)
    })

@login_required
@role_required('Administrador', 'Delegado')
def cambiar_estado_validacion(request, id_validacion):
    if request.method == 'POST':
        validacion = get_object_or_404(Validacion, pk=id_validacion)
        
        with transaction.atomic():
            datos_antiguos = model_to_dict(validacion)
            nuevo_estado = not validacion.estado
            validacion.estado = nuevo_estado
            validacion.save()
            registrar_auditoria(request, "CAMBIO_ESTADO", "Validacion", validacion, datos_antiguos)
                
        accion_str = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'La validación fue {accion_str} correctamente.')
        
    return redirect('actividadApp:lista_validaciones')


@login_required
@role_required('Profesional', 'Delegado', 'Administrador')
def lista_gestiones(request, id_actividad):
    """ Muestra la tabla de gestiones para una actividad específica con su barra de búsqueda """
    actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
    gestiones = GestionActividad.objects.filter(actividad=actividad).select_related('tipo_gestion', 'profesional').order_by('-fecha_registro')
    
    # --- FILTRO DE BÚSQUEDA ---
    query = request.GET.get('q')
    if query:
        gestiones = gestiones.filter(
            Q(tipo_gestion__nombre__icontains=query) |
            Q(descripcion__icontains=query)
        ).distinct()
    
    return render(request, 'profesional/lista_gestiones.html', {
        'actividad': actividad,
        'gestiones': gestiones,
        'query': query
    })

@login_required
@role_required('Profesional', 'Delegado', 'Administrador')
def crear_gestion(request, id_actividad):
    actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
    
    if request.method == 'POST':
        form = GestionActividadForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    gestion = form.save(commit=False)
                    gestion.actividad = actividad
                    # Asignamos al profesional que está haciendo el registro
                    gestion.profesional = request.user.profesional 
                    gestion.estado = True
                    gestion.save()
                    
                    # --- AUDITORÍA ---
                    registrar_auditoria(request, "CREACION", "GestionActividad", gestion)
                    
                messages.success(request, 'La gestión fue registrada con éxito.')
                return redirect('actividadApp:lista_gestiones', id_actividad=actividad.id_actividad)
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = GestionActividadForm()
        
    return render(request, 'profesional/form_gestion.html', {
        'form': form,
        'actividad': actividad,
        'titulo': f'Registrar Gestión para {actividad.codigo_unico}'
    })

@login_required
@role_required('Profesional', 'Delegado', 'Administrador')
def editar_gestion(request, id_gestion):
    gestion = get_object_or_404(GestionActividad, id_gestion=id_gestion)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(gestion) # --- AUDITORÍA ---
        form = GestionActividadForm(request.POST, instance=gestion)
        if form.is_valid():
            try:
                with transaction.atomic():
                    gestion_guardada = form.save()
                    
                    # --- AUDITORÍA ---
                    registrar_auditoria(request, "EDICION", "GestionActividad", gestion_guardada, datos_antiguos)
                    
                messages.success(request, 'La gestión fue actualizada correctamente.')
                return redirect('actividadApp:lista_gestiones', id_actividad=gestion.actividad.id_actividad)
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = GestionActividadForm(instance=gestion)
        
    return render(request, 'profesional/form_gestion.html', {
        'form': form,
        'actividad': gestion.actividad,
        'titulo': 'Editar Gestión'
    })

@login_required
@role_required('Profesional', 'Delegado', 'Administrador')
def cambiar_estado_gestion(request, id_gestion):
    if request.method == 'POST':
        gestion = get_object_or_404(GestionActividad, id_gestion=id_gestion)
        
        with transaction.atomic():
            datos_antiguos = model_to_dict(gestion) # --- AUDITORÍA ---
            nuevo_estado = not gestion.estado
            gestion.estado = nuevo_estado
            gestion.save()
            
            # --- AUDITORÍA ---
            registrar_auditoria(request, "CAMBIO_ESTADO", "GestionActividad", gestion, datos_antiguos)
                
        accion_str = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'La gestión fue {accion_str} correctamente.')
        
    return redirect(request.META.get('HTTP_REFERER', '/'))


@login_required
@role_required('Administrador', 'Coordinador')
def lista_todas_gestiones(request):
    query = request.GET.get('q')
    gestiones = GestionActividad.objects.all().select_related('actividad', 'tipo_gestion', 'profesional').order_by('-fecha_registro')
    
    if query:
        gestiones = gestiones.filter(
            Q(actividad__codigo_unico__icontains=query) |
            Q(tipo_gestion__nombre__icontains=query) |
            Q(descripcion__icontains=query)
        ).distinct()
        
    return render(request, 'administrador/gestiones/lista_todas_gestiones.html', {
        'gestiones': gestiones,
        'query': query
    })

@login_required
@role_required('Profesional')
def mis_gestiones(request):
    # Gestiones que registró el profesional que inició sesión, en todas sus actividades
    query = request.GET.get('q')
    gestiones = GestionActividad.objects.filter(profesional=request.user.profesional).select_related('actividad', 'tipo_gestion').order_by('-fecha_registro')

    if query:
        gestiones = gestiones.filter(
            Q(actividad__codigo_unico__icontains=query) |
            Q(tipo_gestion__nombre__icontains=query) |
            Q(descripcion__icontains=query)
        ).distinct()

    return render(request, 'profesional/mis_gestiones.html', {
        'gestiones': gestiones,
        'query': query
    })