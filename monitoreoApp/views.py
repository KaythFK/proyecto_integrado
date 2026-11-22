from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import OuterRef, Q, Subquery
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required
from usuariosApp.decorators import role_required
from actividadApp.models import Actividad, Ausencia
from actividadApp.forms import etiqueta_meta
from .models import Alerta, HistorialMeta, Meta, Indicador, ReglaAlerta
from .services import dias_aviso_vencimiento, dias_umbral_sin_registros, funcionarios_a_monitorear, uso_de_funcionarios, generar_alertas, registrar_incumplimientos, resumen_compromisos, tipo_de_alerta, asegurar_indicadores_para_tablero, sincronizar_indicador
from .forms import MetaForm, IndicadorForm, ReglaAlertaForm
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponse, request
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_POST
from tuboApp.models import Compromiso, HistorialIncumplimiento
from tuboApp.filters import CompromisoFilter, buscar_compromisos
from datetime import date, timedelta
from django.core.exceptions import ValidationError
from config.utils import validar_periodo_abierto, recordar_filtros, url_con_filtros, delegacion_del_delegado, calcular_porcentaje_cumplimiento, procesar_resumen_dashboard, sincronizar_calculos_indicador 
from django.core.exceptions import PermissionDenied
from .filters import MetaFilter
from config.utils import procesar_resumen_dashboard
from django.core.exceptions import ValidationError as CoreValidationError
from administracionApp.models import Cargo, CargoItem, CatalagoItem, Periodo, Delegacion, Profesional, Auditoria



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
        if profesional_actual is None:
            print(f"Auditoría omitida: {request.user} no tiene un perfil de funcionario asociado.")
            return
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
    rezagados = resultados_bajo_umbral(delegacion_actual, periodo)
    umbral_sin_registros = dias_umbral_sin_registros(hoy)
    sin_registros = [f for f in uso_de_funcionarios(funcionarios_a_monitorear(delegacion_actual), periodo, umbral_sin_registros, hoy)
                     if f['supera_umbral']]

    context = {
        'delegacion_nombre': delegacion_actual.nombre,
        'periodos': periodos,
        'periodo': periodo,
        'filas': filas,
        'esperado': periodo.porcentaje_esperado() if periodo else None,
        'cumplimiento_delegacion': cumplimiento_delegacion,
        'semaforo_delegacion': semaforo_delegacion,
        'metas_en_rojo': metas_en_rojo,
        'rezagados': rezagados,
        'desviaciones_criticas': [f for f in filas if f['desviacion'] == 'ROJO'],
        'total_actividades': actividades_equipo.count(),
        'en_proceso': actividades_equipo.filter(estado_progreso='EN_PROCESO').count(),
        'finalizadas': actividades_equipo.filter(estado_progreso='FINALIZADA').count(),
        'tubo': resumen_compromisos(compromisos_equipo, hoy),
        'dias_aviso': dias_aviso_vencimiento(hoy),
        'sin_registros': sin_registros,
        'umbral_sin_registros': umbral_sin_registros,
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


def cumplimiento_de(indicador):
    """Misma fórmula del panel: base topada en 120 %, más el ajuste por retroalimentaciones, acotada entre 0 % y 120 %."""
    objetivo = float(indicador.meta_id_meta.valor_objetivo or 0)
    if not objetivo:
        return None
    base = min(float(indicador.avance) / objetivo * 100, 120.0)
    return max(0.0, min(base + float(indicador.ajuste or 0), 120.0))


def registros_de_origen(meta, funcionario):
    """Actividades activas con evidencia aprobada que forman el avance de un funcionario en una meta."""
    return (Actividad.objects
            .filter(id_meta=meta, id_profesional=funcionario, estado=True,
                    evidencia__estado=True, evidencia__estado_revision='APROBADO')
            .distinct().order_by('-fecha_registro'))


def umbrales_en_porcentaje(periodo):
    regular, excelencia = float(periodo.umbral_regular), float(periodo.umbral_exelencia)
    if excelencia <= 1:
        regular, excelencia = regular * 100, excelencia * 100
    return regular, excelencia


def resultados_bajo_umbral(delegacion, periodo):
    """Indicadores del equipo en rojo, cada uno con su meta y las actividades aprobadas que forman su avance."""
    if periodo is None:
        return []
    indicadores = (Indicador.objects
                   .filter(estado=True, meta_id_meta__estado=True, meta_id_meta__id_periodo=periodo,
                           id_funcionario__id_delegacion=delegacion)
                   .select_related('id_funcionario', 'meta_id_meta__id_periodo', 'meta_id_meta__id_cargo_item__id_item'))
    resultados = []
    for indicador in indicadores:
        meta = indicador.meta_id_meta
        cumplimiento = cumplimiento_de(indicador)
        if cumplimiento is None or semaforo_segun_umbral(cumplimiento, periodo) != 'ROJO':
            continue
        registros = registros_de_origen(meta, indicador.id_funcionario)
        resultados.append({
            'indicador': indicador,
            'funcionario': indicador.id_funcionario,
            'meta': etiqueta_meta(meta),
            'objetivo': meta.valor_objetivo,
            'avance': indicador.avance,
            'ajuste': indicador.ajuste or 0,
            'cumplimiento': round(cumplimiento, 1),
            'registros': registros,
        })
    resultados.sort(key=lambda r: r['cumplimiento'])
    return resultados

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
    ).annotate(fecha_incumplimiento=Subquery(
        HistorialIncumplimiento.objects.filter(compromiso=OuterRef('pk'), estado=True).values('fecha_vencimiento')[:1]
    )).order_by('fecha_comprometida', 'id_compromiso')

    if query:
        compromisos = buscar_compromisos(compromisos, query)

    hoy = date.today()
    registrar_incumplimientos(hoy)
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
        'hoy': hoy,
        'limite_aviso': hoy + timedelta(days=dias_aviso_vencimiento(hoy)),
    }
    return render(request, 'delegado/lista_tubo_delegado.html', context)


# --- NUEVAS VISTAS DE GESTIÓN DE METAS ---
def equipo_de(delegacion):
    return Profesional.objects.filter(id_delegacion=delegacion, estado=True)


def cargos_del_equipo(user):
    delegacion = delegacion_del_delegado(user)
    if delegacion is None:
        return None
    return Cargo.objects.filter(profesional__id_delegacion=delegacion, profesional__estado=True).distinct()


def validar_meta_de_su_equipo(user, meta):
    cargos = cargos_del_equipo(user)
    if cargos is not None and not cargos.filter(pk=meta.id_cargo_item.id_cargo_id).exists():
        raise PermissionDenied('No tienes permiso para modificar esta meta: no corresponde a un cargo de tu equipo.')


@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def listar_metas(request):
    metas = Meta.objects.select_related('id_cargo_item', 'id_periodo', 'autor').order_by('-id_meta')
    cargos = cargos_del_equipo(request.user)
    if cargos is not None:
        metas = metas.filter(id_cargo_item__id_cargo__in=cargos)
    filtro = MetaFilter(request.GET, queryset=metas)
    if cargos is not None:
        filtro.filters['cargo'].queryset = cargos.order_by('nombre')
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
        form = MetaForm(request.POST, cargos=cargos_del_equipo(request.user))
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

                    hoy = date.today()
                    if meta.fecha_inicio and meta.fecha_inicio > hoy:
                        messages.info(
                            request,
                            f"La meta regirá desde el {meta.fecha_inicio.strftime('%d/%m/%Y')} y no altera períodos cerrados."
                        )
                    elif meta.id_periodo and meta.id_periodo.esta_abierto:
                        from .services import asegurar_indicadores_profesional
                        for prof in Profesional.objects.filter(id_cargo_id=meta.id_cargo_item.id_cargo_id, estado=True):
                            asegurar_indicadores_profesional(prof, periodo_id=meta.id_periodo_id, fecha_referencia=hoy)

                messages.success(request, 'La meta se ha registrado correctamente.')
                return redirect(url_con_filtros(request, 'monitoreoApp:listar_metas'))
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Corrige los errores del formulario.')
    else:
        form = MetaForm(cargos=cargos_del_equipo(request.user))

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
    validar_meta_de_su_equipo(request.user, meta)
    try:
        validar_periodo_abierto(meta)
    except CoreValidationError as e:
        msg = str(e.message if hasattr(e, 'message') else e.messages[0])
        messages.error(request, msg)
        return redirect(url_con_filtros(request, 'monitoreoApp:listar_metas'))

    if request.method == 'POST':
        datos_antiguos = model_to_dict(meta)
        form = MetaForm(request.POST, instance=meta, cargos=cargos_del_equipo(request.user))
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

                    hoy = date.today()
                    if meta_guardada.fecha_inicio and meta_guardada.fecha_inicio > hoy:
                        messages.info(
                            request,
                            f"La actualización regirá desde el {meta_guardada.fecha_inicio.strftime('%d/%m/%Y')} y no modifica períodos cerrados."
                        )
                    elif meta_guardada.id_periodo and meta_guardada.id_periodo.esta_abierto:
                        from .services import asegurar_indicadores_profesional
                        for prof in Profesional.objects.filter(id_cargo_id=meta_guardada.id_cargo_item.id_cargo_id, estado=True):
                            asegurar_indicadores_profesional(prof, periodo_id=meta_guardada.id_periodo_id, fecha_referencia=hoy)

                messages.success(request, 'La meta se ha actualizado correctamente.')
                return redirect(url_con_filtros(request, 'monitoreoApp:listar_metas'))
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
        else:
            messages.error(request, 'Corrige los errores del formulario.')
    else:
        form = MetaForm(instance=meta, cargos=cargos_del_equipo(request.user))

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
        validar_meta_de_su_equipo(request.user, meta)
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
        indicadores = indicadores.filter(id_funcionario=request.user.profesional)
    
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
                sincronizar_calculos_indicador(indicador, guardar=False)

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
        datos_antiguos = model_to_dict(indicador)
        form = IndicadorForm(request.POST, instance=indicador)
        if form.is_valid():
            try:
                indicador_modificado = form.save(commit=False)
                validar_periodo_abierto(indicador_modificado.meta_id_meta)
                sincronizar_calculos_indicador(indicador_modificado, guardar=False)

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


from decimal import Decimal, ROUND_HALF_UP

@login_required
@role_required('Administrador', 'Coordinador')
def tablero_indicadores_coordinador(request):
    periodos, periodo_activo = elegir_periodo(request)
    delegaciones = Delegacion.objects.order_by('nombre')

    periodo_param = request.GET.get('periodo', '').strip()
    if not periodo_param and periodo_activo:
        periodo_param = str(periodo_activo.pk)

    delegacion_param = request.GET.get('delegacion', '').strip()
    semaforo_param = request.GET.get('semaforo', '').strip()
    estado_param = request.GET.get('estado', '').strip()
    query = request.GET.get('q', '').strip()

    # 1. Asegura los indicadores según las metas del cargo de cada profesional
    asegurar_indicadores_para_tablero(
        periodo_param=periodo_param,
        delegacion_param=delegacion_param,
    )

    # 2. Consulta base ordenada por delegación y nombre del profesional
    indicadores_qs = Indicador.objects.select_related(
        'meta_id_meta__id_periodo',
        'meta_id_meta__id_cargo_item__id_cargo',
        'meta_id_meta__id_cargo_item__id_item',
        'id_funcionario__id_delegacion',
        'id_funcionario__id_cargo',
    ).order_by(
        'id_funcionario__id_delegacion__nombre',
        'id_funcionario__apellido_paterno',
        'id_funcionario__apellido_materno',
        'id_funcionario__nombres',
        '-id_indicador',
    )

    if periodo_param.isdigit():
        indicadores_qs = indicadores_qs.filter(meta_id_meta__id_periodo_id=int(periodo_param))

    if delegacion_param.isdigit():
        indicadores_qs = indicadores_qs.filter(id_funcionario__id_delegacion_id=int(delegacion_param))

    if semaforo_param in {'VERDE', 'AMARILLO', 'ROJO'}:
        indicadores_qs = indicadores_qs.filter(semaforo=semaforo_param)

    if estado_param == 'activo':
        indicadores_qs = indicadores_qs.filter(estado=True)
    elif estado_param == 'inactivo':
        indicadores_qs = indicadores_qs.filter(estado=False)

    if query:
        indicadores_qs = indicadores_qs.filter(
            Q(meta_id_meta__unidad__icontains=query)
            | Q(meta_id_meta__id_cargo_item__id_cargo__nombre__icontains=query)
            | Q(meta_id_meta__id_cargo_item__id_item__nombre__icontains=query)
            | Q(id_funcionario__nombres__icontains=query)
            | Q(id_funcionario__apellido_paterno__icontains=query)
            | Q(id_funcionario__apellido_materno__icontains=query)
            | Q(id_funcionario__id_delegacion__nombre__icontains=query)
        ).distinct()

    # 3. Sincroniza cálculos y agrupa por funcionario
    indicadores_lista = list(indicadores_qs)
    agrupados = {}

    for ind in indicadores_lista:
        try:
            sincronizar_indicador(ind, guardar=True)
        except ValidationError:
            pass

        func = ind.id_funcionario
        func_key = func.pk if func else f"sin_func_{ind.pk}"

        if func_key not in agrupados:
            agrupados[func_key] = {
                'funcionario': func,
                'indicadores': [],
                'total_metas': 0,
                'suma_cumplimiento': Decimal('0.00'),
                'promedio_cumplimiento': Decimal('0.00'),
                'total_verde': 0,
                'total_amarillo': 0,
                'total_rojo': 0,
            }

        grupo = agrupados[func_key]
        grupo['indicadores'].append(ind)
        grupo['total_metas'] += 1
        grupo['suma_cumplimiento'] += Decimal(str(ind.cumplimiento or 0))

        if ind.semaforo == 'VERDE':
            grupo['total_verde'] += 1
        elif ind.semaforo == 'AMARILLO':
            grupo['total_amarillo'] += 1
        elif ind.semaforo == 'ROJO':
            grupo['total_rojo'] += 1

    grupos_funcionarios = []
    for grupo in agrupados.values():
        if grupo['total_metas'] > 0:
            grupo['promedio_cumplimiento'] = (
                grupo['suma_cumplimiento'] / Decimal(grupo['total_metas'])
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        grupos_funcionarios.append(grupo)

    recordar_filtros(request, 'monitoreoApp:tablero_indicadores_coordinador')

    context = {
        'grupos_funcionarios': grupos_funcionarios,
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


# --- ALERTAS (HU-31) ---
FILTROS_ALERTAS = {
    'pendientes': {'revision': False},
    'revisadas': {'revision': True},
    'todas': {},
}


@login_required
@role_required('Delegado', 'Coordinador', 'Profesional')
def mis_alertas(request):
    generar_alertas()
    profesional = getattr(request.user, 'profesional', None)
    alertas = (Alerta.objects.filter(id_destinatario=profesional, estado=True)
               .select_related('id_responsable').order_by('revision', '-fecha'))
    ver = request.GET.get('ver', 'pendientes')
    if ver not in FILTROS_ALERTAS:
        ver = 'pendientes'
    listado = list(alertas.filter(**FILTROS_ALERTAS[ver]))
    for alerta in listado:
        alerta.tipo = tipo_de_alerta(alerta)
        alerta.tipo_nombre = dict(ReglaAlerta.OPCIONES_TIPO).get(alerta.tipo, 'Alerta')
    return render(request, 'monitoreo/mis_alertas.html', {
        'alertas': listado,
        'ver': ver,
        'total_pendientes': alertas.filter(revision=False).count(),
        'total_revisadas': alertas.filter(revision=True).count(),
    })


@login_required
@role_required('Delegado', 'Coordinador', 'Profesional')
@require_POST
def marcar_alerta_revisada(request, id_alerta):
    profesional = getattr(request.user, 'profesional', None)
    alerta = get_object_or_404(Alerta, pk=id_alerta, id_destinatario=profesional, estado=True)
    if not alerta.revision:
        alerta.revision = True
        alerta.save(update_fields=['revision'])
        messages.success(request, 'La alerta quedó marcada como revisada.')
    ver = request.POST.get('ver', 'pendientes')
    return redirect(f"{reverse('monitoreoApp:mis_alertas')}?ver={ver if ver in FILTROS_ALERTAS else 'pendientes'}")


@login_required
@role_required('Administrador')
def lista_reglas_alerta(request):
    hoy = date.today()
    reglas = []
    for tipo, nombre in ReglaAlerta.OPCIONES_TIPO:
        historial = ReglaAlerta.objects.filter(tipo=tipo, estado=True)
        reglas.append({
            'tipo': tipo,
            'nombre': nombre,
            'vigente': ReglaAlerta.vigente(tipo, hoy),
            'programadas': historial.filter(vigente_desde__gt=hoy).order_by('vigente_desde'),
            'anteriores': historial.filter(vigente_desde__lte=hoy).order_by('-vigente_desde', '-id_regla')[1:],
        })
    return render(request, 'monitoreo/reglas_alerta.html', {'reglas': reglas})


@login_required
@role_required('Administrador')
def editar_regla_alerta(request, tipo):
    if tipo not in dict(ReglaAlerta.OPCIONES_TIPO):
        raise Http404('Tipo de alerta desconocido.')
    actual = ReglaAlerta.vigente(tipo, date.today())

    if request.method == 'POST':
        form = ReglaAlertaForm(request.POST, tipo=tipo)
        if form.is_valid():
            nueva = form.save(commit=False)
            nueva.tipo = tipo
            nueva.save()
            registrar_auditoria(request, 'EDICION', 'ReglaAlerta', nueva, model_to_dict(actual) if actual else None)
            messages.success(request, f'La regla se aplicará desde el {nueva.vigente_desde:%d/%m/%Y}.')
            return redirect('monitoreoApp:lista_reglas_alerta')
    else:
        inicial = {'vigente_desde': date.today()}
        if actual is not None:
            inicial.update(umbral=actual.umbral, notificar_delegado=actual.notificar_delegado,
                           notificar_coordinador=actual.notificar_coordinador)
        form = ReglaAlertaForm(initial=inicial, tipo=tipo)

    return render(request, 'monitoreo/form_regla_alerta.html', {
        'form': form,
        'nombre_tipo': dict(ReglaAlerta.OPCIONES_TIPO)[tipo],
        'actual': actual,
    })


@login_required
@role_required('Delegado', 'Coordinador', 'Administrador')
def frecuencia_registros(request):
    hoy = date.today()
    periodos, periodo = elegir_periodo(request)
    delegacion = delegacion_del_delegado(request.user)
    es_delegado = delegacion is not None
    delegaciones = Delegacion.objects.none()
    if not es_delegado:
        delegaciones = Delegacion.objects.filter(estado=True).order_by('nombre')
        if (request.GET.get('delegacion') or '').isdigit():
            delegacion = delegaciones.filter(pk=request.GET['delegacion']).first()

    umbral = dias_umbral_sin_registros(hoy)
    filas = uso_de_funcionarios(funcionarios_a_monitorear(delegacion), periodo, umbral, hoy)
    con_promedio = [f['promedio'] for f in filas if f['promedio'] is not None]
    return render(request, 'monitoreo/frecuencia_registros.html', {
        'filas': filas,
        'periodos': periodos,
        'periodo': periodo,
        'es_delegado': es_delegado,
        'delegaciones': delegaciones,
        'delegacion': delegacion,
        'umbral': umbral,
        'hay_regla': ReglaAlerta.vigente(ReglaAlerta.SIN_REGISTROS, hoy) is not None,
        'medido_hasta': min(hoy - timedelta(days=1), periodo.fecha_termino) if periodo else None,
        'total_registros': sum(f['total'] for f in filas),
        'promedio_equipo': round(sum(con_promedio) / len(con_promedio), 2) if con_promedio else None,
        'sin_actividad': sum(1 for f in filas if f['supera_umbral']),
    })


AVISO_REPORTE = 'Informe de apoyo al análisis. No ejecuta decisiones automáticas sobre el personal.'


def periodos_para_tendencia(desde=None, hasta=None, incluir_en_curso=True):
    """Períodos con metas activas, en orden cronológico; los abiertos solo si ya comenzaron y se pidió incluirlos."""
    hoy = date.today()
    periodos = []
    for periodo in Periodo.objects.filter(meta__estado=True).distinct().order_by('fecha_inicio', 'id_periodo'):
        if desde and periodo.fecha_inicio < desde.fecha_inicio:
            continue
        if hasta and periodo.fecha_inicio > hasta.fecha_inicio:
            continue
        if periodo.esta_abierto:
            if not incluir_en_curso or periodo.fecha_inicio > hoy:
                continue
        periodos.append(periodo)
    return periodos


def tendencia_por_cargo(periodos, cargo=None, delegacion=None):
    """
    Cumplimiento ponderado de cada cargo en cada período, evaluado con los umbrales y la versión
    de reglas de ese mismo período, con el detalle de indicadores y actividades que lo originan.
    """
    filas = []
    for periodo in periodos:
        regular, objetivo = umbrales_en_porcentaje(periodo)
        indicadores = (Indicador.objects
                       .filter(estado=True, meta_id_meta__estado=True, meta_id_meta__id_periodo=periodo)
                       .select_related('id_funcionario__id_delegacion', 'meta_id_meta__id_periodo',
                                       'meta_id_meta__id_cargo_item__id_cargo', 'meta_id_meta__id_cargo_item__id_item')
                       .order_by('id_funcionario__nombres', 'id_indicador'))
        if cargo:
            indicadores = indicadores.filter(meta_id_meta__id_cargo_item__id_cargo=cargo)
        if delegacion:
            indicadores = indicadores.filter(id_funcionario__id_delegacion=delegacion)

        por_cargo = {}
        for indicador in indicadores:
            meta = indicador.meta_id_meta
            try:
                cargo_meta = meta.id_cargo_item.id_cargo
            except ObjectDoesNotExist:
                continue
            cumplimiento = cumplimiento_de(indicador)
            if cumplimiento is None:
                continue
            grupo = por_cargo.setdefault(cargo_meta.pk, {'cargo': cargo_meta, 'suma': 0.0, 'peso': 0.0, 'detalle': []})
            peso = float(meta.ponderador or 0)
            grupo['suma'] += cumplimiento * peso
            grupo['peso'] += peso
            grupo['detalle'].append({
                'funcionario': indicador.id_funcionario,
                'meta': etiqueta_meta(meta),
                'objetivo': meta.valor_objetivo,
                'avance': indicador.avance,
                'ajuste': indicador.ajuste or 0,
                'cumplimiento': round(cumplimiento, 1),
                'registros': list(registros_de_origen(meta, indicador.id_funcionario)),
            })

        for grupo in sorted(por_cargo.values(), key=lambda g: g['cargo'].nombre):
            cumplimiento = round(grupo['suma'] / grupo['peso'], 1) if grupo['peso'] else 0.0
            filas.append({
                'clave': f"{periodo.pk}-{grupo['cargo'].pk}",
                'periodo': periodo,
                'cerrado': not periodo.esta_abierto,
                'version': periodo.version_parametros,
                'cargo': grupo['cargo'],
                'cumplimiento': cumplimiento,
                'objetivo': round(objetivo, 1),
                'regular': round(regular, 1),
                'brecha': round(cumplimiento - objetivo, 1),
                'semaforo': semaforo_segun_umbral(cumplimiento, periodo),
                'detalle': grupo['detalle'],
            })
    return filas


def datos_grafico_tendencia(periodos, filas):
    etiquetas = [p.nombre for p in periodos]
    indice = {p.pk: i for i, p in enumerate(periodos)}
    series = {}
    for fila in filas:
        serie = series.setdefault(fila['cargo'].pk, {'label': fila['cargo'].nombre, 'data': [None] * len(periodos)})
        serie['data'][indice[fila['periodo'].pk]] = fila['cumplimiento']
    objetivo = [round(umbrales_en_porcentaje(p)[1], 1) for p in periodos]
    return {'etiquetas': etiquetas, 'series': list(series.values()), 'objetivo': objetivo}


def reporte_tendencia_excel(request, filas, filtros, periodos):
    from openpyxl import Workbook
    from openpyxl.chart import LineChart, Reference
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    guinda, oscuro, gris = '8B1D19', '212529', 'F2F2F2'
    blanco_negrita = Font(bold=True, color='FFFFFF')
    linea = Side(style='thin', color='D0D0D0')
    borde = Border(left=linea, right=linea, top=linea, bottom=linea)
    centro = Alignment(horizontal='center', vertical='center', wrap_text=True)
    colores_semaforo = {'VERDE': ('C6EFCE', '006100', 'Verde'), 'AMARILLO': ('FFEB9C', '7F6000', 'Amarillo'),
                        'ROJO': ('FFC7CE', '9C0006', 'Rojo')}
    porcentaje, puntos, fecha = '0.0"%"', '+0.0" pts";-0.0" pts";0.0" pts"', 'DD/MM/YYYY'

    def encabezado(hoja, fila, titulos, color=oscuro):
        for col, titulo in enumerate(titulos, start=1):
            celda = hoja.cell(row=fila, column=col, value=titulo)
            celda.font, celda.alignment, celda.border = blanco_negrita, centro, borde
            celda.fill = PatternFill('solid', fgColor=color)
        hoja.row_dimensions[fila].height = 30

    def titulo(hoja, texto, ancho):
        hoja.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ancho)
        celda = hoja.cell(row=1, column=1, value=texto)
        celda.font = Font(bold=True, size=15, color='FFFFFF')
        celda.fill = PatternFill('solid', fgColor=guinda)
        celda.alignment = Alignment(horizontal='left', vertical='center', indent=1)
        hoja.row_dimensions[1].height = 32
        hoja.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ancho)
        sub = hoja.cell(row=2, column=1, value=f"Ilustre Municipalidad de La Serena · Generado el "
                                              f"{timezone.localtime():%d/%m/%Y %H:%M} por {request.user.get_username()}")
        sub.font = Font(italic=True, color='595959')

    def anchos(hoja, medidas):
        for col, medida in enumerate(medidas, start=1):
            hoja.column_dimensions[get_column_letter(col)].width = medida

    libro = Workbook()
    resumen = libro.active
    resumen.title = 'Resumen'
    columnas = ['Período', 'Inicio', 'Término', 'Estado', 'Reglas', 'Cargo', 'Cumplimiento', 'Objetivo',
                'Umbral regular', 'Brecha', 'Semáforo', 'Indicadores']
    titulo(resumen, 'Reporte de tendencias por cargo', len(columnas))

    fila = 4
    for nombre, valor in filtros:
        resumen.cell(row=fila, column=1, value=nombre).font = Font(bold=True, color=guinda)
        resumen.merge_cells(start_row=fila, start_column=2, end_row=fila, end_column=len(columnas))
        resumen.cell(row=fila, column=2, value=valor)
        fila += 1
    resumen.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=len(columnas))
    aviso = resumen.cell(row=fila, column=1, value=AVISO_REPORTE)
    aviso.font = Font(italic=True, color='595959')
    aviso.fill = PatternFill('solid', fgColor=gris)

    inicio_tabla = fila + 2
    encabezado(resumen, inicio_tabla, columnas)
    for i, f in enumerate(filas, start=inicio_tabla + 1):
        valores = [f['periodo'].nombre, f['periodo'].fecha_inicio, f['periodo'].fecha_termino,
                   'Cerrado' if f['cerrado'] else 'En curso', f"v{f['version']}", f['cargo'].nombre,
                   f['cumplimiento'], f['objetivo'], f['regular'], f['brecha'], None, len(f['detalle'])]
        for col, valor in enumerate(valores, start=1):
            celda = resumen.cell(row=i, column=col, value=valor)
            celda.border = borde
            celda.alignment = Alignment(horizontal='left' if col in (1, 6) else 'center', vertical='center')
            if (i - inicio_tabla) % 2 == 0:
                celda.fill = PatternFill('solid', fgColor=gris)
        resumen.cell(row=i, column=2).number_format = fecha
        resumen.cell(row=i, column=3).number_format = fecha
        for col in (7, 8, 9):
            resumen.cell(row=i, column=col).number_format = porcentaje
        resumen.cell(row=i, column=7).font = Font(bold=True)
        brecha = resumen.cell(row=i, column=10)
        brecha.number_format = puntos
        brecha.font = Font(bold=True, color='9C0006' if f['brecha'] < 0 else '006100')
        fondo, letra, texto = colores_semaforo.get(f['semaforo'], ('FFFFFF', '000000', f['semaforo']))
        semaforo = resumen.cell(row=i, column=11, value=texto)
        semaforo.fill = PatternFill('solid', fgColor=fondo)
        semaforo.font = Font(bold=True, color=letra)
        if not f['cerrado']:
            resumen.cell(row=i, column=4).font = Font(italic=True, color='7F6000')
    ultima = inicio_tabla + max(len(filas), 1)
    resumen.auto_filter.ref = f"A{inicio_tabla}:{get_column_letter(len(columnas))}{ultima}"
    resumen.freeze_panes = resumen.cell(row=inicio_tabla + 1, column=1)
    anchos(resumen, [22, 13, 13, 13, 10, 24, 17, 13, 17, 14, 14, 15])

    detalle = libro.create_sheet('Detalle')
    columnas_det = ['Período', 'Cargo', 'Funcionario', 'Meta', 'Objetivo', 'Avance', 'Ajuste', 'Cumplimiento',
                    'Actividades que originan el avance']
    titulo(detalle, 'Detalle que origina cada resultado', len(columnas_det))
    encabezado(detalle, 4, columnas_det, color=guinda)
    i = 5
    for f in filas:
        for d in f['detalle']:
            valores = [f['periodo'].nombre, f['cargo'].nombre, f"{d['funcionario'].nombres} {d['funcionario'].apellido_paterno}",
                       d['meta'], float(d['objetivo']), float(d['avance']), float(d['ajuste']), d['cumplimiento'],
                       ', '.join(a.codigo_unico for a in d['registros']) or 'Sin actividades aprobadas']
            for col, valor in enumerate(valores, start=1):
                celda = detalle.cell(row=i, column=col, value=valor)
                celda.border = borde
                celda.alignment = Alignment(horizontal='center' if 5 <= col <= 8 else 'left', vertical='center',
                                            wrap_text=col in (4, 9))
                if i % 2 == 0:
                    celda.fill = PatternFill('solid', fgColor=gris)
            detalle.cell(row=i, column=8).number_format = porcentaje
            i += 1
    detalle.auto_filter.ref = f"A4:{get_column_letter(len(columnas_det))}{max(i - 1, 5)}"
    detalle.freeze_panes = 'A5'
    anchos(detalle, [20, 24, 24, 38, 13, 13, 13, 17, 60])

    grafico = libro.create_sheet('Gráfico')
    cargos = list(dict.fromkeys(f['cargo'].nombre for f in filas))
    titulo(grafico, 'Cumplimiento por cargo frente al objetivo', max(len(cargos) + 2, 4))
    encabezado(grafico, 4, ['Período'] + cargos + ['Objetivo'])
    valor_de = {(f['periodo'].pk, f['cargo'].nombre): f['cumplimiento'] for f in filas}
    for i, periodo in enumerate(periodos, start=5):
        grafico.cell(row=i, column=1, value=f"{periodo.nombre} (v{periodo.version_parametros})").border = borde
        for col, cargo_nombre in enumerate(cargos, start=2):
            celda = grafico.cell(row=i, column=col, value=valor_de.get((periodo.pk, cargo_nombre)))
            celda.number_format, celda.border, celda.alignment = porcentaje, borde, centro
        objetivo = grafico.cell(row=i, column=len(cargos) + 2, value=round(umbrales_en_porcentaje(periodo)[1], 1))
        objetivo.number_format, objetivo.border, objetivo.alignment = porcentaje, borde, centro
    anchos(grafico, [24] + [18] * (len(cargos) + 1))
    if periodos:
        linea_grafico = LineChart()
        linea_grafico.title = 'Cumplimiento por cargo y período'
        linea_grafico.y_axis.title = 'Cumplimiento (%)'
        linea_grafico.x_axis.title = 'Período'
        linea_grafico.y_axis.scaling.min, linea_grafico.y_axis.scaling.max = 0, 120
        linea_grafico.height, linea_grafico.width = 9, 20
        ultima_fila = 4 + len(periodos)
        datos = Reference(grafico, min_col=2, max_col=len(cargos) + 2, min_row=4, max_row=ultima_fila)
        linea_grafico.add_data(datos, titles_from_data=True)
        linea_grafico.set_categories(Reference(grafico, min_col=1, min_row=5, max_row=ultima_fila))
        paleta = [guinda, '1F6F8B', 'D97706', '198754', '6F42C1']
        for n, serie in enumerate(linea_grafico.series):
            if n == len(linea_grafico.series) - 1:
                serie.graphicalProperties.line.solidFill = '6C757D'
                serie.graphicalProperties.line.dashStyle = 'dash'
            else:
                serie.graphicalProperties.line.solidFill = paleta[n % len(paleta)]
                serie.graphicalProperties.line.width = 28000
            serie.smooth = False
        grafico.add_chart(linea_grafico, f"A{ultima_fila + 3}")

    for hoja in libro.worksheets:
        hoja.page_setup.orientation = 'landscape'
        hoja.page_setup.fitToWidth = 1
        hoja.sheet_properties.pageSetUpPr.fitToPage = True

    respuesta = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    respuesta['Content-Disposition'] = f'attachment; filename="tendencias_por_cargo_{date.today():%Y%m%d}.xlsx"'
    libro.save(respuesta)
    return respuesta


@login_required
@role_required('Coordinador', 'Administrador')
def tendencias_cargo(request):
    cargos = Cargo.objects.order_by('nombre')
    delegaciones = Delegacion.objects.filter(estado=True).order_by('nombre')
    todos_los_periodos = periodos_para_tendencia(incluir_en_curso=True)

    def elegido(modelo, clave):
        valor = request.GET.get(clave, '')
        return modelo.objects.filter(pk=valor).first() if valor.isdigit() else None

    cargo = elegido(Cargo, 'cargo')
    delegacion = elegido(Delegacion, 'delegacion')
    desde = elegido(Periodo, 'desde')
    hasta = elegido(Periodo, 'hasta')
    incluir_en_curso = request.GET.get('en_curso') == '1' or not request.GET

    filas = tendencia_por_cargo(periodos_para_tendencia(desde, hasta, incluir_en_curso), cargo, delegacion)
    periodos = list(dict.fromkeys(f['periodo'] for f in filas))
    filtros = [
        ('Cargo', cargo.nombre if cargo else 'Todos'),
        ('Delegación', delegacion.nombre if delegacion else 'Todas'),
        ('Desde', desde.nombre if desde else 'Primer período'),
        ('Hasta', hasta.nombre if hasta else 'Último período'),
        ('Períodos en curso', 'Incluidos' if incluir_en_curso else 'Solo cerrados'),
        ('Períodos comparados', ', '.join(f'{p.nombre} (v{p.version_parametros})' for p in periodos) or 'Ninguno'),
    ]

    if request.GET.get('formato') == 'excel':
        return reporte_tendencia_excel(request, filas, filtros, periodos)

    parametros = request.GET.copy()
    parametros.pop('formato', None)
    if not request.GET:
        parametros['en_curso'] = '1'
    parametros['formato'] = 'excel'
    return render(request, 'coordinador/tendencias_cargo.html', {
        'cargos': cargos,
        'delegaciones': delegaciones,
        'todos_los_periodos': todos_los_periodos,
        'cargo': cargo,
        'delegacion': delegacion,
        'desde': desde,
        'hasta': hasta,
        'incluir_en_curso': incluir_en_curso,
        'periodos': periodos,
        'filas': filas,
        'filtros': filtros,
        'grafico': datos_grafico_tendencia(periodos, filas),
        'url_reporte': f"{request.path}?{parametros.urlencode()}",
        'aviso': AVISO_REPORTE,
    })
