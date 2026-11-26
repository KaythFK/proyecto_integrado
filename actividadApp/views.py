from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from datetime import datetime, date, timedelta
import uuid
from usuariosApp.decorators import role_required
from .models import Actividad, Evidencia, Ausencia, Retroalimentacion, Validacion, GestionActividad
from .forms import ActividadForm, ActividadDelegadoForm, AusenciaForm, RetroalimentacionForm, EvidenciaForm, EvidenciaAdminForm, ValidacionForm, GestionActividadForm, ActividadProfesionalForm
from administracionApp.models import Profesional, Auditoria, Vecino, Periodo # <- Añadido Auditoria
from monitoreoApp.models import Meta, Indicador, Alerta
from monitoreoApp.views import estado_desviacion, resumen_indicadores
from monitoreoApp.services import dias_aviso_vencimiento, registrar_incumplimiento
from .filters import ActividadFilter
from django.urls import reverse
from config.utils import recordar_filtros, url_con_filtros, url_listado_actividades, delegacion_del_delegado
from tuboApp.models import Compromiso
from config.utils import con_marca_aprobada, rechazar_si_aprobada, puede_modificar_compromiso, validar_acceso_actividad, filtrar_evidencias_por_rol, validar_actividad_permite_evidencias, validar_actividad_finalizada, validar_datos_vecino_actividad, validar_tope_diario_actividades, validar_cierre_semanal, validar_evidencia_no_duplicada, validar_actividad_permite_evidencias, rol_usuario, validar_imagen_evidencia
from django.db import transaction
from config.utils import validar_evidencia_no_duplicada
from django.core.exceptions import ValidationError, PermissionDenied
import json
from django.forms.models import model_to_dict
from comunidadApp.models import AfiliacionVecino, VinculoFamiliar
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

def periodo_vigente():
    hoy = date.today()
    candidatos = Periodo.objects.filter(estado=True, fecha_inicio__lte=hoy, fecha_termino__gte=hoy).order_by('-fecha_inicio')
    return next((p for p in candidatos if p.esta_vigente), None)


def avance_diario(profesional, periodo):
    """Avance real vs. esperado al día; sin indicadores registrados el avance real es 0 %."""
    filas = resumen_indicadores(None, periodo, profesional=profesional)[0]
    if filas:
        return filas[0]
    esperado = periodo.porcentaje_esperado()
    return {'cumplimiento': 0, 'esperado': esperado, 'diferencia': round(-esperado, 1),
            'desviacion': estado_desviacion(0, esperado, periodo)}


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

    for actividad in actividades_asignadas:
        evidencia = Evidencia.objects.filter(id_actividad=actividad).first()
        if evidencia:
            actividad.estado_evidencia = evidencia.estado_revision
        else:
            actividad.estado_evidencia = 'SIN_EVIDENCIA'

    periodo_actual = periodo_vigente()
    mi_avance = avance_diario(profesional_actual, periodo_actual) if profesional_actual and periodo_actual else None
    semaforo = mi_avance['desviacion'] if mi_avance else None
    porcentaje_avance = round(mi_avance['cumplimiento']) if mi_avance else 0

    limite_vencimiento = date.today() + timedelta(days=dias_aviso_vencimiento())
    total_proximos = compromisos_tubo.filter(
        fecha_comprometida__gte=date.today(), fecha_comprometida__lte=limite_vencimiento
    ).exclude(estado_progreso='REALIZADO').count()

    context = {
        'total_asignadas': total_asignadas,
        'evidencias_registradas': evidencias_registradas,
        'actividades_asignadas': actividades_asignadas,
        'semaforo': semaforo, 
        'porcentaje_avance': porcentaje_avance,
        'compromisos_tubo': compromisos_tubo,
        'total_proximos_vencer': total_proximos,
        'profesional_actual': profesional_actual,
        'periodo_actual': periodo_actual,
        'mi_avance': mi_avance,
    }
    return render(request, 'profesional/dashboard_profesional.html', context)

@login_required
@role_required('Profesional')
def listar_actividades(request):
    profesional_actual = request.user.profesional
    propias = con_marca_aprobada(Actividad.objects.filter(id_profesional=profesional_actual)).prefetch_related('gestiones__tipo_gestion').order_by('-fecha_registro')
    filtro = ActividadFilter(request.GET, queryset=propias, ocultar=('delegacion', 'funcionario'))
    recordar_filtros(request, 'actividadApp:listar_actividades')

    context = {
        'actividades': filtro.qs if filtro.is_valid() else propias.none(),
        'filtro': filtro,
        'query': request.GET.get('q'),
    }
    return render(request, 'profesional/listar_actividades.html', context)

# No olvides importar las funciones y utilidades arriba en tu views.py:
# from config.utils import validar_datos_vecino_actividad, validar_tope_diario_actividades, validar_cierre_semanal
# from django.core.exceptions import ValidationError

@login_required
@role_required('Profesional')
def registrar_actividad(request, actividad_id=None):
    if request.method == 'POST':
        # Le pasamos el usuario logueado
        form = ActividadProfesionalForm(request.POST, usuario_actual=request.user) 
        
        if form.is_valid():
            # Si is_valid() es True, significa que pasó todas las reglas de utils.py
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
                    fecha_comprometida=nueva_actividad.fecha_comprometida or date.today() + timedelta(days=7), 
                    estado_progreso='INGRESADO',
                    estado=True,
                    id_funcionario=nueva_actividad.id_profesional, 
                    id_actividad=nueva_actividad,
                    organizacion=nueva_actividad.id_organizacion  
                )
                registrar_auditoria(request, "CREACION", "Compromiso", nuevo_compromiso)
                messages.success(request, f'¡Actividad registrada! Compromiso código {nueva_actividad.codigo_unico}.')
            else:
                messages.success(request, f'¡Actividad registrada con éxito! Código: {nueva_actividad.codigo_unico}')
            
            return redirect('actividadApp:dashboard_profesional') 
        else:
            messages.error(request, 'No se pudo guardar. Revisa las alertas en el formulario.')
    else:
        # GET: Renderizamos el formulario pasándole el usuario
        form = ActividadProfesionalForm(usuario_actual=request.user) 

    context = {
        'form': form,
        'titulo': 'Nueva Intervención Profesional'
    }
    return render(request, 'profesional/registrar_actividad.html', context)
@login_required
@role_required('Profesional')
def editar_actividad(request, id_actividad):
    actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
    validar_acceso_actividad(request.user, actividad)
    bloqueo = rechazar_si_aprobada(request, actividad, 'actividadApp:listar_actividades')
    if bloqueo:
        return bloqueo
    if request.method == 'POST':
        datos_antiguos = model_to_dict(actividad)
        form = ActividadForm(request.POST, instance=actividad)
        if form.is_valid():
            actividad_guardada = form.save()
            registrar_auditoria(request, "EDICION", "Actividad", actividad_guardada, datos_antiguos)
            messages.success(request, 'Actividad actualizada correctamente.')
            return redirect(url_con_filtros(request, 'actividadApp:listar_actividades'))
    else:
        form = ActividadForm(instance=actividad)
    return render(request, 'profesional/registrar_actividad.html', {
        'form': form, 
        'titulo': f'Editar Actividad: {actividad.codigo_unico}'
    })

# No olvides importar la función arriba:
# from config.utils import validar_actividad_permite_evidencias

def _clave_ingreso_evidencia(ev):
    meta = ev.metadatos if isinstance(ev.metadatos, dict) else {}
    lote = meta.get('lote_id') or ev.fecha.strftime('%Y%m%d%H%M')
    return f"{ev.id_actividad_id}_{lote}"


@login_required
@role_required('Profesional', 'Delegado', 'Administrador')
def registrar_evidencia(request, actividad_id):
    actividad = get_object_or_404(Actividad, id_actividad=actividad_id)
    validar_acceso_actividad(request.user, actividad)

    # NUEVO: Escudo modular desde utils.py
    try:
        validar_actividad_permite_evidencias(actividad)
    except ValidationError as e:
        mensaje_error = str(e.message if hasattr(e, 'message') else e.messages[0])
        messages.warning(request, mensaje_error)
        return redirect(request.META.get('HTTP_REFERER', 'actividadApp:dashboard_profesional'))

    errores_archivos = []

    if request.method == 'POST':
        archivos = request.FILES.getlist('archivo_foto')
        if not archivos:
            errores_archivos.append('Debes seleccionar al menos una fotografía o archivo de respaldo.')

        archivos_validados = []
        for archivo in archivos:
            try:
                archivos_validados.append(validar_imagen_evidencia(archivo))
            except ValidationError as e:
                msg = str(e.message if hasattr(e, 'message') else e.messages[0])
                errores_archivos.append(f"{archivo.name}: {msg}")

        if not errores_archivos:
            try:
                lote_id = str(uuid.uuid4())[:8]
                autor_nombre = request.user.username if request.user.is_authenticated else 'Profesional'
                with transaction.atomic():
                    for idx, archivo_limpio in enumerate(archivos_validados, start=1):
                        evidencia = Evidencia(
                            id_actividad=actividad,
                            archivo_foto=archivo_limpio,
                            estado=True,
                            metadatos={
                                "codigo_actividad": actividad.codigo_unico,
                                "autor": autor_nombre,
                                "origen": "Panel Profesional",
                                "lote_id": lote_id,
                                "lote_indice": idx,
                                "lote_total": len(archivos_validados),
                            },
                        )
                        evidencia.save()
                        registrar_auditoria(request, "CREACION", "Evidencia", evidencia)

                cantidad = len(archivos_validados)
                if cantidad == 1:
                    messages.success(request, f'Evidencia vinculada correctamente al código {actividad.codigo_unico}.')
                else:
                    messages.success(request, f'{cantidad} evidencias vinculadas correctamente al código {actividad.codigo_unico}.')

                if request.user.groups.filter(name='Delegado').exists():
                    return redirect(url_con_filtros(request, 'actividadApp:actividades_delegacion'))
                return redirect('actividadApp:dashboard_profesional')

            except Exception as e:
                messages.error(request, f'Error al guardar las evidencias: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en los archivos seleccionados.')

    form = EvidenciaForm(initial={'id_actividad': actividad})

    context = {
        'form': form,
        'actividad': actividad,
        'errores_archivos': errores_archivos,
    }
    return render(request, 'profesional/registrar_evidencia.html', context)

@login_required
@role_required('Profesional')
def desactivar_actividad(request, codigo_unico):
    actividad = get_object_or_404(Actividad, codigo_unico=codigo_unico)
    validar_acceso_actividad(request.user, actividad)
    bloqueo = rechazar_si_aprobada(request, actividad, 'actividadApp:listar_actividades')
    if bloqueo:
        return bloqueo
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

        if not puede_modificar_compromiso(request.user, compromiso):
            raise PermissionDenied('No tienes permiso para modificar este compromiso: está asignado a otro funcionario.')
        bloqueo = rechazar_si_aprobada(request, compromiso.id_actividad, 'actividadApp:dashboard_profesional')
        if bloqueo:
            return bloqueo

        nuevo_estado = request.POST.get('estado_progreso')
        registrar_incumplimiento(compromiso)
        estados_validos = dict(Compromiso.OPCIONES_ESTADO_PROGRESO).keys()
        
        if nuevo_estado in estados_validos:
            with transaction.atomic():
                datos_antiguos = model_to_dict(compromiso)
                actividad = compromiso.id_actividad
                datos_antiguos_actividad = model_to_dict(actividad)

                compromiso.estado_progreso = nuevo_estado
                if nuevo_estado == 'REALIZADO':
                    compromiso.fecha_termino = date.today()
                else:
                    compromiso.fecha_termino = None
                compromiso.save()

                if nuevo_estado == 'INGRESADO':
                    actividad.estado_progreso = 'PENDIENTE'
                elif nuevo_estado == 'REALIZADO':
                    actividad.estado_progreso = 'FINALIZADA'
                else:
                    actividad.estado_progreso = nuevo_estado
                actividad.save()

                registrar_auditoria(request, "CAMBIO_PROGRESO", "Compromiso", compromiso, datos_antiguos)
                registrar_auditoria(request, "CAMBIO_PROGRESO", "Actividad", actividad, datos_antiguos_actividad)
            
            messages.success(request, f'El compromiso en {compromiso.territorio} se ha actualizado a: {compromiso.get_estado_progreso_display()}')
        else:
            messages.error(request, 'Error: El estado seleccionado no es válido.')
    return redirect('actividadApp:dashboard_profesional')

login_required
@role_required('Delegado')
def actividades_delegacion(request):
    delegacion_actual = request.user.profesional.id_delegacion
    del_equipo = con_marca_aprobada(Actividad.objects.filter(id_profesional__id_delegacion=delegacion_actual)).order_by('-fecha_registro')
    equipo = Profesional.objects.filter(id_delegacion=delegacion_actual, estado=True)
    filtro = ActividadFilter(request.GET, queryset=del_equipo, profesionales=equipo, ocultar=('delegacion',))
    recordar_filtros(request, 'actividadApp:actividades_delegacion')

    retroalimentaciones_delegacion = Retroalimentacion.objects.filter(
        delegacion=delegacion_actual,
        estado=True
    ).select_related('retroalimentado', 'meta', 'vecino').order_by('-fecha', '-id_retroalimentacion')

    context = {
        'actividades': filtro.qs if filtro.is_valid() else del_equipo.none(),
        'filtro': filtro,
        'query': request.GET.get('q'),
        'delegacion_nombre': delegacion_actual.nombre,
        'retroalimentaciones': retroalimentaciones_delegacion,
    }
    return render(request, 'delegado/lista_actividades.html', context)

@login_required
@role_required('Delegado')
def registrar_actividad_delegado(request):
    delegacion_actual = request.user.profesional.id_delegacion

    if request.method == 'POST':
        form = ActividadDelegadoForm(request.POST, delegacion=delegacion_actual)
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
                            fecha_comprometida=nueva_actividad.fecha_comprometida or date.today() + timedelta(days=7), 
                            estado_progreso='INGRESADO',
                            estado=True,
                            id_funcionario=nueva_actividad.id_profesional,
                            id_actividad=nueva_actividad,
                            organizacion=nueva_actividad.id_organizacion
                        )
                        registrar_auditoria(request, "CREACION", "Compromiso", nuevo_compromiso)
                        messages.success(request, f'¡Actividad registrada y derivada al Tubo! Código: {nueva_actividad.codigo_unico}.')
                    else:
                        messages.success(request, f'¡Actividad registrada con éxito! Código: {nueva_actividad.codigo_unico}')
                    
                    return redirect(url_con_filtros(request, 'actividadApp:actividades_delegacion'))
            except Exception as e:
                messages.error(request, f'Error al registrar la actividad: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        form = ActividadDelegadoForm(delegacion=delegacion_actual)

    context = {
        'form': form,
        'titulo': 'Registrar Nueva Actividad',  # (o el título de editar)
        'filtro_metas_data': form.datos_filtro_metas(),
    }
    return render(request, 'delegado/form_actividad.html', context)


@login_required
@role_required('Delegado')
def editar_actividad_delegado(request, id_actividad):
    delegacion_actual = request.user.profesional.id_delegacion
    actividad = get_object_or_404(Actividad, id_actividad=id_actividad, id_profesional__id_delegacion=delegacion_actual)
    bloqueo = rechazar_si_aprobada(request, actividad, 'actividadApp:actividades_delegacion')
    if bloqueo:
        return bloqueo
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(actividad)
        form = ActividadDelegadoForm(request.POST, instance=actividad, delegacion=delegacion_actual)
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
                    return redirect(url_con_filtros(request, 'actividadApp:actividades_delegacion'))
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        form = ActividadDelegadoForm(instance=actividad, delegacion=delegacion_actual)

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
        bloqueo = rechazar_si_aprobada(request, actividad, 'actividadApp:actividades_delegacion')
        if bloqueo:
            return bloqueo
        
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
            
    return redirect(url_con_filtros(request, 'actividadApp:actividades_delegacion'))

@login_required
def actualizar_progreso_actividad(request, id_actividad):
    if request.method == 'POST':
        actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
        validar_acceso_actividad(request.user, actividad)
        bloqueo = rechazar_si_aprobada(request, actividad, 'actividadApp:listar_actividades')
        if bloqueo:
            return bloqueo
        
        # NUEVO ESCUDO: Verificamos que no esté finalizada antes de intentar cambiarla
        try:
            validar_actividad_finalizada(actividad)
        except ValidationError as e:
            mensaje = str(e.message if hasattr(e, 'message') else e.messages[0])
            messages.warning(request, mensaje)
            return redirect(request.META.get('HTTP_REFERER', '/'))

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


def recalcular_indicadores(request, profesional, periodo, evento):
    """Recalcula los indicadores del profesional en el período y deja en la auditoría los que cambiaron."""
    from monitoreoApp.services import sincronizar_indicador
    cambiados = 0
    indicadores = (Indicador.objects
                   .filter(estado=True, id_funcionario=profesional, meta_id_meta__id_periodo=periodo, meta_id_meta__estado=True)
                   .select_related('meta_id_meta__id_periodo', 'id_funcionario'))
    for indicador in indicadores:
        antes = model_to_dict(indicador)
        sincronizar_indicador(indicador, guardar=True)
        if any(str(antes[campo]) != str(getattr(indicador, campo)) for campo in ('avance', 'ajuste', 'cumplimiento', 'semaforo')):
            registrar_auditoria(request, evento, "Indicador", indicador, antes)
            cambiados += 1
    return cambiados


def recalcular_por_retroalimentacion(request, retro):
    if retro.meta_id and retro.retroalimentado_id and retro.meta.id_periodo.esta_abierto:
        recalcular_indicadores(request, retro.retroalimentado, retro.meta.id_periodo, "AJUSTE_RETROALIMENTACION")


def ausencias_visibles(user):
    ausencias = Ausencia.objects.select_related('profesional_ausente', 'periodo_ausencia')
    delegacion = delegacion_del_delegado(user)
    if delegacion is not None:
        ausencias = ausencias.filter(profesional_ausente__id_delegacion=delegacion)
    return ausencias


def mensaje_recalculo(cambiados):
    if not cambiados:
        return ''
    return f' Se recalcularon {cambiados} indicador{"es" if cambiados != 1 else ""} del funcionario.'


@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def lista_ausencias(request):
    query = request.GET.get('q')
    ausencias = ausencias_visibles(request.user).order_by('-id_ausencia')

    if query:
        tipos = [clave for clave, nombre in Ausencia.OPCIONES_TIPO if query.lower() in nombre.lower()]
        ausencias = ausencias.filter(
            Q(profesional_ausente__nombres__icontains=query) |
            Q(profesional_ausente__apellido_paterno__icontains=query) |
            Q(tipo_ausencia__in=tipos)
        ).distinct()

    return render(request, 'administrador/ausencias/lista_ausencias.html', {
        'ausencias': ausencias,
        'query': query,
        'delegacion': delegacion_del_delegado(request.user),
    })

@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def crear_ausencia(request):
    delegacion = delegacion_del_delegado(request.user)
    if request.method == 'POST':
        form = AusenciaForm(request.POST, delegacion=delegacion)
        if form.is_valid():
            try:
                with transaction.atomic():
                    ausencia = form.save(commit=False)
                    ausencia.estado = True
                    ausencia.save()
                    registrar_auditoria(request, "CREACION", "Ausencia", ausencia)
                    cambiados = recalcular_indicadores(request, ausencia.profesional_ausente, ausencia.periodo_ausencia, "AJUSTE_AUSENCIA")
                messages.success(request, 'El registro de ausencia fue guardado con éxito.' + mensaje_recalculo(cambiados))
                return redirect('actividadApp:lista_ausencias')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = AusenciaForm(delegacion=delegacion)

    return render(request, 'administrador/ausencias/form_ausencia.html', {
        'form': form,
        'titulo': 'Registrar Ausencia o Permiso'
    })

@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def editar_ausencia(request, id_ausencia):
    ausencia = get_object_or_404(ausencias_visibles(request.user), pk=id_ausencia)
    delegacion = delegacion_del_delegado(request.user)
    if not ausencia.periodo_ausencia.esta_abierto:
        messages.error(request, 'No se puede editar una ausencia de un período cerrado.')
        return redirect('actividadApp:lista_ausencias')

    if request.method == 'POST':
        datos_antiguos = model_to_dict(ausencia)
        profesional_anterior, periodo_anterior = ausencia.profesional_ausente, ausencia.periodo_ausencia
        form = AusenciaForm(request.POST, instance=ausencia, delegacion=delegacion)
        if form.is_valid():
            try:
                with transaction.atomic():
                    ausencia_guardada = form.save()
                    registrar_auditoria(request, "EDICION", "Ausencia", ausencia_guardada, datos_antiguos)
                    cambiados = recalcular_indicadores(request, ausencia_guardada.profesional_ausente, ausencia_guardada.periodo_ausencia, "AJUSTE_AUSENCIA")
                    if (profesional_anterior, periodo_anterior) != (ausencia_guardada.profesional_ausente, ausencia_guardada.periodo_ausencia):
                        cambiados += recalcular_indicadores(request, profesional_anterior, periodo_anterior, "AJUSTE_AUSENCIA")
                messages.success(request, 'La ausencia fue actualizada correctamente.' + mensaje_recalculo(cambiados))
                return redirect('actividadApp:lista_ausencias')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = AusenciaForm(instance=ausencia, delegacion=delegacion)

    return render(request, 'administrador/ausencias/form_ausencia.html', {
        'form': form,
        'titulo': 'Editar Ausencia'
    })

@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def cambiar_estado_ausencia(request, id_ausencia):
    if request.method == 'POST':
        ausencia = get_object_or_404(ausencias_visibles(request.user), pk=id_ausencia)
        if not ausencia.periodo_ausencia.esta_abierto:
            messages.error(request, 'No se puede modificar una ausencia de un período cerrado.')
            return redirect('actividadApp:lista_ausencias')
        if not ausencia.estado and AusenciaForm.se_superpone(ausencia):
            messages.error(request, 'No se puede reactivar: el funcionario ya tiene otra ausencia activa en esas fechas.')
            return redirect('actividadApp:lista_ausencias')

        with transaction.atomic():
            datos_antiguos = model_to_dict(ausencia)
            nuevo_estado = not ausencia.estado
            ausencia.estado = nuevo_estado
            ausencia.save()
            registrar_auditoria(request, "CAMBIO_ESTADO", "Ausencia", ausencia, datos_antiguos)
            cambiados = recalcular_indicadores(request, ausencia.profesional_ausente, ausencia.periodo_ausencia, "AJUSTE_AUSENCIA")

        accion_str = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'El registro de ausencia fue {accion_str} correctamente.' + mensaje_recalculo(cambiados))

    return redirect('actividadApp:lista_ausencias')



@login_required
@role_required('Delegado', 'Administrador')
def lista_retroalimentaciones(request):
    delegado_prof = getattr(request.user, 'profesional', None)
    if not delegado_prof or not delegado_prof.id_delegacion:
        raise PermissionDenied("Tu usuario no tiene una delegación asociada.")

    query = request.GET.get('q')
    retroalimentaciones = Retroalimentacion.objects.filter(
        delegacion=delegado_prof.id_delegacion
    ).select_related(
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
@role_required('Delegado', 'Administrador')
def crear_retroalimentacion(request):
    delegado_prof = getattr(request.user, 'profesional', None)
    if not delegado_prof or not delegado_prof.id_delegacion:
        raise PermissionDenied("Tu usuario no tiene una delegación asociada.")

    if request.method == 'POST':
        form = RetroalimentacionForm(
            request.POST,
            request.FILES,
            delegacion=delegado_prof.id_delegacion
        )
        if form.is_valid():
            try:
                with transaction.atomic():
                    retro = form.save(commit=False)

                    # Bloqueo en backend (KAN-386): exige respaldo formal antes de asignar puntaje/impacto
                    if not retro.archivo_respaldo:
                        raise ValidationError("No se puede registrar ni asignar puntaje sin respaldo formal.")

                    retro.estado = True
                    retro.receptor = delegado_prof
                    retro.delegacion = delegado_prof.id_delegacion
                    retro.save()

                    if retro.tipo == 'RECLAMO':
                        Alerta.objects.create(
                            motivo=f"Reclamo formal registrado ({retro.retroalimentado})",
                            enlace_referencia=retro.archivo_respaldo.url if retro.archivo_respaldo else "",
                            id_destinatario=retro.retroalimentado,
                            id_responsable=delegado_prof,
                            id_delegacion=retro.delegacion,
                        )

                    registrar_auditoria(request, "CREACION", "Retroalimentacion", retro)
                    recalcular_por_retroalimentacion(request, retro)

                messages.success(request, 'La retroalimentación formal fue registrada correctamente.')
                return redirect('actividadApp:lista_retroalimentaciones')
            except ValidationError as e:
                msg = str(e.message if hasattr(e, 'message') else e.messages[0])
                messages.error(request, msg)
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = RetroalimentacionForm(delegacion=delegado_prof.id_delegacion)

    return render(request, 'administrador/retroalimentaciones/form_retroalimentacion.html', {
        'form': form,
        'titulo': 'Registrar Felicitación o Reclamo Formal'
    })


@login_required
@role_required('Delegado', 'Administrador')
def editar_retroalimentacion(request, id_retroalimentacion):
    delegado_prof = getattr(request.user, 'profesional', None)
    retro = get_object_or_404(
        Retroalimentacion,
        pk=id_retroalimentacion,
        delegacion=delegado_prof.id_delegacion if delegado_prof else None
    )

    if request.method == 'POST':
        datos_antiguos = model_to_dict(retro)
        form = RetroalimentacionForm(
            request.POST,
            request.FILES,
            instance=retro,
            delegacion=delegado_prof.id_delegacion
        )
        if form.is_valid():
            try:
                with transaction.atomic():
                    anterior = Retroalimentacion.objects.get(pk=retro.pk)
                    retro_guardada = form.save()
                    registrar_auditoria(request, "EDICION", "Retroalimentacion", retro_guardada, datos_antiguos)
                    recalcular_por_retroalimentacion(request, retro_guardada)
                    if (anterior.meta_id, anterior.retroalimentado_id) != (retro_guardada.meta_id, retro_guardada.retroalimentado_id):
                        recalcular_por_retroalimentacion(request, anterior)
                messages.success(request, 'La retroalimentación fue actualizada correctamente.')
                return redirect('actividadApp:lista_retroalimentaciones')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = RetroalimentacionForm(instance=retro, delegacion=delegado_prof.id_delegacion)

    return render(request, 'administrador/retroalimentaciones/form_retroalimentacion.html', {
        'form': form,
        'titulo': 'Editar Retroalimentación'
    })


@login_required
@role_required('Delegado', 'Administrador')
def cambiar_estado_retroalimentacion(request, id_retroalimentacion):
    if request.method == 'POST':
        delegado_prof = getattr(request.user, 'profesional', None)
        retro = get_object_or_404(
            Retroalimentacion,
            pk=id_retroalimentacion,
            delegacion=delegado_prof.id_delegacion if delegado_prof else None
        )

        with transaction.atomic():
            datos_antiguos = model_to_dict(retro)
            nuevo_estado = not retro.estado
            retro.estado = nuevo_estado
            retro.save()
            registrar_auditoria(request, "CAMBIO_ESTADO", "Retroalimentacion", retro, datos_antiguos)
            recalcular_por_retroalimentacion(request, retro)

        accion_str = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'La retroalimentación fue {accion_str} correctamente.')

    return redirect('actividadApp:lista_retroalimentaciones')



@login_required
@role_required('Administrador', 'Profesional', 'Delegado')
def lista_evidencias(request):
    query = (request.GET.get('q') or '').strip()

    # Aplicamos la regla modular de filtrado por rol
    evidencias = (
        filtrar_evidencias_por_rol(request.user)
        .select_related('id_actividad', 'id_actividad__id_profesional')
        .order_by('-id_evidencia')
    )

    # Lógica de búsqueda por texto
    if query:
        evidencias = evidencias.filter(
            Q(archivo_foto__icontains=query) |
            Q(estado_revision__icontains=query) |
            Q(id_actividad__codigo_unico__icontains=query)
        ).distinct()

    evidencias_list = list(evidencias)
    validaciones_por_evidencia = {}
    for val in Validacion.objects.filter(id_evidencia__in=evidencias_list).select_related('id_validador').order_by('-id_validacion'):
        if val.id_evidencia_id not in validaciones_por_evidencia:
            validaciones_por_evidencia[val.id_evidencia_id] = val

    grupos_map = {}
    for ev in evidencias_list:
        clave = _clave_ingreso_evidencia(ev)
        if clave not in grupos_map:
            grupos_map[clave] = {
                'evidencia': ev,
                'evidencias': [],
                'validacion': None,
                'estado_revision': ev.estado_revision,
                'tiene_pendientes': False,
                'url_evidencias': [],
            }

        grupo = grupos_map[clave]
        grupo['evidencias'].append(ev)
        if ev.estado_revision == 'PENDIENTE':
            grupo['tiene_pendientes'] = True
            grupo['url_evidencias'].append(f"evidencias={ev.pk}")

        if not grupo['validacion'] and ev.pk in validaciones_por_evidencia:
            grupo['validacion'] = validaciones_por_evidencia[ev.pk]

        estados = {item.estado_revision for item in grupo['evidencias']}
        if 'RECHAZADO' in estados:
            grupo['estado_revision'] = 'RECHAZADO'
        elif estados == {'APROBADO'}:
            grupo['estado_revision'] = 'APROBADO'
        elif 'PENDIENTE' in estados:
            grupo['estado_revision'] = 'PENDIENTE'
        else:
            grupo['estado_revision'] = ev.estado_revision

    evidencias_con_validacion = []
    for grupo in grupos_map.values():
        if not grupo['url_evidencias']:
            grupo['url_evidencias'] = [f"evidencias={ev.pk}" for ev in grupo['evidencias']]
        grupo['query_validacion'] = "&".join(grupo['url_evidencias'])
        evidencias_con_validacion.append(grupo)

    return render(request, 'administrador/evidencias/lista_evidencias.html', {
        'evidencias_con_validacion': evidencias_con_validacion,
        'query': query,
    })

@login_required
@role_required('Administrador')
def crear_evidencia(request):
    if request.method == 'POST':
        form = EvidenciaAdminForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    evidencia = form.save(commit=False)
                    evidencia.estado = True
                    
                    evidencia.metadatos = {
                        "registrado_por": request.user.username,
                        "origen": "Panel de Administración Global",
                        "fecha_sistema": str(date.today())
                    }
                    
                    evidencia.save()
                    
                    # --- ¡AQUÍ ESTÁ ASEGURADA LA AUDITORÍA! ---
                    registrar_auditoria(request, "CREACION", "Evidencia", evidencia)
                    
                messages.success(request, 'La evidencia fue registrada con éxito.')
                return redirect('actividadApp:lista_evidencias')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = EvidenciaAdminForm()
        
    return render(request, 'administrador/evidencias/form_evidencia.html', {
        'form': form,
        'titulo': 'Registrar Evidencia Global'
    })

@login_required
@role_required('Administrador', 'Profesional')
def editar_evidencia(request, id_evidencia):
    evidencia = get_object_or_404(Evidencia, pk=id_evidencia)
    validar_acceso_actividad(request.user, evidencia.id_actividad)
    bloqueo = rechazar_si_aprobada(request, evidencia.id_actividad, 'actividadApp:lista_evidencias')
    if bloqueo:
        return bloqueo
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(evidencia)
        # Se incluye request.FILES por si editan y cambian la foto
        form = EvidenciaForm(request.POST, request.FILES, instance=evidencia)
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
        validar_acceso_actividad(request.user, evidencia.id_actividad)
        bloqueo = rechazar_si_aprobada(request, evidencia.id_actividad, 'actividadApp:lista_evidencias')
        if bloqueo:
            return bloqueo
        
        with transaction.atomic():
            datos_antiguos = model_to_dict(evidencia)
            nuevo_estado = not evidencia.estado
            evidencia.estado = nuevo_estado
            evidencia.save()
            registrar_auditoria(request, "CAMBIO_ESTADO", "Evidencia", evidencia, datos_antiguos)
                
        accion_str = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'La evidencia fue {accion_str} correctamente.')
        
    return redirect('actividadApp:lista_evidencias')


@login_required
@role_required('Administrador', 'Delegado')
def lista_validaciones(request):
    query = (request.GET.get('q') or '').strip()
    validaciones = Validacion.objects.all().select_related(
        'id_evidencia',
        'id_evidencia__id_actividad',
        'id_validador',
    ).order_by('-id_validacion')
    delegacion = delegacion_del_delegado(request.user)
    if delegacion is not None:
        validaciones = validaciones.filter(id_evidencia__id_actividad__id_profesional__id_delegacion=delegacion)

    if query:
        validaciones = validaciones.filter(
            Q(observacion__icontains=query) |
            Q(decision__icontains=query) |
            Q(id_validador__nombres__icontains=query) |
            Q(id_evidencia__archivo_foto__icontains=query) |
            Q(id_evidencia__id_actividad__codigo_unico__icontains=query)
        ).distinct()

    grupos_val = {}
    for val in validaciones:
        clave = _clave_ingreso_evidencia(val.id_evidencia)
        if clave not in grupos_val:
            grupos_val[clave] = val

    validaciones_agrupadas = list(grupos_val.values())

    return render(request, 'administrador/validaciones/lista_validaciones.html', {
        'validaciones': validaciones_agrupadas,
        'query': query,
    })

@login_required
@role_required('Administrador', 'Delegado')
def crear_validacion(request):
    evidencia_id = request.GET.get('evidencia') or request.POST.get('id_evidencia')
    evidencias_ids_raw = request.GET.getlist('evidencias') or request.POST.getlist('evidencias')

    evidencias_objetivo = []
    if evidencias_ids_raw:
        ids_limpios = [int(x) for x in evidencias_ids_raw if str(x).isdigit()]
        evidencias_objetivo = list(
            Evidencia.objects.filter(pk__in=ids_limpios)
            .select_related('id_actividad', 'id_actividad__id_profesional', 'id_actividad__id_meta__id_periodo')
            .order_by('id_evidencia')
        )
    elif evidencia_id and str(evidencia_id).isdigit():
        ev_base = get_object_or_404(
            Evidencia.objects.select_related('id_actividad', 'id_actividad__id_profesional', 'id_actividad__id_meta__id_periodo'),
            pk=int(evidencia_id),
        )
        clave_base = _clave_ingreso_evidencia(ev_base)
        misma_actividad = Evidencia.objects.filter(id_actividad=ev_base.id_actividad, estado=True).order_by('id_evidencia')
        evidencias_objetivo = [e for e in misma_actividad if _clave_ingreso_evidencia(e) == clave_base] or [ev_base]

    evidencia_obj = evidencias_objetivo[0] if evidencias_objetivo else None
    if evidencia_obj is not None:
        validar_acceso_actividad(request.user, evidencia_obj.id_actividad)

    # Obtenemos el perfil profesional del usuario actual logueado para asignarlo como validador automático
    profesional_actual = getattr(request.user, 'profesional', None)

    if request.method == 'POST':
        form = ValidacionForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    decision = form.cleaned_data['decision']
                    observacion = form.cleaned_data.get('observacion')
                    version = form.cleaned_data['version']

                    objetivos_a_validar = evidencias_objetivo if evidencias_objetivo else (
                        [form.cleaned_data['id_evidencia']] if form.cleaned_data.get('id_evidencia') else []
                    )
                    if not objetivos_a_validar:
                        raise ValidationError("No se encontraron evidencias para validar.")

                    if decision == 'APROBADO':
                        for ev in objetivos_a_validar:
                            validar_evidencia_no_duplicada(ev)

                    validaciones_creadas = []
                    for ev in objetivos_a_validar:
                        val = Validacion(
                            decision=decision,
                            observacion=observacion,
                            version=version,
                            estado=True,
                            id_evidencia=ev,
                            id_validador=profesional_actual,
                        )
                        val.save()
                        validaciones_creadas.append(val)

                        if decision == 'APROBADO':
                            ev.estado_revision = 'APROBADO'
                        elif decision == 'RECHAZADO':
                            ev.estado_revision = 'RECHAZADO'
                        else:
                            ev.estado_revision = 'REVISADO'
                        ev.save()

                        registrar_auditoria(request, "CREACION", "Validacion", val)

                    # [KAN-169] ACCIÓN: Sumar avance solo si está "Aprobada" (una vez por actividad)
                    periodo_abierto = True
                    meta = None
                    if decision == 'APROBADO' and evidencia_obj is not None:
                        actividad = evidencia_obj.id_actividad
                        meta = actividad.id_meta
                        indicador = Indicador.objects.filter(meta_id_meta=meta).first()

                        periodo_abierto = meta is not None and meta.id_periodo.esta_abierto
                        if indicador and periodo_abierto:
                            indicador.avance += 1
                            indicador.save()
                            registrar_auditoria(request, "ACTUALIZACION_AVANCE", "Indicador", indicador)

                if decision == 'APROBADO' and not periodo_abierto and meta is not None:
                    messages.warning(request, f'Las evidencias fueron aprobadas, pero no suman al indicador porque el período "{meta.id_periodo.nombre}" está cerrado.')
                else:
                    messages.success(request, f'La validación fue registrada con éxito para {len(validaciones_creadas)} evidencia(s) y el avance ha sido actualizado.')
                return redirect('actividadApp:lista_validaciones')

            except ValidationError as e:
                messages.error(request, str(e.message if hasattr(e, 'message') else e.messages[0]))
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        initial_data = {}
        if evidencia_obj:
            initial_data['id_evidencia'] = evidencia_obj
        if profesional_actual:
            initial_data['id_validador'] = profesional_actual

        form = ValidacionForm(initial=initial_data)

    return render(request, 'administrador/validaciones/form_validacion.html', {
        'form': form,
        'titulo': 'Registrar Validación de Evidencia',
        'evidencia': evidencia_obj,
        'evidencias_grupo': evidencias_objetivo,
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
        'titulo': 'Editar Validación'
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
@role_required('Profesional', 'Administrador')
def lista_gestiones(request, id_actividad):
    """ Muestra la tabla de gestiones para una actividad específica con su barra de búsqueda """
    actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
    validar_acceso_actividad(request.user, actividad)
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
@role_required('Profesional', 'Administrador')
def crear_gestion(request, id_actividad):
    actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
    validar_acceso_actividad(request.user, actividad)
    bloqueo = rechazar_si_aprobada(request, actividad, reverse('actividadApp:lista_gestiones', args=[actividad.pk]))
    if bloqueo:
        return bloqueo
    
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
@role_required('Profesional', 'Administrador')
def editar_gestion(request, id_gestion):
    gestion = get_object_or_404(GestionActividad, id_gestion=id_gestion)
    validar_acceso_actividad(request.user, gestion.actividad)
    bloqueo = rechazar_si_aprobada(request, gestion.actividad, reverse('actividadApp:lista_gestiones', args=[gestion.actividad_id]))
    if bloqueo:
        return bloqueo
    
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
@role_required('Profesional', 'Administrador')
def cambiar_estado_gestion(request, id_gestion):
    if request.method == 'POST':
        gestion = get_object_or_404(GestionActividad, id_gestion=id_gestion)
        validar_acceso_actividad(request.user, gestion.actividad)
        bloqueo = rechazar_si_aprobada(request, gestion.actividad, reverse('actividadApp:lista_gestiones', args=[gestion.actividad_id]))
        if bloqueo:
            return bloqueo
        
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


@login_required
@role_required('Delegado')
def gestiones_delegado(request, id_actividad):
    """Vista exclusiva de consulta para que el Delegado revise las gestiones de una actividad de su delegación."""
    delegacion_actual = getattr(getattr(request.user, 'profesional', None), 'id_delegacion', None)
    if not delegacion_actual:
        raise PermissionDenied("Tu usuario no tiene una delegación asociada.")

    actividad = get_object_or_404(
        Actividad,
        id_actividad=id_actividad,
        id_profesional__id_delegacion=delegacion_actual,
    )
    validar_acceso_actividad(request.user, actividad)

    gestiones = (
        GestionActividad.objects.filter(actividad=actividad)
        .select_related('tipo_gestion', 'subtipo_gestion', 'profesional')
        .order_by('-fecha_registro')
    )

    query = request.GET.get('q')
    if query:
        gestiones = gestiones.filter(
            Q(tipo_gestion__nombre__icontains=query) |
            Q(subtipo_gestion__nombre__icontains=query) |
            Q(descripcion__icontains=query) |
            Q(profesional__nombres__icontains=query) |
            Q(profesional__apellido_paterno__icontains=query)
        ).distinct()

    return render(request, 'delegado/lista_gestiones.html', {
        'actividad': actividad,
        'gestiones': gestiones,
        'query': query,
        'delegacion_nombre': delegacion_actual.nombre,
    })


@login_required
def detalle_vecino(request, id_vecino):
    vecino = get_object_or_404(Vecino, pk=id_vecino)
    actividades_vecino = Actividad.objects.filter(solicitante_vecino=vecino).order_by('-fecha_registro')
    afiliaciones_vecino = (
        AfiliacionVecino.objects.filter(vecino=vecino)
        .select_related('organizacion', 'organizacion__id_delegacion')
        .order_by('-estado', '-id_afiliacion')
    )

    vinculos_cargas = list(
        VinculoFamiliar.objects.filter(familiar=vecino)
        .select_related('carga')
        .prefetch_related('carga__vinculos__familiar')
        .order_by('-estado', '-id_vinculo')
    )

    cargas_detalle = []
    for v in vinculos_cargas:
        otros_vinculos = [
            otro for otro in v.carga.vinculos.all()
            if otro.estado and otro.familiar_id != vecino.pk
        ]
        if v.vive_con_este_vecino:
            badge_residencia = 'Vive en este domicilio'
            badge_clase = 'bg-success'
        elif v.carga.padres_separados:
            badge_residencia = 'Padres separados - Vive con otro progenitor'
            badge_clase = 'bg-warning text-dark'
        else:
            badge_residencia = 'No vive en este domicilio'
            badge_clase = 'bg-secondary'

        cargas_detalle.append({
            'vinculo': v,
            'carga': v.carga,
            'otros_vinculos': otros_vinculos,
            'badge_residencia': badge_residencia,
            'badge_clase': badge_clase,
        })

    # Determinamos el rol exacto para el menú lateral dinámico
    if request.user.groups.filter(name='Administrador').exists():
        rol_menu = 'administrador'
    elif request.user.groups.filter(name='Coordinador').exists():
        rol_menu = 'coordinador'
    elif request.user.groups.filter(name='Delegado').exists():
        rol_menu = 'delegado'
    else:
        rol_menu = 'profesional'

    context = {
        'vecino': vecino,
        'actividades_vecino': actividades_vecino,
        'afiliaciones_vecino': afiliaciones_vecino,
        'vinculos_cargas': vinculos_cargas,
        'cargas_detalle': cargas_detalle,
        'rol_menu': rol_menu,
    }
    return render(request, 'detalle_vecino.html', context)

# ==========================================
# UTILIDAD ORM PARA REPORTES Y ESTADÍSTICAS (CA3)
# ==========================================
def obtener_atenciones_validas_para_informe():
    """
    Cumple con el CA3: Retorna únicamente las atenciones/actividades válidas 
    (excluyendo el borrado lógico con estado=True) contadas de manera única 
    para los informes estadísticos de la municipalidad.
    """
    return Actividad.objects.filter(estado=True).distinct()


@login_required
@role_required('Administrador', 'Coordinador')
def gestiones_coordinador(request, id_actividad):
    """ Vista exclusiva para que el Coordinador audite las gestiones de una actividad """
    actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
    
    # Validamos acceso corporativo con tu util existente
    validar_acceso_actividad(request.user, actividad)
    
    # Registramos en la auditoría del sistema que el coordinador consultó las gestiones de esta actividad
    try:
        registrar_auditoria(request, "CONSULTA_AUDITORIA", "Actividad", actividad)
    except Exception:
        pass  # Evita que falle si la estructura de auditoría requiere un evento específico
    
    gestiones = GestionActividad.objects.filter(actividad=actividad).select_related('tipo_gestion', 'profesional').order_by('-fecha_registro')
    
    # Filtro de búsqueda opcional por si la actividad tiene muchas gestiones
    query = request.GET.get('q')
    if query:
        gestiones = gestiones.filter(
            Q(tipo_gestion__nombre__icontains=query) |
            Q(descripcion__icontains=query)
        ).distinct()
    
    contexto = {
        'actividad': actividad,
        'gestiones': gestiones,
        'query': query,
        'url_volver': url_con_filtros(request, 'tuboApp:listar_todas'),
        **rol_usuario(request)
    }
    return render(request, 'coordinador/gestiones_coordinador.html', contexto)


@login_required
@role_required('Administrador', 'Coordinador')
def cambiar_estado_actividad_coordinador(request, id_actividad):
    """ Vista exclusiva para que el Coordinador cambie el estado mediante POST """
    if request.method == 'POST':
        actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
        bloqueo = rechazar_si_aprobada(request, actividad, 'tuboApp:listar_todas')
        if bloqueo:
            return bloqueo
        
        with transaction.atomic():
            from django.forms.models import model_to_dict
            datos_antiguos = model_to_dict(actividad)
            
            nuevo_estado = not actividad.estado
            actividad.estado = nuevo_estado
            actividad.save()
            
            # Auditoría (Importando la función desde administracionApp si es necesario)
            try:
                from administracionApp.views import registrar_auditoria
                registrar_auditoria(request, "CAMBIO_ESTADO", "Actividad", actividad, datos_antiguos)
            except Exception:
                pass
                
        accion = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'La actividad {actividad.codigo_unico} fue {accion}.')
        
    return redirect(url_con_filtros(request, 'tuboApp:listar_todas'))