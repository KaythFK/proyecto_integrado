from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required
from usuariosApp.decorators import role_required
from actividadApp.models import Actividad
from .models import Meta, Indicador
from .forms import MetaForm, IndicadorForm
from tuboApp.models import Compromiso
from datetime import date


# --- NUEVOS IMPORTS PARA AUDITORÍA ---
from administracionApp.models import Profesional, Auditoria
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

# --- FUNCIÓN AUXILIAR PARA RUTA DINÁMICA ---
def obtener_url_retorno(user):
    """Devuelve la ruta del dashboard correspondiente según el rol del usuario."""
    if user.groups.filter(name='Administrador').exists():
        return 'administracionApp:dashboard_admin'
    elif user.groups.filter(name='Coordinador').exists():
        return 'tuboApp:dashboard_coordinador'
    else:
        return 'monitoreoApp:dashboard_delegado'


# --- VISTAS ORIGINALES DEL DELEGADO ---

@login_required
@role_required('Delegado')
def dashboard_delegado(request):
    """ UML: consultarResumenEjecutivo() """
    # 1. Obtener la delegación del delegado conectado
    delegacion_actual = request.user.profesional.id_delegacion
    
    # 2. Métricas de Actividades (Solo de su equipo)
    actividades_equipo = Actividad.objects.filter(id_profesional__id_delegacion=delegacion_actual, estado=True)
    total_actividades = actividades_equipo.count()
    en_proceso = actividades_equipo.filter(estado_progreso='EN_PROCESO').count()
    finalizadas = actividades_equipo.filter(estado_progreso='FINALIZADA').count()
    
    # 3. Métricas del Tubo de Compromisos (Solo de su equipo)
    compromisos_equipo = Compromiso.objects.filter(id_funcionario__id_delegacion=delegacion_actual, estado=True)
    tubo_total = compromisos_equipo.count()
    tubo_vencidos = compromisos_equipo.filter(fecha_comprometida__lt=date.today()).exclude(estado_progreso='REALIZADO').count()
    
    context = {
        'total_actividades': total_actividades,
        'en_proceso': en_proceso,
        'finalizadas': finalizadas,
        'tubo_total': tubo_total,
        'tubo_vencidos': tubo_vencidos,
        'delegacion_nombre': delegacion_actual.nombre,
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

@login_required
@role_required('Delegado')
def tubo_delegacion(request):
    """ UML: monitorearCompromisos(filtros) """
    query = request.GET.get('q')
    delegacion_actual = request.user.profesional.id_delegacion
    
    # Filtro estricto: Solo compromisos de funcionarios que pertenecen a la delegación del usuario
    compromisos = Compromiso.objects.filter(
        id_funcionario__id_delegacion=delegacion_actual
    ).order_by('-fecha_comprometida')

    if query:
        compromisos = compromisos.filter(
            Q(id_actividad__codigo_unico__icontains=query) |
            Q(id_actividad__solicitud_problema__icontains=query) |
            Q(territorio__icontains=query)
        ).distinct()
        
    context = {
        'compromisos': compromisos,
        'query': query,
        'delegacion_nombre': delegacion_actual.nombre
    }
    return render(request, 'delegado/lista_tubo_delegado.html', context)


# --- NUEVAS VISTAS DE GESTIÓN DE METAS ---
@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def listar_metas(request):
    query = request.GET.get('q')
    metas = Meta.objects.select_related('id_item', 'id_periodo', 'id_funcionario').all().order_by('-id_meta')

    if query:
        metas = metas.filter(
            Q(unidad__icontains=query) |
            Q(valor_objetivo__icontains=query) |
            Q(id_item__nombre__icontains=query)
        ).distinct()

    context = {
        'metas': metas,
        'query': query,
        'url_retorno': obtener_url_retorno(request.user),
    }
    return render(request, 'monitoreo/lista_metas.html', context)


@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def crear_meta(request):
    if request.method == 'POST':
        form = MetaForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    meta = form.save(commit=False)
                    meta.estado = True
                    meta.save()
                    
                    # --- AUDITORÍA ---
                    registrar_auditoria(request, "CREACION", "Meta", meta)
                    
                messages.success(request, 'La meta se ha registrado correctamente.')
                return redirect('monitoreoApp:listar_metas')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Corrige los errores del formulario.')
    else:
        form = MetaForm()
        
    context = {
        'form': form, 
        'titulo': 'Registrar Nueva Meta',
        'url_retorno': obtener_url_retorno(request.user),
    }
    return render(request, 'monitoreo/form_meta.html', context)

@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def editar_meta(request, id_meta):
    meta = get_object_or_404(Meta, id_meta=id_meta)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(meta) # --- AUDITORÍA ---
        form = MetaForm(request.POST, instance=meta)
        if form.is_valid():
            try:
                with transaction.atomic():
                    meta_guardada = form.save()
                    
                    # --- AUDITORÍA ---
                    registrar_auditoria(request, "EDICION", "Meta", meta_guardada, datos_antiguos)
                    
                messages.success(request, 'La meta se ha actualizado correctamente.')
                return redirect('monitoreoApp:listar_metas')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = MetaForm(instance=meta)
        
    context = {
        'form': form, 
        'titulo': f'Editar Meta #{meta.id_meta}',
        'url_retorno': obtener_url_retorno(request.user),
    }
    return render(request, 'monitoreo/form_meta.html', context)

@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def cambiar_estado_meta(request, id_meta):
    if request.method == 'POST':
        meta = get_object_or_404(Meta, id_meta=id_meta)
        try:
            with transaction.atomic():
                datos_antiguos = model_to_dict(meta) # --- AUDITORÍA ---
                nuevo_estado = not meta.estado
                meta.estado = nuevo_estado
                meta.save()
                
                # --- AUDITORÍA ---
                registrar_auditoria(request, "CAMBIO_ESTADO", "Meta", meta, datos_antiguos)
                
                accion = "habilitada" if nuevo_estado else "inhabilitada"
                messages.success(request, f'La meta #{meta.id_meta} fue {accion} correctamente.')
        except Exception as e:
            messages.error(request, f'Error al cambiar el estado: {str(e)}')
            
    return redirect('monitoreoApp:listar_metas')



@login_required
@role_required('Administrador', 'Coordinador', 'Profesional')
def lista_indicadores(request):
    query = request.GET.get('q')
    indicadores = Indicador.objects.all().select_related('meta_id_meta').order_by('-id_indicador')
    
    if query:
        indicadores = indicadores.filter(
            Q(semaforo__icontains=query) |
            Q(meta_id_meta__unidad__icontains=query)
        ).distinct()
        
    return render(request, 'administrador/indicadores/lista_indicadores.html', {
        'indicadores': indicadores,
        'query': query
    })

@login_required
@role_required('Administrador', 'Coordinador')
def crear_indicador(request):
    if request.method == 'POST':
        form = IndicadorForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    indicador = form.save(commit=False)
                    indicador.estado = True
                    indicador.save()
                    
                    # --- AUDITORÍA ---
                    registrar_auditoria(request, "CREACION", "Indicador", indicador)
                    
                messages.success(request, 'El indicador fue registrado con éxito.')
                return redirect('monitoreoApp:lista_indicadores')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = IndicadorForm()
        
    return render(request, 'administrador/indicadores/form_indicador.html', {
        'form': form,
        'titulo': 'Registrar Nuevo Indicador'
    })

@login_required
@role_required('Administrador', 'Coordinador')
def editar_indicador(request, id_indicador):
    indicador = get_object_or_404(Indicador, id_indicador=id_indicador)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(indicador) # --- AUDITORÍA ---
        form = IndicadorForm(request.POST, instance=indicador)
        if form.is_valid():
            try:
                with transaction.atomic():
                    indicador_guardado = form.save()
                    
                    # --- AUDITORÍA ---
                    registrar_auditoria(request, "EDICION", "Indicador", indicador_guardado, datos_antiguos)
                    
                messages.success(request, 'El indicador fue actualizado correctamente.')
                return redirect('monitoreoApp:lista_indicadores')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = IndicadorForm(instance=indicador)
        
    return render(request, 'administrador/indicadores/form_indicador.html', {
        'form': form,
        'titulo': f'Editar Indicador #{indicador.id_indicador}'
    })

@login_required
@role_required('Administrador', 'Coordinador')
def cambiar_estado_indicador(request, id_indicador):
    if request.method == 'POST':
        indicador = get_object_or_404(Indicador, id_indicador=id_indicador)
        
        with transaction.atomic():
            datos_antiguos = model_to_dict(indicador) # --- AUDITORÍA ---
            nuevo_estado = not indicador.estado
            indicador.estado = nuevo_estado
            indicador.save()
            
            # --- AUDITORÍA ---
            registrar_auditoria(request, "CAMBIO_ESTADO", "Indicador", indicador, datos_antiguos)
                
        accion_str = "habilitado" if nuevo_estado else "inhabilitado"
        messages.success(request, f'El indicador #{indicador.id_indicador} fue {accion_str} correctamente.')
        
    return redirect('monitoreoApp:lista_indicadores')