from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from usuariosApp.decorators import role_required 
from .models import Compromiso, ObservacionCompromiso
from actividadApp.models import Actividad
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from datetime import date
from actividadApp.models import Actividad
from .forms import ObservacionRegistroForm
from monitoreoApp.views import elegir_periodo, resumen_indicadores
from actividadApp.filters import ActividadFilter
from config.utils import recordar_filtros, url_con_filtros, url_listado_actividades

# --- NUEVOS IMPORTS PARA AUDITORÍA ---
from administracionApp.models import Profesional, Auditoria
import json
from django.forms.models import model_to_dict
from config.utils import puede_modificar_compromiso
from .filters import CompromisoFilter
from django.core.exceptions import PermissionDenied


def url_tubo_segun_rol(user):
    if user.groups.filter(name='Administrador').exists():
        return 'tuboApp:tubo'
    if user.groups.filter(name='Delegado').exists():
        return 'monitoreoApp:tubo_delegacion'
    if user.groups.filter(name='Coordinador').exists():
        return 'tuboApp:dashboard_coordinador'
    return 'tuboApp:tubo'

# --- FUNCIÓN AUXILIAR DE AUDITORÍA ---
def registrar_auditoria(request, evento, entidad, objeto_instancia, datos_anteriores=None, extra=None):
    """
    Función centralizada para registrar auditoría con descripciones legibles.
    """
    try:
        profesional_actual = Profesional.objects.filter(usuario=request.user).first() if request.user.is_authenticated else None
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
        compromisos = compromisos.filter(
            Q(id_actividad__codigo_unico__icontains=query) |
            Q(id_actividad__solicitud_problema__icontains=query) |
            Q(territorio__icontains=query)
        ).distinct()

    filtro = CompromisoFilter(request.GET, queryset=compromisos)

    context = {
        'compromisos': filtro.qs if filtro.is_valid() else compromisos.none(),
        'filtro': filtro,
        'observaciones': observaciones,
        'query': query,
    }
    return render(request, 'administrador/tubo/lista_tubo.html', context)


@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def actualizar_progreso_tubo(request, id_compromiso):
    if request.method == 'POST':
        compromiso = get_object_or_404(Compromiso, id_compromiso=id_compromiso)

        if not puede_modificar_compromiso(request.user, compromiso):
            raise PermissionDenied('No tienes permiso para modificar este compromiso: pertenece a otro funcionario o delegación.')

        nuevo_estado = request.POST.get('nuevo_estado')
        
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
@role_required('Administracion', 'Coordinacion', 'Delegado')
def agregar_observacion_tubo(request, id_compromiso):
    if request.method == 'POST':
        compromiso = get_object_or_404(Compromiso, id_compromiso=id_compromiso)

        if not puede_modificar_compromiso(request.user, compromiso):
            raise PermissionDenied('No tienes permiso para agregar observaciones a este compromiso: pertenece a otro funcionario o delegación.')

        texto_obs = request.POST.get('texto_observacion')
        
        if texto_obs and texto_obs.strip():
            try:
                with transaction.atomic():
                    nueva_observacion = ObservacionCompromiso.objects.create(
                        id_compromiso=compromiso,
                        id_actividad=compromiso.id_actividad,
                        autor=getattr(request.user, 'profesional', None),
                        texto=texto_obs.strip(),
                        fecha=timezone.now()
                    )
                    # --- AUDITORÍA ---
                    registrar_auditoria(request, "CREACION", "ObservacionCompromiso", nueva_observacion)
                    
                messages.success(request, 'Observación agregada exitosamente al historial.')
            except Exception as e:
                messages.error(request, f'Error al guardar la observación: {str(e)}')
        else:
            messages.error(request, 'El texto de la observación no puede estar vacío.')
            
    return redirect(url_tubo_segun_rol(request.user))


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
    }
    return render(request, 'coordinador/dashboard_coordinador.html', context)


@login_required
@role_required('Coordinador')
def listar_todas_actividades(request):
    todas = Actividad.objects.all().prefetch_related('evidencia_set').order_by('-fecha_registro')
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
    compromiso = Compromiso.objects.filter(id_actividad=actividad).first()
    observaciones = ObservacionCompromiso.objects.filter(id_actividad=actividad)

    if request.method == 'POST':
        form = ObservacionRegistroForm(request.POST)
        if form.is_valid():
            nueva_obs = form.save(commit=False)
            nueva_obs.id_actividad = actividad
            
            if compromiso:
                nueva_obs.id_compromiso = compromiso
                
            if hasattr(request.user, 'profesional'):
                nueva_obs.autor = request.user.profesional
            
            nueva_obs.save()
            messages.success(request, "Observación registrada correctamente.")
            return redirect('tuboApp:detalle_actividad', pk=pk)
    else:
        form = ObservacionRegistroForm()

    return render(request, 'coordinador/detalle_registros.html', {
        'actividad': actividad,
        'observaciones': observaciones,
        'form': form,
        'url_volver': url_listado_actividades(request),
    })