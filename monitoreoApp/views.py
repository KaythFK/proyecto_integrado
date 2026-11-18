from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required
from usuariosApp.decorators import role_required
from actividadApp.models import Actividad, Ausencia
from .models import Meta, Indicador
from .forms import MetaForm, IndicadorForm, MetaAsignacionForm
from tuboApp.models import Compromiso
from tuboApp.filters import CompromisoFilter
from datetime import date
from django.core.exceptions import ValidationError
from config.utils import validar_periodo_abierto, recordar_filtros, url_con_filtros, delegacion_del_delegado
from django.core.exceptions import PermissionDenied
from .filters import MetaFilter
from config.utils import procesar_resumen_dashboard
from administracionApp.models import Cargo, CargoItem


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
    metas = Meta.objects.filter(id_periodo=periodo, estado=True).select_related('id_cargo', 'id_item')
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
    metas = Meta.objects.select_related('id_cargo_item__id_cargo', 'id_cargo_item__id_item', 'id_periodo').order_by('-id_meta')
    cargos = cargos_del_equipo(request.user)
    if cargos is not None:
        metas = metas.filter(id_cargo_item__id_cargo__in=cargos)
    filtro = MetaFilter(request.GET, queryset=metas, cargos=cargos)
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
def editar_meta(request, id_meta):
    meta = get_object_or_404(Meta, id_meta=id_meta)
    validar_meta_de_su_equipo(request.user, meta)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(meta) # --- AUDITORÍA ---
        form = MetaForm(request.POST, instance=meta, cargos=cargos_del_equipo(request.user))
        if form.is_valid():
            try:
                with transaction.atomic():
                    meta_guardada = form.save()
                    
                    # --- AUDITORÍA ---
                    registrar_auditoria(request, "EDICION", "Meta", meta_guardada, datos_antiguos)
                    
                messages.success(request, 'La meta se ha actualizado correctamente.')
                return redirect(url_con_filtros(request, 'monitoreoApp:listar_metas'))
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
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


def asignar_metas_cargo(request, cargo_pk):
    cargo = get_object_or_404(Cargo, pk=cargo_pk)
    periodo_actual = Periodo.objects.filter(estado=True).order_by('-fecha_inicio').first()
    
    if not periodo_actual:
        messages.error(request, "No hay un período de medición abierto.")
        return redirect('administracionApp:lista_cargos')

    if request.method == 'POST':
        form = MetaAsignacionForm(request.POST)
        if form.is_valid():
            nueva_meta = form.save(commit=False)
            nueva_meta.version = 1 # KAN-208: Versión inicial
            nueva_meta.save()
            
            messages.success(request, "Meta asignada correctamente.")
            return redirect('administracionApp:asignar_metas_cargo', cargo_pk=cargo.pk)
        else:
            messages.error(request, "Error al guardar la meta. Revisa los datos ingresados.")
    else:
        form = MetaAsignacionForm(initial={
            'id_periodo': periodo_actual,
            'fecha_inicio': periodo_actual.fecha_inicio
        })

    # Restringimos el select solo a los ítems que pertenecen a la matriz de este cargo
    form.fields['id_cargo_item'].queryset = CargoItem.objects.filter(id_cargo=cargo.pk)

    context = {
        'titulo': f'Asignar Metas: {cargo.nombre}',
        'cargo': cargo,
        'form': form,
        'periodo': periodo_actual,
    }
    return render(request, 'administracionApp/asignar_metas.html', context)