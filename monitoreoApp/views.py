from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required
from usuariosApp.decorators import role_required
from actividadApp.models import Actividad, Ausencia
from .models import HistorialMeta, Meta, Indicador
from .forms import MetaForm, IndicadorForm
from tuboApp.models import Compromiso
from tuboApp.filters import CompromisoFilter
from datetime import date
from django.core.exceptions import ValidationError
from config.utils import validar_periodo_abierto, recordar_filtros, url_con_filtros, delegacion_del_delegado, calcular_porcentaje_cumplimiento, procesar_resumen_dashboard, sincronizar_calculos_indicador
from django.core.exceptions import PermissionDenied
from .filters import MetaFilter
from config.utils import procesar_resumen_dashboard
from django.core.exceptions import ValidationError as CoreValidationError
from administracionApp.models import CargoItem, CatalagoItem, Periodo, Delegacion, Profesional, Auditoria



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
    periodos, periodo = elegir_periodo(request)

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
        'esperado': periodo.porcentaje_esperado() if periodo else None,
        'cumplimiento_delegacion': cumplimiento_delegacion,
        'semaforo_delegacion': semaforo_delegacion,
        'metas_en_rojo': metas_en_rojo,
        'desviaciones_criticas': [f for f in filas if f['desviacion'] == 'ROJO'],
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


def elegir_periodo(request):
    hoy = date.today()
    periodos = Periodo.objects.order_by('-fecha_inicio')
    periodo = None
    if (request.GET.get('periodo') or '').isdigit():
        periodo = periodos.filter(pk=request.GET['periodo']).first()
    if periodo is None:
        periodo = periodos.filter(estado=True, fecha_inicio__lte=hoy, fecha_termino__gte=hoy).first() or periodos.first()
    return periodos, periodo


def estado_desviacion(real, esperado, periodo):
    """Regla de la matriz del cliente: verde si alcanza lo esperado al día, amarillo si llega a umbral_regular × esperado, rojo bajo eso."""
    regular = float(periodo.umbral_regular)
    if regular > 1:
        regular = regular / 100
    if real >= esperado:
        return 'VERDE'
    if real >= esperado * regular:
        return 'AMARILLO'
    return 'ROJO'


def resumen_indicadores(delegacion, periodo, profesional=None):
    """
    Vista delgada: Solo realiza las consultas (QuerySets) correctas a la BD 
    y delega TODA la validación y matemática a config/utils.py.
    """
    if periodo is None:
        return [], None, None, 0
        
    # Consultas usando la arquitectura corregida (sin pedirle el funcionario a la Meta)
    metas = Meta.objects.filter(id_periodo=periodo, estado=True).select_related('id_cargo_item__id_cargo', 'id_cargo_item__id_item')
    indicadores = Indicador.objects.filter(meta_id_meta__in=metas, estado=True).select_related('id_funcionario__id_delegacion')
    
    modo = 'delegacion' # Por defecto, agrupa por delegaciones (Dashboard Coordinador)
    
    # Filtros según quién está mirando
    if delegacion is not None:
        indicadores = indicadores.filter(id_funcionario__id_delegacion=delegacion)
        modo = 'funcionario' # Si mira un Delegado, agrupamos por sus funcionarios
        
    if profesional is not None:
        indicadores = indicadores.filter(id_funcionario=profesional)
        modo = 'funcionario'
        
    esperado = periodo.porcentaje_esperado()
    
    # Se envía la data cruda a utils.py para que devuelva la tabla calculada
    return procesar_resumen_dashboard(metas, indicadores, periodo, esperado, modo_agrupacion=modo)

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
def equipo_de(delegacion):
    return Profesional.objects.filter(id_delegacion=delegacion, estado=True)


def validar_meta_de_su_delegacion(user, meta):
    delegacion = delegacion_del_delegado(user)
    if delegacion is not None and meta.id_funcionario.id_delegacion_id != delegacion.pk:
        raise PermissionDenied('No tienes permiso para modificar esta meta: pertenece a otra delegación.')


def limitar_funcionarios_meta(user, form):
    delegacion = delegacion_del_delegado(user)
    if delegacion is not None:
        form.fields['id_funcionario'].queryset = equipo_de(delegacion)


@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def listar_metas(request):
    metas = Meta.objects.select_related('id_cargo_item', 'id_periodo', 'autor').order_by('-id_meta')
    delegacion = delegacion_del_delegado(request.user)
    if delegacion is not None:
        filtro = MetaFilter(request.GET, queryset=metas, ocultar=('delegacion',))
    else:
        filtro = MetaFilter(request.GET, queryset=metas)
    recordar_filtros(request, 'monitoreoApp:listar_metas')

    context = {
        'metas': filtro.qs if filtro.is_valid() else metas.none(),
        'filtro': filtro,
        'query': request.GET.get('q'),
        'url_retorno': obtener_url_retorno(request.user),
    }
    return render(request, 'monitoreo/lista_metas.html', context)

@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def crear_meta(request):
    if request.method == 'POST':
        form = MetaForm(request.POST)
        limitar_funcionarios_meta(request.user, form)
        if form.is_valid():
            try:
                with transaction.atomic():
                    meta = form.save(commit=False)
                    meta.estado = True

                    # --- AQUÍ VA KAN-209 (asignar autor antes de guardar en BD) ---
                    profesional = getattr(request.user, 'profesional', None)
                    if not profesional and request.user.is_authenticated:
                        profesional = Profesional.objects.filter(usuario=request.user).first()
                    meta.autor = profesional
                    # fecha_creacion se llena sola por auto_now_add=True en el modelo

                    meta.save()

                    # --- AUDITORÍA ---
                    registrar_auditoria(request, "CREACION", "Meta", meta)

                messages.success(request, 'La meta se ha registrado correctamente.')
                return redirect(url_con_filtros(request, 'monitoreoApp:listar_metas'))
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Corrige los errores del formulario.')
    else:
        form = MetaForm()
        limitar_funcionarios_meta(request.user, form)

    context = {
        'form': form,
        'titulo': 'Registrar Nueva Meta',
        'url_listado': url_con_filtros(request, 'monitoreoApp:listar_metas'),
        'url_retorno': obtener_url_retorno(request.user),
    }
    return render(request, 'monitoreo/form_meta.html', context)

@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def editar_meta(request, meta_id):
    meta = get_object_or_404(Meta, id_meta=meta_id) 
    validar_meta_de_su_delegacion(request.user, meta) 
    try:
        validar_periodo_abierto(meta) 
    except CoreValidationError as e:
        msg = str(e.message if hasattr(e, 'message') else e.messages[0]) 
        messages.error(request, msg) 
        return redirect(url_con_filtros(request, 'monitoreoApp:listar_metas')) 

    if request.method == 'POST':
        datos_antiguos = model_to_dict(meta) 
        form = MetaForm(request.POST, instance=meta) 
        limitar_funcionarios_meta(request.user, form) 
        if form.is_valid():
            try:
                with transaction.atomic():
                    meta_guardada = form.save(commit=False) 
                    version_anterior = datos_antiguos.get('version') or 1 
                    meta_guardada.version = int(version_anterior) + 1 
                    meta_guardada.save() 

                    profesional = getattr(request.user, 'profesional', None)
                    if not profesional and request.user.is_authenticated:
                        profesional = Profesional.objects.filter(usuario=request.user).first() 
                    HistorialMeta.objects.create(
                        meta=meta_guardada,
                        version=meta_guardada.version, 
                        autor=profesional, 
                        id_periodo=meta_guardada.id_periodo, 
                    )

                    registrar_auditoria(request, "EDICION", "Meta", meta_guardada, datos_antiguos) 

                messages.success(request, 'La meta se ha actualizado correctamente.') 
                return redirect(url_con_filtros(request, 'monitoreoApp:listar_metas')) 
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}') 
        else:
            messages.error(request, 'Corrige los errores del formulario.') 
    else:
        form = MetaForm(instance=meta) 
        limitar_funcionarios_meta(request.user, form) 

    context = {
        'form': form, 
        'titulo': f'Editar Meta #{meta.id_meta}', 
        'url_listado': url_con_filtros(request, 'monitoreoApp:listar_metas'),
        'url_retorno': obtener_url_retorno(request.user), 
    }
    return render(request, 'monitoreo/form_meta.html', context) 

@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def cambiar_estado_meta(request, id_meta):
    if request.method == 'POST':
        meta = get_object_or_404(Meta, id_meta=id_meta)
        validar_meta_de_su_delegacion(request.user, meta)
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
            
    return redirect(url_con_filtros(request, 'monitoreoApp:listar_metas'))



@login_required
@role_required('Administrador', 'Coordinador', 'Profesional')
def lista_indicadores(request):
    query = request.GET.get('q')
    indicadores = Indicador.objects.all().select_related('meta_id_meta__id_periodo').order_by('-id_indicador')
    if request.user.groups.filter(name='Profesional').exists():
        indicadores = indicadores.filter(meta_id_meta__id_funcionario=request.user.profesional)
    
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
                indicador = form.save(commit=False)
                validar_periodo_abierto(indicador.meta_id_meta)

                meta = indicador.meta_id_meta
                indicador.cumplimiento = calcular_porcentaje_cumplimiento(
                    indicador.avance,
                    meta.valor_objetivo
                )
                if getattr(meta, 'id_periodo', None):
                    indicador.semaforo = semaforo_segun_umbral(
                        indicador.cumplimiento,
                        meta.id_periodo
                    )

                with transaction.atomic():
                    indicador.estado = True
                    indicador.save()
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
                indicador_modificado = form.save(commit=False)
                validar_periodo_abierto(indicador_modificado.meta_id_meta)

                meta = indicador_modificado.meta_id_meta
                indicador_modificado.cumplimiento = calcular_porcentaje_cumplimiento(
                    indicador_modificado.avance,
                    meta.valor_objetivo
                )
                if getattr(meta, 'id_periodo', None):
                    indicador_modificado.semaforo = semaforo_segun_umbral(
                        indicador_modificado.cumplimiento,
                        meta.id_periodo
                    )

                with transaction.atomic():
                    indicador_guardado = indicador_modificado.save() or indicador_modificado
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


@login_required
@role_required('Administrador', 'Coordinador')
def tablero_metas_coordinador(request):
    periodos, periodo_activo = elegir_periodo(request)

    # Si no viene parámetro 'periodo' en GET y existe uno vigente, preseleccionamos el vigente
    data_filtro = request.GET.copy()
    if 'periodo' not in data_filtro and periodo_activo:
        data_filtro['periodo'] = str(periodo_activo.pk)

    metas_base = Meta.objects.select_related(
        'id_cargo_item__id_cargo',
        'id_cargo_item__id_item',
        'id_periodo',
        'autor',
    ).order_by('id_cargo_item__id_cargo__nombre', 'id_cargo_item__id_item__nombre', '-id_meta')

    filtro = MetaFilter(data_filtro, queryset=metas_base)
    metas_qs = filtro.qs if filtro.is_valid() else metas_base.none()

    estado_param = request.GET.get('estado', '').strip()
    if estado_param == 'activo':
        metas_qs = metas_qs.filter(estado=True)
    elif estado_param == 'inactivo':
        metas_qs = metas_qs.filter(estado=False)

    # Período efectivo seleccionado para diagnósticos de cobertura y ponderación
    periodo_sel_id = data_filtro.get('periodo', '').strip()
    periodo_diagnostico = (
        Periodo.objects.filter(pk=int(periodo_sel_id)).first()
        if periodo_sel_id.isdigit()
        else periodo_activo
    )

    cargos_items_activos = CargoItem.objects.filter(
        estado=True,
        id_cargo__estado=True,
        id_item__estado=True,
    ).select_related('id_cargo', 'id_item').order_by('id_cargo__nombre', 'id_item__nombre')

    faltantes_cargo_item = []
    resumen_ponderacion_cargos = []

    if periodo_diagnostico:
        metas_periodo_activas = Meta.objects.filter(
            id_periodo=periodo_diagnostico,
            estado=True,
        ).select_related('id_cargo_item__id_cargo', 'id_cargo_item__id_item')

        ids_asignados = set(metas_periodo_activas.values_list('id_cargo_item_id', flat=True))
        faltantes_cargo_item = [ci for ci in cargos_items_activos if ci.pk not in ids_asignados]

        # Agrupar suma de ponderadores por Cargo en el período
        por_cargo = {}
        for m in metas_periodo_activas:
            cargo_obj = m.id_cargo_item.id_cargo
            entry = por_cargo.setdefault(cargo_obj.pk, {
                'cargo': cargo_obj.nombre,
                'suma_ponderador': 0,
                'cantidad_metas': 0,
            })
            entry['suma_ponderador'] += float(m.ponderador)
            entry['cantidad_metas'] += 1

        for entry in por_cargo.values():
            entry['suma_ponderador'] = round(entry['suma_ponderador'], 2)
            entry['completo'] = (entry['suma_ponderador'] == 100.0)
            resumen_ponderacion_cargos.append(entry)
        resumen_ponderacion_cargos.sort(key=lambda x: x['cargo'])

    # Guardamos filtros para que editar / cambiar estado vuelvan al tablero con los mismos filtros
    recordar_filtros(request, 'monitoreoApp:tablero_metas_coordinador')

    context = {
        'metas': metas_qs,
        'filtro': filtro,
        'periodo_diagnostico': periodo_diagnostico,
        'estado_seleccionado': estado_param,
        'total_metas': metas_qs.count(),
        'metas_activas': metas_qs.filter(estado=True).count(),
        'metas_inactivas': metas_qs.filter(estado=False).count(),
        'faltantes_cargo_item': faltantes_cargo_item,
        'resumen_ponderacion_cargos': resumen_ponderacion_cargos,
        'url_retorno': obtener_url_retorno(request.user),
    }
    return render(request, 'coordinador/tablero_metas.html', context)


@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def historial_meta(request, meta_id):
    meta = get_object_or_404(
        Meta.objects.select_related(
            'id_cargo_item__id_cargo',
            'id_cargo_item__id_item',
            'id_periodo',
            'autor',
        ),
        id_meta=meta_id,
    )

    registros_historial = (
        HistorialMeta.objects.filter(meta=meta)
        .select_related('autor', 'id_periodo')
        .order_by('version', 'fecha_modificacion')
    )

    versiones = [
        {
            'version': 1,
            'fecha': meta.fecha_creacion,
            'autor': meta.autor,
            'periodo': meta.id_periodo,
            'es_creacion': True,
        }
    ]

    for reg in registros_historial:
        versiones.append({
            'version': reg.version,
            'fecha': reg.fecha_modificacion,
            'autor': reg.autor,
            'periodo': reg.id_periodo,
            'es_creacion': False,
        })

    # Ordenamos de la versión más reciente a la más antigua
    versiones.sort(key=lambda item: item['version'], reverse=True)

    if request.user.groups.filter(name__in=['Administrador', 'Coordinador']).exists():
        url_volver = url_con_filtros(request, 'monitoreoApp:tablero_metas_coordinador')
    else:
        url_volver = url_con_filtros(request, 'monitoreoApp:listar_metas')

    context = {
        'meta': meta,
        'versiones': versiones,
        'url_volver': url_volver,
    }
    return render(request, 'coordinador/historial_metas.html', context)


@login_required
@role_required('Administrador', 'Coordinador')
def cambiar_estado_meta_tablero(request, id_meta):
    if request.method == 'POST':
        meta = get_object_or_404(Meta, id_meta=id_meta)
        try:
            with transaction.atomic():
                datos_antiguos = model_to_dict(meta)
                nuevo_estado = not meta.estado
                meta.estado = nuevo_estado
                meta.save()

                registrar_auditoria(request, "CAMBIO_ESTADO", "Meta", meta, datos_antiguos)

                accion = "habilitada" if nuevo_estado else "inhabilitada"
                messages.success(request, f'La meta #{meta.id_meta} fue {accion} correctamente.')
        except Exception as e:
            messages.error(request, f'Error al cambiar el estado: {str(e)}')

    return redirect(url_con_filtros(request, 'monitoreoApp:tablero_metas_coordinador'))


@login_required
@role_required('Administrador', 'Coordinador')
def tablero_indicadores_coordinador(request):
    periodos, periodo_activo = elegir_periodo(request)
    delegaciones = Delegacion.objects.order_by('nombre')

    indicadores_qs = Indicador.objects.select_related(
        'meta_id_meta__id_periodo',
        'meta_id_meta__id_cargo_item__id_cargo',
        'meta_id_meta__id_cargo_item__id_item',
        'id_funcionario__id_delegacion',
    ).order_by('id_funcionario__id_delegacion__nombre', '-id_indicador')

    periodo_param = request.GET.get('periodo', '').strip()
    if not periodo_param and periodo_activo:
        periodo_param = str(periodo_activo.pk)
    if periodo_param.isdigit():
        indicadores_qs = indicadores_qs.filter(meta_id_meta__id_periodo_id=int(periodo_param))

    delegacion_param = request.GET.get('delegacion', '').strip()
    if delegacion_param.isdigit():
        indicadores_qs = indicadores_qs.filter(id_funcionario__id_delegacion_id=int(delegacion_param))

    semaforo_param = request.GET.get('semaforo', '').strip()
    if semaforo_param in {'VERDE', 'AMARILLO', 'ROJO'}:
        indicadores_qs = indicadores_qs.filter(semaforo=semaforo_param)

    estado_param = request.GET.get('estado', '').strip()
    if estado_param == 'activo':
        indicadores_qs = indicadores_qs.filter(estado=True)
    elif estado_param == 'inactivo':
        indicadores_qs = indicadores_qs.filter(estado=False)

    query = request.GET.get('q', '').strip()
    if query:
        indicadores_qs = indicadores_qs.filter(
            Q(meta_id_meta__unidad__icontains=query)
            | Q(meta_id_meta__id_cargo_item__id_cargo__nombre__icontains=query)
            | Q(meta_id_meta__id_cargo_item__id_item__nombre__icontains=query)
            | Q(id_funcionario__nombres__icontains=query)
            | Q(id_funcionario__apellidos__icontains=query)
            | Q(id_funcionario__id_delegacion__nombre__icontains=query)
        ).distinct()

    indicadores_lista = list(indicadores_qs)
    for ind in indicadores_lista:
        try:
            sincronizar_calculos_indicador(ind, guardar=True)
        except ValidationError:
            pass

    recordar_filtros(request, 'monitoreoApp:tablero_indicadores_coordinador')

    context = {
        'indicadores': indicadores_lista,
        'periodos': periodos,
        'delegaciones': delegaciones,
        'periodo_seleccionado': periodo_param,
        'delegacion_seleccionada': delegacion_param,
        'semaforo_seleccionado': semaforo_param,
        'estado_seleccionado': estado_param,
        'query': query,
        'total_indicadores': len(indicadores_lista),
        'total_verde': sum(1 for i in indicadores_lista if i.semaforo == 'VERDE'),
        'total_amarillo': sum(1 for i in indicadores_lista if i.semaforo == 'AMARILLO'),
        'total_rojo': sum(1 for i in indicadores_lista if i.semaforo == 'ROJO'),
        'url_retorno': obtener_url_retorno(request.user),
    }
    return render(request, 'coordinador/tablero_indicadores.html', context)


@login_required
@role_required('Administrador', 'Coordinador')
def cambiar_estado_indicador_tablero(request, id_indicador):
    if request.method == 'POST':
        indicador = get_object_or_404(Indicador, id_indicador=id_indicador)
        try:
            with transaction.atomic():
                datos_antiguos = model_to_dict(indicador)
                nuevo_estado = not indicador.estado
                indicador.estado = nuevo_estado
                indicador.save()

                registrar_auditoria(request, "CAMBIO_ESTADO", "Indicador", indicador, datos_antiguos)

                accion = "habilitado" if nuevo_estado else "inhabilitado"
                messages.success(request, f'El indicador #{indicador.id_indicador} fue {accion} correctamente.')
        except Exception as e:
            messages.error(request, f'Error al cambiar el estado: {str(e)}')

    return redirect(url_con_filtros(request, 'monitoreoApp:tablero_indicadores_coordinador'))