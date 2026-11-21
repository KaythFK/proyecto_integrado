from django.shortcuts import render
from django.db.models import Q, Max
from django.core.paginator import Paginator
from .filters import AuditoriaFilter
from usuariosApp.models import ClaveTemporal
from administracionApp.models import Delegacion, Profesional, Cargo, CatalagoServicio, CatalagoItem, CatalagoAreaApoyo, Vecino, FotoPerfil, Periodo, Auditoria, CargoItem
# --- IMPORTAMOS CatalogoTipoGestion ---
from actividadApp.models import Actividad, CatalogoTipoGestion
from administracionApp.forms import ProfesionalForm, UsuarioSeguridadForm, DelegacionForm, CargoForm, VecinoForm, PeriodoForm
from actividadApp.forms import ActividadForm
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from config.utils import verificar_periodo_activo
from usuariosApp.decorators import role_required
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
import secrets
import string
from django.urls import reverse
from tuboApp.models import Compromiso
from datetime import date, datetime, timedelta
from django.core.exceptions import ValidationError
# Importamos las validaciones desde tu utils.py
from config.utils import (
    verificar_periodo_activo, 
    validar_vigencia_fecha_actual, 
    validar_suma_ponderaciones, 
)
import json
import re
from django.forms.models import model_to_dict
from decimal import Decimal, InvalidOperation
# --- FUNCIÓN AUXILIAR DE AUDITORÍA ---
def registrar_auditoria(request, evento, entidad, objeto_instancia, datos_anteriores=None):
    """
    Función centralizada para registrar auditoría.
    """
    try:
        profesional_actual = Profesional.objects.filter(usuario=request.user).first()
        identificador = getattr(objeto_instancia, 'pk', 0)
        
        # Extraemos los datos nuevos
        diccionario_nuevo = model_to_dict(objeto_instancia)
        datos_nuevos_limpios = {k: str(v) for k, v in diccionario_nuevo.items()}
        
        # ¡EL TRUCO! Guardamos el nombre legible del objeto (ej: "Juan Pérez" o "ACT-2026")
        datos_nuevos_limpios['descripcion_legible'] = str(objeto_instancia)
        
        datos_anteriores_limpios = None
        if datos_anteriores:
            datos_anteriores_limpios = {k: str(v) for k, v in datos_anteriores.items()}
            datos_anteriores_limpios['descripcion_legible'] = str(objeto_instancia)

        Auditoria.objects.create(
            evento=evento,
            entidad=entidad,
            identificador=identificador,
            valor_anterior=datos_anteriores_limpios, # Django lo convierte a JSON automáticamente
            valor_nuevo=datos_nuevos_limpios,
            funcionario_id_funcionario=profesional_actual
        )
    except Exception as e:
        print(f"Error interno registrando auditoría: {e}")
# ---------------------------------------

def main(request):
    return render(request, 'main.html')

SECCIONES_PANEL_ADMIN = [
    ('Personas y estructura', [
        ('Profesionales', 'Usuarios, roles y delegación', 'people', 'administracionApp:directorio_profesional'),
        ('Cargos', 'Funciones y vigencia', 'person-badge', 'administracionApp:lista_cargos'),
        ('Delegaciones', 'Unidades territoriales', 'building', 'administracionApp:delegaciones'),
        ('Vecinos', 'Personas atendidas', 'person-vcard', 'administracionApp:lista_vecinos'),
    ]),
    ('Operación', [
        ('Actividades', 'Registro de intervenciones', 'clipboard-check', 'administracionApp:admin-actividades'),
        ('Gestiones', 'Acciones por actividad', 'list-task', 'actividadApp:lista_todas_gestiones'),
        ('Tubo', 'Compromisos y estados', 'kanban', 'tuboApp:tubo'),
        ('Evidencias', 'Respaldos fotográficos', 'camera', 'actividadApp:lista_evidencias'),
        ('Validaciones', 'Revisión de evidencias', 'patch-check', 'actividadApp:lista_validaciones'),
    ]),
    ('Medición', [
        ('Metas', 'Objetivos por cargo', 'bullseye', 'monitoreoApp:listar_metas'),
        ('Indicadores', 'Avance y semáforo', 'bar-chart-line', 'monitoreoApp:lista_indicadores'),
        ('Tendencias', 'Cumplimiento histórico por cargo', 'graph-up-arrow', 'monitoreoApp:tendencias_cargo'),
        ('Períodos', 'Fechas y umbrales', 'calendar-range', 'administracionApp:lista_periodos'),
        ('Ausencias', 'Licencias y permisos', 'calendar-x', 'actividadApp:lista_ausencias'),
    ]),
    ('Comunidad', [
        ('Organizaciones', 'Juntas y agrupaciones', 'house-heart', 'comunidadApp:lista_organizaciones'),
        ('Afiliaciones', 'Vecinos por organización', 'person-plus', 'comunidadApp:lista_afiliaciones'),
        ('Cargas', 'Cargas familiares', 'diagram-3', 'comunidadApp:lista_cargas'),
        ('Vínculos', 'Relaciones familiares', 'link-45deg', 'comunidadApp:lista_vinculos'),
        ('Retroalimentaciones', 'Felicitaciones y reclamos', 'chat-heart', 'actividadApp:lista_retroalimentaciones'),
    ]),
    ('Configuración', [
        ('Catálogos', 'Ítems, servicios y tipos', 'journal-text', 'administracionApp:panel_catalogos'),
    ]),
]


@role_required('Administrador')
@login_required
def dashboard_admin(request):
    secciones = [
        {'titulo': titulo, 'accesos': [
            {'texto': texto, 'detalle': detalle, 'icono': icono, 'url': reverse(nombre_url)}
            for texto, detalle, icono, nombre_url in accesos
        ]}
        for titulo, accesos in SECCIONES_PANEL_ADMIN
    ]
    return render(request, 'administrador/dashboard_admin.html', {'secciones': secciones})

def generar_clave_segura(longitud=10):
    alfabeto = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alfabeto) for _ in range(longitud))

@role_required('Administrador')
@login_required
def lista_actividades(request):
    query = request.GET.get('q')
    actividades = Actividad.objects.all().prefetch_related('gestiones__tipo_gestion').order_by('-fecha_registro')
    
    if query:
        actividades = actividades.filter(
            Q(codigo_unico__icontains=query) |
            Q(solicitud_problema__icontains=query)
        ).distinct()
        
    context = {
        'actividades': actividades,
        'query': query,
    }
    return render(request, 'administrador/actividades/lista_actividades.html', context)

@role_required('Administrador')
@login_required
def crear_actividad(request):
    if request.method == 'POST':
        form = ActividadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    actividad = form.save(commit=False)
                    actividad.estado = True
                    
                    if not actividad.codigo_unico:
                        actividad.codigo_unico = f"ACT-{datetime.now().year}-{secrets.token_hex(3).upper()}"
                        
                    actividad.save()
                    
                    # AUDITORIA
                    registrar_auditoria(request, "CREACION", "Actividad", actividad)
                    
                    if actividad.en_tubo:
                        funcionario_asignado = request.user.profesional if hasattr(request.user, 'profesional') else Profesional.objects.first()
                        
                        Compromiso.objects.create(
                            id_actividad=actividad,
                            territorio='Por definir',
                            fecha_comprometida=actividad.fecha_comprometida or date.today() + timedelta(days=7),
                            id_funcionario=funcionario_asignado,
                            estado_progreso='INGRESADO',
                            organizacion=actividad.id_organizacion  # el compromiso exige organización
                        )
                        messages.success(request, f'La actividad {actividad.codigo_unico} fue registrada y derivada al Tubo de Compromisos.')
                    else:
                        messages.success(request, f'La actividad {actividad.codigo_unico} fue registrada con éxito en el sistema.')
                        
                return redirect('administracionApp:admin-actividades')
            except Exception as e:
                messages.error(request, f'Error al procesar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores marcados en el formulario.')
    else:
        form = ActividadForm()
        
    return render(request, 'administrador/actividades/form_actividades.html', {
        'form': form,
        'titulo': 'Registrar Nueva Actividad'
    })


@role_required('Administrador')
@login_required
def editar_actividad(request, id_actividad):
    actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(actividad)
        form = ActividadForm(request.POST, request.FILES, instance=actividad)
        if form.is_valid():
            try:
                with transaction.atomic():
                    actividad = form.save()
                    
                    # AUDITORIA
                    registrar_auditoria(request, "EDICION", "Actividad", actividad, datos_antiguos)
                    
                    if actividad.en_tubo:
                        funcionario_asignado = request.user.profesional if hasattr(request.user, 'profesional') else Profesional.objects.first()
                        
                        Compromiso.objects.get_or_create(
                            id_actividad=actividad,
                            defaults={
                                'territorio': 'Por definir',
                                'fecha_comprometida': actividad.fecha_comprometida or date.today() + timedelta(days=7),
                                'id_funcionario': funcionario_asignado,
                                'estado_progreso': 'INGRESADO',
                                'organizacion': actividad.id_organizacion
                            }
                        )
                        messages.success(request, f'La actividad {actividad.codigo_unico} fue actualizada y asegurada en el Tubo.')
                    else:
                        messages.success(request, f'La actividad {actividad.codigo_unico} fue actualizada correctamente.')

                return redirect('administracionApp:admin-actividades')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = ActividadForm(instance=actividad)
        
    return render(request, 'administrador/actividades/form_actividades.html', {
        'form': form,
        'titulo': f'Editar Actividad {actividad.codigo_unico}'
    })

@role_required('Administrador')
@login_required
def desactivar_actividad(request, id_actividad):
    if request.method == 'POST':
        actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
        
        with transaction.atomic():
            datos_antiguos = model_to_dict(actividad)
            nuevo_estado = not actividad.estado
            actividad.estado = nuevo_estado
            actividad.save()
            
            # AUDITORIA
            registrar_auditoria(request, "CAMBIO_ESTADO", "Actividad", actividad, datos_antiguos)
                
        accion = "habilitada" if nuevo_estado else "deshabilitada"
        messages.success(request, f'La actividad {actividad.codigo_unico} fue {accion}.')
        
    return redirect('administracionApp:admin-actividades')

@role_required('Administrador')
@login_required
def directorio_profesional(request):
    query = request.GET.get('q')
    profesionales = Profesional.objects.all().select_related('usuario', 'id_cargo', 'id_delegacion')
    
    if query:
        profesionales = profesionales.filter(
            Q(rut__icontains=query) |
            Q(nombres__icontains=query) |
            Q(apellido_paterno__icontains=query) |
            Q(correo__icontains=query)
        ).distinct()
        
    return render(request, 'administrador/profesional/lista_profesionales.html', {
        'profesionales': profesionales,
        'query': query
    })

@role_required('Administrador')
@login_required
def crear_profesional(request):
    if request.method == 'POST':
        form_usuario = UsuarioSeguridadForm(request.POST)
        form_profesional = ProfesionalForm(request.POST)
        
        if form_usuario.is_valid() and form_profesional.is_valid():
            try:
                with transaction.atomic():
                    email = form_usuario.cleaned_data['email'].lower().strip()
                    grupo_seleccionado = form_usuario.cleaned_data['rol']
                    
                    clave_temporal = generar_clave_segura(10)
                    nuevo_usuario = User.objects.create_user(
                        username=email,
                        email=email,
                        password=clave_temporal
                    )
                    
                    nuevo_usuario.groups.add(grupo_seleccionado)
                    ClaveTemporal.objects.update_or_create(usuario=nuevo_usuario)
                    
                    profesional = form_profesional.save(commit=False)
                    profesional.usuario = nuevo_usuario
                    profesional.correo = email
                    profesional.estado = True
                    profesional.save()
                    
                    # AUDITORIA
                    registrar_auditoria(request, "CREACION", "Profesional", profesional)
                    
                    foto_archivo = request.FILES.get('foto_perfil')
                    if foto_archivo:
                        FotoPerfil.objects.create(usuario=nuevo_usuario, foto=foto_archivo)
                    
                    messages.success(
                        request, 
                        f'Profesional {profesional.nombres} creado con rol "{grupo_seleccionado.name}". '
                        f'Usuario: {email} | Clave temporal: [{clave_temporal}]. Deberá cambiarla en su primer ingreso.'
                    )
                    return redirect('administracionApp:directorio_profesional')
            except Exception as e:
                messages.error(request, f'Error al guardar en la base de datos: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores marcados en el formulario.')
    else:
        form_usuario = UsuarioSeguridadForm()
        form_profesional = ProfesionalForm()
        
    return render(request, 'administrador/profesional/form_profesional.html', {
        'form_usuario': form_usuario,
        'form_profesional': form_profesional,
        'titulo': 'Registrar Nuevo Profesional'
    })


@role_required('Administrador')
@login_required
def editar_profesional(request, id_profesional):
    profesional = get_object_or_404(Profesional, id_profesional=id_profesional)
    usuario_asociado = profesional.usuario

    if request.method == 'POST':
        datos_antiguos = model_to_dict(profesional)
        form_usuario = UsuarioSeguridadForm(request.POST, instance=usuario_asociado)
        form_profesional = ProfesionalForm(request.POST, instance=profesional)
        
        if form_usuario.is_valid() and form_profesional.is_valid():
            try:
                with transaction.atomic():
                    email = form_usuario.cleaned_data['email'].lower().strip()
                    nuevo_grupo = form_usuario.cleaned_data['rol']
                    
                    if not usuario_asociado:
                        clave_temporal = generar_clave_segura(10)
                        usuario_asociado = User.objects.create_user(
                            username=email,
                            email=email,
                            password=clave_temporal
                        )
                        profesional.usuario = usuario_asociado
                        ClaveTemporal.objects.update_or_create(usuario=usuario_asociado)
                    else:
                        usuario_asociado.username = email
                        usuario_asociado.email = email
                        usuario_asociado.save()
                    
                    usuario_asociado.groups.clear()
                    usuario_asociado.groups.add(nuevo_grupo)
                    
                    prof_actualizado = form_profesional.save(commit=False)
                    prof_actualizado.correo = email
                    prof_actualizado.save()
                    
                    # AUDITORIA
                    registrar_auditoria(request, "EDICION", "Profesional", prof_actualizado, datos_antiguos)
                    
                    foto_archivo = request.FILES.get('foto_perfil')
                    if foto_archivo:
                        perfil_foto, creado = FotoPerfil.objects.get_or_create(usuario=usuario_asociado)
                        perfil_foto.foto = foto_archivo
                        perfil_foto.save()
                    
                    messages.success(request, f'Datos y permisos de {profesional.nombres} actualizados correctamente.')
                    return redirect('administracionApp:directorio_profesional')
            except Exception as e:
                messages.error(request, f'Error al actualizar los datos: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        initial_user = {'email': profesional.correo} if not usuario_asociado else None
        form_usuario = UsuarioSeguridadForm(instance=usuario_asociado, initial=initial_user)
        form_profesional = ProfesionalForm(instance=profesional)
        
    return render(request, 'administrador/profesional/form_profesional.html', {
        'form_usuario': form_usuario,
        'form_profesional': form_profesional,
        'titulo': 'Editar Profesional y Permisos'
    })

@role_required('Administrador')
@login_required
def cambiar_estado_profesional(request, id_profesional):
    if request.method == 'POST':
        profesional = get_object_or_404(Profesional, id_profesional=id_profesional)
        
        with transaction.atomic():
            datos_antiguos = model_to_dict(profesional)
            nuevo_estado = not profesional.estado
            profesional.estado = nuevo_estado
            profesional.save()
            
            # AUDITORIA
            registrar_auditoria(request, "CAMBIO_ESTADO", "Profesional", profesional, datos_antiguos)
            
            if profesional.usuario:
                profesional.usuario.is_active = nuevo_estado
                profesional.usuario.save()
                
        accion = "activado y con acceso al sistema" if nuevo_estado else "desactivado y bloqueado"
        messages.success(request, f'El profesional {profesional.nombres} fue {accion}.')
        
    return redirect('administracionApp:directorio_profesional')

def obtener_url_retorno(user):
    if user.groups.filter(name='Administrador').exists():
        return 'administracionApp:dashboard_admin'
    elif user.groups.filter(name='Coordinador').exists():
        return 'tuboApp:dashboard_coordinador'
    else:
        return 'monitoreoApp:dashboard_delegado'


@login_required
@role_required('Administrador', 'Coordinador')
def delegaciones(request):
    query = request.GET.get('q')
    lista_delegaciones = Delegacion.objects.all().order_by('-id_delegacion')

    if query:
        lista_delegaciones = lista_delegaciones.filter(
            Q(nombre__icontains=query) |
            Q(territorio__icontains=query)
        ).distinct()

    context = {
        'delegaciones': lista_delegaciones,
        'query': query,
        'url_retorno': obtener_url_retorno(request.user),
    }
    return render(request, 'administrador/delegaciones/lista_delegaciones.html', context)

@login_required
@role_required('Administrador', 'Coordinador')
def crear_delegacion(request):
    if request.method == 'POST':
        form = DelegacionForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    delegacion = form.save(commit=False)
                    delegacion.estado = True
                    delegacion.save()
                    
                    # AUDITORIA
                    registrar_auditoria(request, "CREACION", "Delegacion", delegacion)
                    
                messages.success(request, 'La delegación se ha registrado correctamente.')
                return redirect('administracionApp:delegaciones')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Corrige los errores del formulario.')
    else:
        form = DelegacionForm()
        
    context = {
        'form': form, 
        'titulo': 'Registrar Nueva Delegación',
        'url_retorno': obtener_url_retorno(request.user),
    }
    return render(request, 'administrador/delegaciones/form_delegaciones.html', context)

@login_required
@role_required('Administrador', 'Coordinador')
def editar_delegacion(request, id_delegacion):
    delegacion = get_object_or_404(Delegacion, id_delegacion=id_delegacion)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(delegacion)
        form = DelegacionForm(request.POST, instance=delegacion)
        if form.is_valid():
            try:
                with transaction.atomic():
                    delegacion_guardada = form.save()
                    
                    # AUDITORIA
                    registrar_auditoria(request, "EDICION", "Delegacion", delegacion_guardada, datos_antiguos)
                    
                messages.success(request, 'La delegación se ha actualizado correctamente.')
                return redirect('administracionApp:delegaciones')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = DelegacionForm(instance=delegacion)
        
    context = {
        'form': form, 
        'titulo': 'Editar Delegación',
        'url_retorno': obtener_url_retorno(request.user),
    }
    return render(request, 'administrador/delegaciones/form_delegaciones.html', context)

@login_required
@role_required('Administrador', 'Coordinador')
def cambiar_estado_delegacion(request, id_delegacion):
    if request.method == 'POST':
        delegacion = get_object_or_404(Delegacion, id_delegacion=id_delegacion)
        try:
            with transaction.atomic():
                datos_antiguos = model_to_dict(delegacion)
                nuevo_estado = not delegacion.estado
                delegacion.estado = nuevo_estado
                delegacion.save()
                
                # AUDITORIA
                registrar_auditoria(request, "CAMBIO_ESTADO", "Delegacion", delegacion, datos_antiguos)
                
                accion = "habilitada" if nuevo_estado else "inhabilitada"
                messages.success(request, f'La delegación {delegacion.nombre} fue {accion} correctamente.')
        except Exception as e:
            messages.error(request, f'Error al cambiar el estado: {str(e)}')
            
    return redirect('administracionApp:delegaciones')

@role_required('Administrador', 'Coordinador')
@login_required
def lista_cargos(request):
    query = request.GET.get('q')
    # Añadimos prefetch_related para traer los ítems de la matriz de forma eficiente sin saturar la base de datos
    cargos = Cargo.objects.prefetch_related('cargoitem_set__id_item').all()
    
    if query:
        cargos = cargos.filter(nombre__icontains=query).distinct()
        
    return render(request, 'administrador/cargos/lista_cargos.html', {
        'cargos': cargos,
        'query': query
    })

@role_required('Administrador', 'Coordinador')
@login_required
def crear_cargo(request):
    if request.method == 'POST':
        form = CargoForm(request.POST)
        if form.is_valid():
            try:
                cargo = form.save(commit=False)
                cargo.estado = True
                cargo.save()
                
                # AUDITORIA
                registrar_auditoria(request, "CREACION", "Cargo", cargo)
                
                messages.success(request, f'El cargo "{cargo.nombre}" fue registrado con éxito.')
                return redirect('administracionApp:lista_cargos')
            except Exception as e:
                messages.error(request, f'Error al guardar en base de datos: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = CargoForm()
        
    return render(request, 'administrador/cargos/form_cargos.html', {
        'form': form,
        'titulo': 'Registrar Nuevo Cargo'
    })

@role_required('Administrador', 'Coordinador')
@login_required    
def editar_cargo(request, id_cargo):
    cargo = get_object_or_404(Cargo, id_cargo=id_cargo)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(cargo)
        form = CargoForm(request.POST, instance=cargo)
        if form.is_valid():
            try:
                cargo_guardado = form.save()
                
                # AUDITORIA
                registrar_auditoria(request, "EDICION", "Cargo", cargo_guardado, datos_antiguos)
                
                messages.success(request, f'El cargo "{cargo.nombre}" fue actualizado.')
                return redirect('administracionApp:lista_cargos')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = CargoForm(instance=cargo)
        
    return render(request, 'administrador/cargos/form_cargos.html', {
        'form': form,
        'titulo': 'Editar Cargo'
    })

@role_required('Administrador', 'Coordinador')
@login_required
def cambiar_estado_cargo(request, id_cargo):
    if request.method == 'POST':
        cargo = get_object_or_404(Cargo, id_cargo=id_cargo)
        
        with transaction.atomic():
            datos_antiguos = model_to_dict(cargo)
            nuevo_estado = not cargo.estado
            cargo.estado = nuevo_estado
            cargo.save()
            
            # AUDITORIA
            registrar_auditoria(request, "CAMBIO_ESTADO", "Cargo", cargo, datos_antiguos)
                
        accion = "activado" if nuevo_estado else "desactivado"
        messages.success(request, f'El cargo "{cargo.nombre}" fue {accion}.')
        
    return redirect('administracionApp:lista_cargos')

# --- MODIFICADO: AÑADIDO CATALOGOTIPOGESTION ---
@role_required('Administrador', 'Coordinador')
@login_required
def panel_catalogos(request):
    tab_activa = request.GET.get('tab', 'servicio')
    
    context = {
        'servicios': CatalagoServicio.objects.all(),
        'items': CatalagoItem.objects.all(),
        'areas': CatalagoAreaApoyo.objects.all(),
        # --- NUEVO ---
        'gestiones': CatalogoTipoGestion.objects.all(),
        'tab_activa': tab_activa
    }
    return render(request, 'administrador/catalogos/panel_catalogos.html', context)

@role_required('Administrador', 'Coordinador')
@login_required
def gestionar_catalogo(request):
    
    if request.method == 'POST':
        accion = request.POST.get('accion')
        tipo = request.POST.get('tipo')
        id_obj = request.POST.get('id_obj')
        nombre = request.POST.get('nombre')
        
        # --- NUEVO: Capturamos el correo (puede venir vacío si es otro catálogo) ---
        correo = request.POST.get('correo')
        
        modelos = {
            'servicio': CatalagoServicio,
            'item': CatalagoItem,
            'area': CatalagoAreaApoyo,
            'gestion': CatalogoTipoGestion
        }
        
        ModeloActivo = modelos.get(tipo)
        
        if ModeloActivo:
            try:
                with transaction.atomic():
                    if accion == 'crear':
                        if ModeloActivo.objects.filter(nombre__iexact=nombre).exists():
                            messages.error(request, f'Error: Ya existe un registro llamado "{nombre}".')
                        else:
                            nuevo_registro = ModeloActivo(nombre=nombre, estado=True)
                            
                            # Si es un área de apoyo, le asignamos el correo antes de guardar
                            if tipo == 'area' and correo is not None:
                                nuevo_registro.correo = correo
                                
                            nuevo_registro.full_clean() 
                            nuevo_registro.save()
                            
                            # AUDITORIA
                            registrar_auditoria(request, "CREACION", tipo.capitalize(), nuevo_registro)
                            
                            messages.success(request, 'Registro creado con éxito.')

                    elif accion == 'editar':
                        obj = ModeloActivo.objects.get(pk=id_obj)
                        if ModeloActivo.objects.filter(nombre__iexact=nombre).exclude(pk=id_obj).exists():
                            messages.error(request, f'Error: No puedes renombrarlo a "{nombre}" porque ya existe otro igual.')
                        else:
                            datos_antiguos = model_to_dict(obj)
                            obj.nombre = nombre
                            
                            # Si es un área de apoyo, actualizamos su correo
                            if tipo == 'area' and correo is not None:
                                obj.correo = correo
                                
                            obj.full_clean() 
                            obj.save()
                            
                            # AUDITORIA
                            registrar_auditoria(request, "EDICION", tipo.capitalize(), obj, datos_antiguos)
                            
                            messages.success(request, 'Registro actualizado correctamente.')

                    elif accion == 'estado':
                        obj = ModeloActivo.objects.get(pk=id_obj)
                        datos_antiguos = model_to_dict(obj)
                        obj.estado = not obj.estado
                        obj.save()
                        
                        # AUDITORIA
                        registrar_auditoria(request, "CAMBIO_ESTADO", tipo.capitalize(), obj, datos_antiguos)
                        
                        txt = "activado" if obj.estado else "desactivado"
                        messages.success(request, f'El registro fue {txt}.')

            except Exception as e:
                messages.error(request, f'Error de validación: {str(e)}')
                
        base_url = reverse('administracionApp:panel_catalogos')
        return redirect(f"{base_url}?tab={tipo}")
        
    return redirect('administracionApp:panel_catalogos')


@role_required('Administrador', 'Coordinador')
@login_required
def lista_periodos(request):
    query = request.GET.get('q')
    periodos = Periodo.objects.all().order_by('-fecha_inicio')
    
    if query:
        periodos = periodos.filter(nombre__icontains=query).distinct()
        
    return render(request, 'administrador/periodos/lista_periodos.html', {
        'periodos': periodos,
        'query': query,
        'url_retorno': obtener_url_retorno(request.user)
    })

@role_required('Administrador', 'Coordinador')
@login_required
def crear_periodo(request):
    if request.method == 'POST':
        form = PeriodoForm(request.POST)
        if form.is_valid():
            periodo = None
            try:
                with transaction.atomic():
                    periodo = form.save(commit=False)
                    periodo.estado = True
                    if not periodo.version_parametros:
                        periodo.version_parametros = 1
                    periodo.save()

                    # AUDITORIA
                    registrar_auditoria(request, "CREACION", "Periodo", periodo)

                # KAN-414 (CA2): Inicializar ítems vigentes una vez guardado el período
                if periodo and periodo.esta_abierto:
                    try:
                        from monitoreoApp.services import inicializar_items_vigentes_periodo
                        inicializar_items_vigentes_periodo(periodo)
                    except Exception as err_init:
                        print(f"Aviso al inicializar ítems del período: {err_init}")

                messages.success(request, f'El periodo "{periodo.nombre}" fue registrado con éxito.')
                return redirect('administracionApp:lista_periodos')
            except Exception as e:
                messages.error(request, f'Error al guardar en base de datos: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = PeriodoForm(initial={'version_parametros': 1})

    return render(request, 'administrador/periodos/form_periodo.html', {
        'form': form,
        'titulo': 'Registrar Nuevo Periodo',
        'url_retorno': obtener_url_retorno(request.user)
    })


@role_required('Administrador', 'Coordinador')
@login_required
def editar_periodo(request, id_periodo):
    periodo = get_object_or_404(Periodo, id_periodo=id_periodo)

    if not periodo.estado:
        messages.error(request, f'El periodo "{periodo.nombre}" está cerrado. Reábrelo antes de editarlo.')
        return redirect('administracionApp:lista_periodos')
    estaba_vencido = periodo.cerrado_por_fecha

    if request.method == 'POST':
        datos_antiguos = model_to_dict(periodo)
        form = PeriodoForm(request.POST, instance=periodo)
        if form.is_valid():
            periodo_guardado = None
            try:
                with transaction.atomic():
                    periodo_guardado = form.save()

                    # AUDITORIA
                    evento = "REAPERTURA" if estaba_vencido and not periodo_guardado.cerrado_por_fecha else "EDICION"
                    registrar_auditoria(request, evento, "Periodo", periodo_guardado, datos_antiguos)

                if periodo_guardado and periodo_guardado.esta_abierto:
                    try:
                        from monitoreoApp.services import inicializar_items_vigentes_periodo
                        inicializar_items_vigentes_periodo(periodo_guardado)
                    except Exception as err_init:
                        print(f"Aviso al sincronizar ítems del período: {err_init}")

                messages.success(request, f'El periodo "{periodo_guardado.nombre}" fue actualizado.')
                return redirect('administracionApp:lista_periodos')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = PeriodoForm(instance=periodo)

    return render(request, 'administrador/periodos/form_periodo.html', {
        'form': form,
        'titulo': f'Editar Periodo v{periodo.version_parametros}',
        'url_retorno': obtener_url_retorno(request.user)
    })


@role_required('Administrador', 'Coordinador')
@login_required
def cambiar_estado_periodo(request, id_periodo):
    if request.method == 'POST':
        periodo = get_object_or_404(Periodo, id_periodo=id_periodo)
        nuevo_estado = False

        with transaction.atomic():
            datos_antiguos = model_to_dict(periodo)
            nuevo_estado = not periodo.estado
            periodo.estado = nuevo_estado
            periodo.save()

            # AUDITORIA
            registrar_auditoria(request, "REAPERTURA" if nuevo_estado else "CIERRE", "Periodo", periodo, datos_antiguos)

        if nuevo_estado and periodo.esta_abierto:
            try:
                from monitoreoApp.services import inicializar_items_vigentes_periodo
                inicializar_items_vigentes_periodo(periodo)
            except Exception as err_init:
                print(f"Aviso al inicializar ítems al reabrir período: {err_init}")

        accion = "reabierto" if nuevo_estado else "cerrado"
        messages.success(request, f'El periodo "{periodo.nombre}" fue {accion}.')
        if nuevo_estado and periodo.cerrado_por_fecha:
            messages.warning(request, f'Su fecha de término ya pasó: sigue cerrado hasta que se extienda en "Editar".')

    return redirect('administracionApp:lista_periodos')


SUFIJO_VERSION = re.compile(r'\s*\(v\d+\)$')


@role_required('Administrador', 'Coordinador')
@login_required
def versionar_periodo(request, id_periodo):
    periodo_original = get_object_or_404(Periodo, id_periodo=id_periodo)
    nombre_base = SUFIJO_VERSION.sub('', periodo_original.nombre)
    familia = Periodo.objects.filter(
        Q(nombre__iexact=nombre_base) | Q(nombre__iregex=r'^' + re.escape(nombre_base) + r' \(v[0-9]+\)$')
    )
    version = max(familia.aggregate(m=Max('version_parametros'))['m'] or 1, periodo_original.version_parametros or 1) + 1
    while Periodo.objects.filter(nombre__iexact=f"{nombre_base} (v{version})").exists():
        version += 1
    nombre_nuevo = f"{nombre_base} (v{version})"
    if len(nombre_nuevo) > Periodo._meta.get_field('nombre').max_length:
        messages.error(request, f'No se pudo versionar: el nombre "{nombre_nuevo}" supera el largo permitido.')
        return redirect('administracionApp:lista_periodos')

    try:
        with transaction.atomic():
            nueva_version = Periodo.objects.get(id_periodo=id_periodo)
            nueva_version.pk = None
            nueva_version.version_parametros = version
            nueva_version.nombre = nombre_nuevo
            nueva_version.estado = True
            nueva_version.save()

            registrar_auditoria(request, "NUEVA_VERSION", "Periodo", nueva_version)

        if nueva_version.esta_abierto:
            try:
                with transaction.atomic():
                    from monitoreoApp.services import inicializar_items_vigentes_periodo
                    inicializar_items_vigentes_periodo(nueva_version)
            except Exception as e_init:
                print(f"Error al inicializar ítems en nueva versión: {e_init}")

        messages.success(
            request,
            f'Se generó la versión {nueva_version.version_parametros}. Por favor ajusta las nuevas fechas o umbrales y guarda los cambios.'
        )
        return redirect('administracionApp:editar_periodo', id_periodo=nueva_version.id_periodo)

    except Exception as e:
        messages.error(request, f'Error al crear nueva versión: {str(e)}')

    return redirect('administracionApp:lista_periodos')


@role_required('Administrador')
@login_required
def lista_vecinos(request):
    query = request.GET.get('q')
    vecinos = Vecino.objects.all().order_by('nombres')
    
    if query:
        vecinos = vecinos.filter(
            Q(nombres__icontains=query) | 
            Q(apellido_paterno__icontains=query) |
            Q(rut__icontains=query)
        ).distinct()
        
    return render(request, 'administrador/vecinos/lista_vecinos.html', {
        'vecinos': vecinos,
        'query': query
    })

@role_required('Administrador')
@login_required
def crear_vecino(request):
    if request.method == 'POST':
        form = VecinoForm(request.POST)
        if form.is_valid():
            try:
                vecino = form.save(commit=False)
                vecino.estado = True
                vecino.save()
                
                # AUDITORIA
                registrar_auditoria(request, "CREACION", "Vecino", vecino)
                
                messages.success(request, f'El vecino "{vecino.nombres} {vecino.apellido_paterno}" fue registrado con éxito.')
                return redirect('administracionApp:lista_vecinos')
            except Exception as e:
                messages.error(request, f'Error al guardar en base de datos: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = VecinoForm()
        
    return render(request, 'administrador/vecinos/form_vecino.html', {
        'form': form,
        'titulo': 'Registrar Nuevo Vecino'
    })

@role_required('Administrador')
@login_required
def editar_vecino(request, id_vecino):
    vecino = get_object_or_404(Vecino, id_vecino=id_vecino)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(vecino)
        form = VecinoForm(request.POST, instance=vecino)
        if form.is_valid():
            try:
                vecino_guardado = form.save()
                
                # AUDITORIA
                registrar_auditoria(request, "EDICION", "Vecino", vecino_guardado, datos_antiguos)
                
                messages.success(request, f'Los datos de "{vecino.nombres}" fueron actualizados.')
                return redirect('administracionApp:lista_vecinos')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = VecinoForm(instance=vecino)
        
    return render(request, 'administrador/vecinos/form_vecino.html', {
        'form': form,
        'titulo': 'Editar Información del Vecino'
    })

@role_required('Administrador')
@login_required
def cambiar_estado_vecino(request, id_vecino):
    if request.method == 'POST':
        vecino = get_object_or_404(Vecino, id_vecino=id_vecino)
        
        with transaction.atomic():
            datos_antiguos = model_to_dict(vecino)
            nuevo_estado = not vecino.estado
            vecino.estado = nuevo_estado
            vecino.save()
            
            # AUDITORIA
            registrar_auditoria(request, "CAMBIO_ESTADO", "Vecino", vecino, datos_antiguos)
                
        accion = "habilitado" if nuevo_estado else "inhabilitado"
        messages.success(request, f'El registro de "{vecino.nombres} {vecino.apellido_paterno}" fue {accion}.')
        
    return redirect('administracionApp:lista_vecinos')

@login_required
@role_required('Administrador')
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
            
            # AUDITORIA
            registrar_auditoria(request, "CAMBIO_PROGRESO", "Actividad", actividad, datos_antiguos)
            
            messages.success(request, f'La actividad {actividad.codigo_unico} cambió su estado a: {actividad.get_estado_progreso_display()}')
        else:
            messages.error(request, 'Error: El estado seleccionado no es válido.')
            
    return redirect(request.META.get('HTTP_REFERER', '/'))


@login_required
@role_required('Administrador') 
def lista_auditoria(request):
    registros = Auditoria.objects.select_related('funcionario_id_funcionario').order_by('-fecha', '-id_auditoria')
    filtro = AuditoriaFilter(request.GET, queryset=registros)
    resultado = filtro.qs if filtro.is_valid() else registros.none()
    pagina = Paginator(resultado, 50).get_page(request.GET.get('page'))
    parametros = request.GET.copy()
    parametros.pop('page', None)

    return render(request, 'administrador/auditoria/lista_auditoria.html', {
        'filtro': filtro,
        'registros': pagina,
        'pagina': pagina,
        'parametros': parametros.urlencode(),
    })



@login_required
def configurar_matriz_cargo(request, pk):
    cargo = get_object_or_404(Cargo, pk=pk)

    if request.method == 'POST':
        # 1. Capturar fechas de vigencia del cargo
        fecha_inicio = request.POST.get('fecha_inicio')
        fecha_termino = request.POST.get('fecha_termino') or None

        datos_items = []
        lista_ponderaciones_str = []

        for key, value in request.POST.items():
            if key.startswith('ponderacion_'):
                item_id = key.split('_')[1]
                lista_ponderaciones_str.append(value)
                datos_items.append((item_id, value))

        try:
            # 2. Validación centralizada de ponderaciones usando utils.py
            validar_suma_ponderaciones(lista_ponderaciones_str)

            # --- CAPTURAR DATOS ANTERIORES PARA AUDITORÍA ---
            datos_antiguos = model_to_dict(cargo)

            # 3. Guardar fechas de vigencia del cargo
            cargo.fecha_inicio = fecha_inicio
            cargo.fecha_termino = fecha_termino
            cargo.save()

            # 4. Actualizar la matriz de ítems
            CargoItem.objects.filter(id_cargo=cargo).delete()
            for item_id, p in datos_items:
                item_catalogo = CatalagoItem.objects.get(pk=item_id)
                CargoItem.objects.create(
                    id_cargo=cargo,
                    id_item=item_catalogo,
                    ponderacion=p,
                    estado=True
                )

            # 5. Auditoría centralizada con los parámetros correctos
            registrar_auditoria(request, "EDICION", "Cargo", cargo, datos_antiguos)

            from monitoreoApp.services import asegurar_indicadores_profesional
            hoy = date.today()
            vigente_hoy = (
                (not cargo.fecha_inicio or cargo.fecha_inicio <= hoy)
                and (not cargo.fecha_termino or cargo.fecha_termino >= hoy)
            )

            if vigente_hoy:
                for prof in Profesional.objects.filter(id_cargo=cargo, estado=True):
                    asegurar_indicadores_profesional(prof, fecha_referencia=hoy)
                messages.success(
                    request,
                    f"Matriz y vigencia del cargo '{cargo.nombre}' configuradas y aplicadas desde hoy ({hoy.strftime('%d/%m/%Y')}) en períodos abiertos."
                )
            else:
                fecha_txt = cargo.fecha_inicio.strftime('%d/%m/%Y') if cargo.fecha_inicio else 'la fecha indicada'
                messages.success(
                    request,
                    f"Matriz y vigencia del cargo '{cargo.nombre}' guardadas. Regirán desde el {fecha_txt} sin modificar períodos cerrados."
                )
            return redirect('administracionApp:lista_cargos')

        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else list(e.messages)[0]
            messages.error(request, error_msg)

    # Preparar datos usando .pk para evitar cualquier error de atributo en CatalagoItem
    items_activos = CatalagoItem.objects.filter(estado=True)
    asignaciones_actuales = {ci.id_item_id: ci.ponderacion for ci in cargo.cargoitem_set.filter(estado=True)}

    items_con_ponderacion = []
    for item in items_activos:
        items_con_ponderacion.append({
            'id': item.pk,
            'nombre': item.nombre,
            'descripcion': getattr(item, 'descripcion', ''),
            'ponderacion': asignaciones_actuales.get(item.pk, '')
        })

    context = {
        'cargo': cargo,
        'items_con_ponderacion': items_con_ponderacion,
    }
    return render(request, 'coordinador/configurar_cargos.html', context)