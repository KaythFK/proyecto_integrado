from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required
from usuariosApp.decorators import role_required
from actividadApp.models import Actividad, Ausencia
from .models import Meta, Indicador
from .forms import MetaForm, IndicadorForm
from tuboApp.models import Compromiso
from tuboApp.filters import CompromisoFilter
from datetime import date
from django.core.exceptions import ValidationError
from config.utils import validar_periodo_abierto


# --- NUEVOS IMPORTS PARA AUDITORÍA ---
from administracionApp.models import Profesional, Auditoria, Periodo
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
    delegacion_actual = request.user.profesional.id_delegacion
    hoy = date.today()

    periodos = Periodo.objects.order_by('-fecha_inicio')
    periodo = None
    if (request.GET.get('periodo') or '').isdigit():
        periodo = periodos.filter(pk=request.GET['periodo']).first()
    if periodo is None:
        periodo = periodos.filter(estado=True, fecha_inicio__lte=hoy, fecha_termino__gte=hoy).first() or periodos.first()

    actividades_equipo = Actividad.objects.filter(id_profesional__id_delegacion=delegacion_actual, estado=True)
    compromisos_equipo = Compromiso.objects.filter(id_funcionario__id_delegacion=delegacion_actual, estado=True)
    if periodo:
        actividades_equipo = actividades_equipo.filter(id_meta__id_periodo=periodo)
        compromisos_equipo = compromisos_equipo.filter(fecha_comprometida__range=(periodo.fecha_inicio, periodo.fecha_termino))

    filas, cumplimiento_delegacion, semaforo_delegacion, metas_en_rojo = resumen_indicadores(delegacion_actual, periodo)

    context = {
        'delegacion_nombre': delegacion_actual.nombre,
        'periodos': periodos,
        'periodo': periodo,
        'filas': filas,
        'cumplimiento_delegacion': cumplimiento_delegacion,
        'semaforo_delegacion': semaforo_delegacion,
        'metas_en_rojo': metas_en_rojo,
        'total_actividades': actividades_equipo.count(),
        'en_proceso': actividades_equipo.filter(estado_progreso='EN_PROCESO').count(),
        'finalizadas': actividades_equipo.filter(estado_progreso='FINALIZADA').count(),
        'tubo_total': compromisos_equipo.count(),
        'tubo_vencidos': compromisos_equipo.filter(fecha_comprometida__lt=hoy).exclude(estado_progreso='REALIZADO').count(),
    }
    return render(request, 'delegado/dashboard_delegado.html', context)


def semaforo_segun_umbral(cumplimiento, periodo):
    """Umbrales del período; si están guardados como fracción (0.6) se pasan a porcentaje (60)."""
    regular = float(periodo.umbral_regular)
    excelencia = float(periodo.umbral_exelencia)
    if excelencia <= 1:
        regular, excelencia = regular * 100, excelencia * 100
    if cumplimiento >= excelencia:
        return 'VERDE'
    if cumplimiento >= regular:
        return 'AMARILLO'
    return 'ROJO'


def resumen_indicadores(delegacion, periodo):
    """Cumplimiento por funcionario (ponderado por meta, tope 120%) y de la delegación, en pocas consultas."""
    if periodo is None:
        return [], None, None, 0
    metas = list(Meta.objects.filter(id_periodo=periodo, id_funcionario__id_delegacion=delegacion, estado=True)
                 .select_related('id_funcionario', 'id_item'))
    avances = {}
    for ind in Indicador.objects.filter(meta_id_meta__in=metas, estado=True):
        avances[ind.meta_id_meta_id] = avances.get(ind.meta_id_meta_id, 0) + float(ind.avance)

    por_funcionario = {}
    metas_en_rojo = 0
    for meta in metas:
        objetivo = float(meta.valor_objetivo)
        cumplimiento = min(avances.get(meta.pk, 0) / objetivo * 100, 120) if objetivo else 0
        if semaforo_segun_umbral(cumplimiento, periodo) == 'ROJO':
            metas_en_rojo += 1
        fila = por_funcionario.setdefault(meta.id_funcionario_id, {'funcionario': meta.id_funcionario, 'metas': 0, 'suma': 0, 'peso': 0})
        fila['metas'] += 1
        fila['suma'] += cumplimiento * float(meta.ponderador)
        fila['peso'] += float(meta.ponderador)

    filas = []
    for fila in por_funcionario.values():
        fila['cumplimiento'] = round(fila['suma'] / fila['peso'], 1) if fila['peso'] else 0
        fila['semaforo'] = semaforo_segun_umbral(fila['cumplimiento'], periodo)
        filas.append(fila)
    filas.sort(key=lambda f: f['cumplimiento'])

    if not filas:
        return [], None, None, 0
    cumplimiento_delegacion = round(sum(f['cumplimiento'] for f in filas) / len(filas), 1)
    return filas, cumplimiento_delegacion, semaforo_segun_umbral(cumplimiento_delegacion, periodo), metas_en_rojo

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
    ).order_by('fecha_comprometida', 'id_compromiso')

    if query:
        compromisos = compromisos.filter(
            Q(id_actividad__codigo_unico__icontains=query) |
            Q(id_actividad__solicitud_problema__icontains=query) |
            Q(territorio__icontains=query)
        ).distinct()

    hoy = date.today()
    profesionales_equipo = Profesional.objects.filter(id_delegacion=delegacion_actual, estado=True).order_by('nombres')
    filtro = CompromisoFilter(request.GET, queryset=compromisos, responsables=profesionales_equipo)
    ausentes_hoy = set(Ausencia.objects.filter(
        profesional_ausente__id_delegacion=delegacion_actual, estado=True,
        fecha_inicio__lte=hoy, fecha_termino__gte=hoy
    ).values_list('profesional_ausente_id', flat=True))

    context = {
        'compromisos': filtro.qs if filtro.is_valid() else compromisos.none(),
        'filtro': filtro,
        'query': query,
        'delegacion_nombre': delegacion_actual.nombre,
        'profesionales_equipo': profesionales_equipo,
        'ausentes_hoy': ausentes_hoy,
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
    indicadores = Indicador.objects.all().select_related('meta_id_meta__id_periodo').order_by('-id_indicador')
    
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
                # 1. Creamos la instancia sin guardar en BD aún para poder validarla
                indicador = form.save(commit=False)
                
                # 2. Validamos que el período de la meta no esté vencido (KAN-100)
                validar_periodo_abierto(indicador.meta_id_meta)
                
                # 3. Si pasa la validación, guardamos con la transacción
                with transaction.atomic():
                    indicador.estado = True
                    indicador.save() # O form.save() ya que la instancia tiene los datos
                    
                    # --- AUDITORÍA ---
                    registrar_auditoria(request, "CREACION", "Indicador", indicador)
                    
                messages.success(request, 'El indicador fue registrado con éxito.')
                return redirect('monitoreoApp:lista_indicadores')
            except ValidationError as e:
                messages.error(request, e.message)
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
                # 1. Obtenemos el objeto actualizado temporalmente sin guardar
                indicador_modificado = form.save(commit=False)
                
                # 2. Validamos que el período asociado no haya finalizado (KAN-100)
                validar_periodo_abierto(indicador_modificado.meta_id_meta)
                
                # 3. Si pasa la validación, guardamos definitivamente el formulario
                with transaction.atomic():
                    indicador_guardado = form.save()
                    
                    # --- AUDITORÍA ---
                    registrar_auditoria(request, "EDICION", "Indicador", indicador_guardado, datos_antiguos)
                    
                messages.success(request, 'El indicador fue actualizado correctamente.')
                return redirect('monitoreoApp:lista_indicadores')
            except ValidationError as e:
                messages.error(request, e.message)
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