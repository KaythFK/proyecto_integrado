import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from usuariosApp.decorators import role_required 
from .models import CartaTubo, Compromiso, HistorialIncumplimiento, ObservacionCompromiso
from actividadApp.models import Actividad
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.urls import reverse
from datetime import date
from actividadApp.models import Actividad
from .forms import CartaTuboForm, ObservacionRegistroForm
from monitoreoApp.views import datos_graficos_panel, elegir_periodo, resumen_indicadores
from monitoreoApp.services import registrar_incumplimiento, resumen_compromisos
from actividadApp.filters import ActividadFilter
from config.utils import recordar_filtros, url_con_filtros, url_listado_actividades, validar_acceso_observaciones

# --- NUEVOS IMPORTS PARA AUDITORÍA ---
from administracionApp.models import Delegacion, Profesional, Auditoria
import json
from django.forms.models import model_to_dict
from config.utils import puede_modificar_compromiso, rechazar_si_aprobada, con_marca_aprobada, paginar
from .filters import CompromisoFilter, buscar_compromisos
from django.core.exceptions import PermissionDenied


def solo_profesional(user):
    return not user.groups.filter(name__in=['Administrador', 'Coordinador', 'Delegado']).exists()


def url_tubo_segun_rol(user):
    if user.groups.filter(name='Administrador').exists():
        return 'tuboApp:tubo'
    if user.groups.filter(name='Delegado').exists():
        return 'monitoreoApp:tubo_delegacion'
    if user.groups.filter(name='Coordinador').exists():
        return 'tuboApp:dashboard_coordinador'
    if user.groups.filter(name='Profesional').exists():
        return 'monitoreoApp:tubo_delegacion'
    return 'tuboApp:tubo'

# --- FUNCIÓN AUXILIAR DE AUDITORÍA ---
def registrar_auditoria(request, evento, entidad, objeto_instancia, datos_anteriores=None, extra=None):
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
        if extra:
            datos_nuevos_limpios.update({k: str(v) for k, v in extra.items()})
        
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
@role_required('Administrador', 'Coordinador', 'Delegado')
def reasignar_compromiso(request, id_compromiso):
    """Traspasa el compromiso a otro funcionario y lo deja en auditoría con el motivo."""
    destino = url_tubo_segun_rol(request.user)
    if request.method != 'POST':
        return redirect(destino)

    compromiso = get_object_or_404(Compromiso, id_compromiso=id_compromiso)

    if not puede_modificar_compromiso(request.user, compromiso):
        raise PermissionDenied('No tienes permiso para reasignar este compromiso: pertenece a otro funcionario o delegación.')
    bloqueo = rechazar_si_aprobada(request, compromiso.id_actividad, destino)
    if bloqueo:
        return bloqueo

    if not compromiso.estado or compromiso.estado_progreso == 'REALIZADO':
        messages.error(request, 'Solo se pueden reasignar compromisos activos que no estén realizados.')
        return redirect(destino)

    nuevo_responsable = Profesional.objects.filter(pk=request.POST.get('nuevo_responsable') or None, estado=True).first()
    motivo = (request.POST.get('motivo') or '').strip()
    responsable_anterior = compromiso.id_funcionario

    if not nuevo_responsable:
        messages.error(request, 'Debes seleccionar un nuevo responsable activo.')
        return redirect(destino)
    if nuevo_responsable.pk == responsable_anterior.pk:
        messages.error(request, 'El nuevo responsable debe ser distinto del actual.')
        return redirect(destino)
    es_admin_o_coord = request.user.groups.filter(name__in=['Administrador', 'Coordinador']).exists()
    if not es_admin_o_coord and nuevo_responsable.id_delegacion_id != responsable_anterior.id_delegacion_id:
        messages.error(request, 'Solo puedes reasignar a funcionarios de la misma delegación.')
        return redirect(destino)
    if len(motivo) < 10:
        messages.error(request, 'Debes indicar el motivo de la reasignación (mínimo 10 caracteres).')
        return redirect(destino)

    with transaction.atomic():
        datos_antiguos = model_to_dict(compromiso)
        compromiso.id_funcionario = nuevo_responsable
        compromiso.save()

        registrar_auditoria(request, "REASIGNACION", "Compromiso", compromiso, datos_antiguos, extra={
            'responsable_anterior': f'{responsable_anterior.nombres} {responsable_anterior.apellido_paterno}',
            'responsable_nuevo': f'{nuevo_responsable.nombres} {nuevo_responsable.apellido_paterno}',
            'motivo': motivo,
        })

    messages.success(request, f'El compromiso {compromiso.id_actividad.codigo_unico} fue reasignado a '
                              f'{nuevo_responsable.nombres} {nuevo_responsable.apellido_paterno}.')
    return redirect(destino)


@login_required
@role_required('Administrador')
def agenda(request):
    query = request.GET.get('q')
    compromisos = Compromiso.objects.select_related('id_actividad', 'id_funcionario', 'apoyo').all().order_by('fecha_comprometida', 'id_compromiso')
    observaciones = ObservacionCompromiso.objects.all().order_by('-fecha')
    
    if query:
        compromisos = buscar_compromisos(compromisos, query)

    filtro = CompromisoFilter(request.GET, queryset=compromisos)

    context = {
        'compromisos': filtro.qs if filtro.is_valid() else compromisos.none(),
        'filtro': filtro,
        'observaciones': observaciones,
        'query': query,
    }
    return render(request, 'administrador/tubo/lista_tubo.html', context)


@login_required
@role_required('Administrador', 'Coordinador', 'Delegado', 'Profesional')
def actualizar_progreso_tubo(request, id_compromiso):
    if request.method == 'POST':
        compromiso = get_object_or_404(Compromiso, id_compromiso=id_compromiso)

        if not puede_modificar_compromiso(request.user, compromiso):
            raise PermissionDenied('No tienes permiso para modificar este compromiso: pertenece a otro funcionario o delegación.')
        bloqueo = rechazar_si_aprobada(request, compromiso.id_actividad, url_tubo_segun_rol(request.user))
        if bloqueo:
            return bloqueo
        if solo_profesional(request.user) and compromiso.estado_progreso == 'REALIZADO':
            messages.error(request, 'El compromiso ya está realizado; solo el Delegado puede modificarlo.')
            return redirect(url_tubo_segun_rol(request.user))

        nuevo_estado = request.POST.get('nuevo_estado')
        registrar_incumplimiento(compromiso)

        estados_validos = dict(Compromiso.OPCIONES_ESTADO_PROGRESO).keys()
        if nuevo_estado in estados_validos:
            try:
                with transaction.atomic():
                    # 1. Capturamos estado ANTERIOR de ambos objetos
                    datos_antiguos_compromiso = model_to_dict(compromiso)
                    actividad = compromiso.id_actividad
                    datos_antiguos_actividad = model_to_dict(actividad)

                    # 2. Mapeo de estados entre Compromiso y Actividad
                    estado_actividad = nuevo_estado
                    if nuevo_estado == 'INGRESADO':
                        estado_actividad = 'PENDIENTE'
                    elif nuevo_estado == 'REALIZADO':
                        estado_actividad = 'FINALIZADA'
                        compromiso.fecha_termino = date.today()
                    else:
                        compromiso.fecha_termino = None
                        
                    # 3. Actualizar Compromiso
                    compromiso.estado_progreso = nuevo_estado
                    compromiso.save()

                    # 4. Actualizar Actividad asociada
                    actividad.estado_progreso = estado_actividad
                    actividad.save()

                    # 5. REGISTRAR AUDITORÍA DOBLE
                    registrar_auditoria(request, "CAMBIO_PROGRESO", "Compromiso", compromiso, datos_antiguos_compromiso)
                    registrar_auditoria(request, "CAMBIO_PROGRESO", "Actividad", actividad, datos_antiguos_actividad)

                    messages.success(request, f'Progreso actualizado a {nuevo_estado} para el compromiso y su actividad.')
            except Exception as e:
                messages.error(request, f'Error al actualizar el progreso: {str(e)}')
        else:
            messages.error(request, 'Estado seleccionado no válido.')
            
    return redirect(url_tubo_segun_rol(request.user))


@login_required
@role_required('Administrador')
def cambiar_estado_tubo(request, id_compromiso):
    if request.method == 'POST':
        compromiso = get_object_or_404(Compromiso, id_compromiso=id_compromiso)
        bloqueo = rechazar_si_aprobada(request, compromiso.id_actividad, 'tuboApp:tubo')
        if bloqueo:
            return bloqueo
        if compromiso.estado and (compromiso.esta_vencido or HistorialIncumplimiento.objects.filter(compromiso=compromiso, estado=True).exists()):
            messages.error(request, f'El compromiso de la actividad {compromiso.id_actividad.codigo_unico} tiene un incumplimiento registrado y no se puede inhabilitar.')
            return redirect('tuboApp:tubo')

        try:
            with transaction.atomic():
                datos_antiguos = model_to_dict(compromiso) # --- AUDITORÍA ---
                nuevo_estado = not compromiso.estado
                
                # Borrado lógico del compromiso
                compromiso.estado = nuevo_estado
                compromiso.save()

                # --- AUDITORÍA ---
                registrar_auditoria(request, "CAMBIO_ESTADO", "Compromiso", compromiso, datos_antiguos)

                accion = "habilitado" if nuevo_estado else "inhabilitado"
                messages.success(request, f'El compromiso asociado a la actividad {compromiso.id_actividad.codigo_unico} fue {accion}.')
        except Exception as e:
            messages.error(request, f'Error al cambiar el estado: {str(e)}')
            
    return redirect('tuboApp:tubo')



@login_required
@role_required('Coordinador')
def dashboard_coordinador(request):
    total_actividades = Actividad.objects.count()
    finalizadas = Actividad.objects.filter(estado_progreso='FINALIZADA').count()
    en_proceso = Actividad.objects.filter(estado_progreso='EN_PROCESO').count()
    pendientes = Actividad.objects.filter(estado_progreso='PENDIENTE').count()

    periodos, periodo = elegir_periodo(request)
    filas = resumen_indicadores(None, periodo)[0]
    filas.sort(key=lambda f: f['diferencia'])
    actividades_periodo = Actividad.objects.filter(estado=True, id_meta__id_periodo=periodo) if periodo else Actividad.objects.none()
    compromisos_periodo = Compromiso.objects.filter(estado=True)
    if periodo:
        compromisos_periodo = compromisos_periodo.filter(fecha_comprometida__range=(periodo.fecha_inicio, periodo.fecha_termino))

    context = {
        'total': total_actividades,
        'finalizadas': finalizadas,
        'en_proceso': en_proceso,
        'pendientes': pendientes,
        'periodos': periodos,
        'periodo': periodo,
        'filas': filas,
        'esperado': periodo.porcentaje_esperado() if periodo else None,
        'desviaciones_criticas': [f for f in filas if f['desviacion'] == 'ROJO'],
        'graficos': datos_graficos_panel(sorted(filas, key=lambda f: f['nombre']), resumen_compromisos(compromisos_periodo),
                                         actividades_periodo, agrupar_por_delegacion=True),
    }
    return render(request, 'coordinador/dashboard_coordinador.html', context)


@login_required
@role_required('Coordinador')
def listar_todas_actividades(request):
    todas = con_marca_aprobada(Actividad.objects.all()).prefetch_related('evidencia_set').order_by('-fecha_registro')
    filtro = ActividadFilter(request.GET, queryset=todas)
    recordar_filtros(request, 'tuboApp:listar_todas')

    context = {
        'actividades': filtro.qs if filtro.is_valid() else todas.none(),
        'filtro': filtro,
        'query': request.GET.get('q'),
    }

    return render(request, 'coordinador/listar_todas.html', context)



@login_required
def detalle_actividad(request, pk):
    actividad = get_object_or_404(Actividad, pk=pk)
    validar_acceso_observaciones(request.user, actividad)

    compromiso = Compromiso.objects.filter(id_actividad=actividad).first()
    observaciones = ObservacionCompromiso.objects.filter(id_actividad=actividad).select_related('autor')
    origen = request.GET.get('volver')
    destinos = {
        'alertas': (reverse('monitoreoApp:mis_alertas'), 'Volver a mis alertas'),
        'tubo': (reverse(url_tubo_segun_rol(request.user)), 'Volver al Tubo'),
    }
    if request.user.groups.filter(name='Delegado').exists():
        destinos['panel'] = (reverse('monitoreoApp:dashboard_delegado'), 'Volver al panel')
    if origen not in destinos:
        origen = None
    url_volver, texto_volver = destinos.get(origen, (url_listado_actividades(request), 'Volver al listado'))

    if request.method == 'POST':
        form = ObservacionRegistroForm(request.POST)
        if form.is_valid():
            profesional_actual = Profesional.objects.filter(usuario=request.user).first()
            if not profesional_actual:
                raise PermissionDenied('Tu usuario no tiene un perfil de funcionario asociado para registrar observaciones.')

            nueva_obs = form.save(commit=False)
            nueva_obs.id_actividad = actividad

            if compromiso:
                nueva_obs.id_compromiso = compromiso

            nueva_obs.autor = profesional_actual
            nueva_obs.save()
            registrar_auditoria(request, "CREACION", "ObservacionCompromiso", nueva_obs)
            messages.success(request, "Observación registrada correctamente.")
            if origen:
                return redirect(f"{reverse('tuboApp:detalle_actividad', args=[pk])}?volver={origen}")
            return redirect('tuboApp:detalle_actividad', pk=pk)
    else:
        form = ObservacionRegistroForm()

    return render(request, 'coordinador/detalle_registros.html', {
        'actividad': actividad,
        'observaciones': observaciones,
        'form': form,
        'url_volver': url_volver,
        'texto_volver': texto_volver,
    })


def es_rol_global(user):
    return user.groups.filter(name__in=['Administrador', 'Coordinador']).exists()


def cartas_visibles(user):
    cartas = CartaTubo.objects.select_related('delegacion', 'encargado', 'registrado_por')
    if es_rol_global(user):
        return cartas
    profesional = getattr(user, 'profesional', None)
    if profesional is None:
        return cartas.none()
    return cartas.filter(delegacion_id=profesional.id_delegacion_id)


def puede_editar_carta(user, carta):
    if user.groups.filter(name='Administrador').exists():
        return True
    profesional = getattr(user, 'profesional', None)
    if profesional is None or carta.delegacion_id != profesional.id_delegacion_id:
        return False
    if user.groups.filter(name='Delegado').exists():
        return True
    return (user.groups.filter(name='Profesional').exists()
            and profesional.pk in (carta.encargado_id, carta.registrado_por_id)
            and carta.estado_carta not in CartaTubo.ESTADOS_CERRADOS)


def puede_aprobar_carta(user):
    return user.groups.filter(name__in=['Administrador', 'Delegado']).exists()


def delegacion_propia(user):
    if user.groups.filter(name='Administrador').exists():
        return None
    return user.profesional.id_delegacion


@login_required
@role_required('Administrador', 'Coordinador', 'Delegado', 'Profesional')
def lista_cartas(request):
    cartas = cartas_visibles(request.user)
    query = (request.GET.get('q') or '').strip()
    estado_carta = request.GET.get('estado_carta') or ''
    encargado = request.GET.get('encargado') or ''
    delegacion = request.GET.get('delegacion') or ''
    desde, hasta = request.GET.get('desde') or '', request.GET.get('hasta') or ''

    if query:
        cartas = cartas.filter(
            Q(codigo__icontains=query) | Q(remitente__icontains=query) | Q(tema__icontains=query) |
            Q(numero_oficina_partes__icontains=query) | Q(telefono_contacto__icontains=query)
        )
    if encargado.isdigit():
        cartas = cartas.filter(encargado_id=encargado)
    if delegacion.isdigit() and es_rol_global(request.user):
        cartas = cartas.filter(delegacion_id=delegacion)
    if desde:
        cartas = cartas.filter(fecha_recepcion__gte=desde)
    if hasta:
        cartas = cartas.filter(fecha_recepcion__lte=hasta)

    conteo = {clave: 0 for clave, _ in CartaTubo.OPCIONES_ESTADO}
    for clave in cartas.filter(estado=True).values_list('estado_carta', flat=True):
        conteo[clave] += 1
    if estado_carta in conteo:
        cartas = cartas.filter(estado_carta=estado_carta)

    cartas = list(cartas.order_by('-fecha_recepcion', '-id_carta'))
    for carta in cartas:
        carta.editable = puede_editar_carta(request.user, carta)

    pagina, parametros = paginar(request, cartas)
    visibles = cartas_visibles(request.user)
    encargados = Profesional.objects.filter(pk__in=visibles.values('encargado_id')).order_by('nombres')
    return render(request, 'administrador/tubo/lista_cartas.html', {
        'cartas': pagina,
        'pagina': pagina,
        'parametros': parametros,
        'resumen': [(clave, nombre, conteo[clave]) for clave, nombre in CartaTubo.OPCIONES_ESTADO],
        'total_activas': sum(conteo.values()),
        'estados': CartaTubo.OPCIONES_ESTADO,
        'encargados': encargados,
        'delegaciones': Delegacion.objects.filter(estado=True).order_by('nombre') if es_rol_global(request.user) else None,
        'filtros': {'q': query, 'estado_carta': estado_carta, 'encargado': encargado, 'delegacion': delegacion, 'desde': desde, 'hasta': hasta},
        'puede_crear': not request.user.groups.filter(name='Coordinador').exists() or request.user.groups.filter(name='Administrador').exists(),
        'puede_desactivar': puede_aprobar_carta(request.user),
    })


@login_required
@role_required('Administrador', 'Delegado', 'Profesional')
def crear_carta(request):
    delegacion = delegacion_propia(request.user)
    form = CartaTuboForm(request.POST or None, delegacion=delegacion, puede_aprobar=puede_aprobar_carta(request.user))
    if request.method == 'POST':
        if form.is_valid():
            carta = form.save(commit=False)
            if delegacion is not None:
                carta.delegacion = delegacion
            carta.registrado_por = getattr(request.user, 'profesional', None)
            carta.codigo = f"CAR-{date.today().year}-{uuid.uuid4().hex[:6].upper()}"
            carta.save()
            registrar_auditoria(request, "CREACION", "CartaTubo", carta)
            messages.success(request, f'Carta registrada con el código {carta.codigo}.')
            return redirect('tuboApp:lista_cartas')
        messages.error(request, 'Revisa los datos marcados en el formulario.')
    return render(request, 'administrador/tubo/form_carta.html', {'form': form, 'titulo': 'Registrar carta'})


@login_required
@role_required('Administrador', 'Delegado', 'Profesional')
def editar_carta(request, id_carta):
    carta = get_object_or_404(cartas_visibles(request.user), pk=id_carta)
    if not puede_editar_carta(request.user, carta):
        messages.error(request, 'Solo puedes modificar las cartas a tu cargo que aún no estén aprobadas ni finalizadas.')
        return redirect('tuboApp:lista_cartas')
    datos_antiguos = model_to_dict(carta)
    form = CartaTuboForm(request.POST or None, instance=carta, delegacion=delegacion_propia(request.user),
                         puede_aprobar=puede_aprobar_carta(request.user))
    if request.method == 'POST':
        if form.is_valid():
            carta = form.save()
            registrar_auditoria(request, "EDICION", "CartaTubo", carta, datos_antiguos)
            messages.success(request, f'La carta {carta.codigo} fue actualizada.')
            return redirect('tuboApp:lista_cartas')
        messages.error(request, 'Revisa los datos marcados en el formulario.')
    return render(request, 'administrador/tubo/form_carta.html', {'form': form, 'titulo': f'Editar carta {carta.codigo}', 'carta': carta})


@login_required
@role_required('Administrador', 'Delegado')
def cambiar_estado_carta(request, id_carta):
    if request.method == 'POST':
        carta = get_object_or_404(cartas_visibles(request.user), pk=id_carta)
        datos_antiguos = model_to_dict(carta)
        carta.estado = not carta.estado
        carta.save(update_fields=['estado'])
        registrar_auditoria(request, "CAMBIO_ESTADO", "CartaTubo", carta, datos_antiguos)
        messages.success(request, f'La carta {carta.codigo} fue {"reactivada" if carta.estado else "desactivada"}.')
    return redirect('tuboApp:lista_cartas')
