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

# --- NUEVOS IMPORTS PARA AUDITORÍA ---
from administracionApp.models import Profesional, Auditoria
import json
from django.forms.models import model_to_dict
from config.utils import puede_modificar_compromiso


def url_tubo_segun_rol(user):
    # HU-13 CA3: tras guardar, cada rol vuelve a SU pantalla del tubo (antes todos iban a la del
    # Administrador y al delegado lo sacaba del sistema por no tener ese rol)
    if user.groups.filter(name='Administrador').exists():
        return 'tuboApp:tubo'
    if user.groups.filter(name='Delegado').exists():
        return 'monitoreoApp:tubo_delegacion'
    if user.groups.filter(name='Coordinador').exists():
        return 'tuboApp:dashboard_coordinador'
    return 'tuboApp:tubo'

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
@role_required('Administrador')
def agenda(request):
    query = request.GET.get('q')
    compromisos = Compromiso.objects.select_related('id_actividad', 'id_funcionario', 'apoyo').all().order_by('-fecha_registro')
    observaciones = ObservacionCompromiso.objects.all().order_by('-fecha')
    
    if query:
        compromisos = compromisos.filter(
            Q(id_actividad__codigo_unico__icontains=query) |
            Q(id_actividad__solicitud_problema__icontains=query) |
            Q(territorio__icontains=query)
        ).distinct()

    context = {
        'compromisos': compromisos,
        'observaciones': observaciones,
        'query': query,
    }
    return render(request, 'administrador/tubo/lista_tubo.html', context)


@login_required
@role_required('Administrador', 'Coordinador', 'Delegado')
def actualizar_progreso_tubo(request, id_compromiso):
    if request.method == 'POST':
        compromiso = get_object_or_404(Compromiso, id_compromiso=id_compromiso)

        # HU-13 CA1: el delegado solo puede cambiar compromisos de su delegación
        if not puede_modificar_compromiso(request.user, compromiso):
            messages.error(request, 'No tienes permiso para modificar este compromiso.')
            return redirect(url_tubo_segun_rol(request.user))

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
        texto_obs = request.POST.get('texto_observacion')
        
        if texto_obs and texto_obs.strip():
            try:
                with transaction.atomic():
                    nueva_observacion = ObservacionCompromiso.objects.create(
                        id_compromiso=compromiso,
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

    context = {
        'total': total_actividades,
        'finalizadas': finalizadas,
        'en_proceso': en_proceso,
        'pendientes': pendientes,
    }
    return render(request, 'coordinador/dashboard_coordinador.html', context)


@login_required
@role_required('Coordinador')
def listar_todas_actividades(request):
    query = request.GET.get('q')
    estado_filtro = request.GET.get('estado')
    
    actividades = Actividad.objects.all().order_by('-fecha_registro')

    if query:
        actividades = actividades.filter(
            Q(codigo_unico__icontains=query) |
            Q(solicitud_problema__icontains=query)
        ).distinct()
        
    if estado_filtro:
        actividades = actividades.filter(estado_progreso=estado_filtro)

    context = {
        'actividades': actividades,
        'query': query,
        'estado_filtro': estado_filtro,
    }

    return render(request, 'coordinador/listar_todas.html', context)