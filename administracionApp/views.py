from django.shortcuts import render
from django.db.models import Q
from administracionApp.models import Delegacion, Profesional, Cargo, CatalagoServicio, CatalagoItem, CatalagoAreaApoyo, Vecino, FotoPerfil, Periodo, Auditoria
# --- IMPORTAMOS CatalogoTipoGestion ---
from actividadApp.models import Actividad, CatalogoTipoGestion
from administracionApp.forms import ProfesionalForm, UsuarioSeguridadForm, DelegacionForm, CargoForm, VecinoForm, PeriodoForm
from actividadApp.forms import ActividadForm
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from usuariosApp.decorators import role_required
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
import secrets
import string
from django.urls import reverse
from tuboApp.models import Compromiso
from datetime import date, datetime

import json
from django.forms.models import model_to_dict

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

@role_required('Administrador')
@login_required
def dashboard_admin(request):
    return render(request, 'administrador/dashboard_admin.html')

def generar_clave_segura(longitud=10):
    alfabeto = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alfabeto) for _ in range(longitud))

@role_required('Administrador')
@login_required
def lista_actividades(request):
    query = request.GET.get('q')
    actividades = Actividad.objects.all().order_by('-fecha_registro')
    
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
                            fecha_comprometida=date.today(),
                            id_funcionario=funcionario_asignado,
                            estado_progreso='INGRESADO'
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
                                'fecha_comprometida': date.today(),
                                'id_funcionario': funcionario_asignado,
                                'estado_progreso': 'INGRESADO'
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
                        f'Usuario: {email} | Clave temporal: [{clave_temporal}]'
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

@role_required('Administrador')
@login_required
def lista_cargos(request):
    query = request.GET.get('q')
    cargos = Cargo.objects.all()
    
    if query:
        cargos = cargos.filter(nombre__icontains=query).distinct()
        
    return render(request, 'administrador/cargos/lista_cargos.html', {
        'cargos': cargos,
        'query': query
    })

@role_required('Administrador')
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

@role_required('Administrador')
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

@role_required('Administrador')
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
@role_required('Administrador')
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

@role_required('Administrador')
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
            try:
                with transaction.atomic():
                    periodo = form.save(commit=False)
                    periodo.estado = True
                    if not periodo.version_parametros:
                        periodo.version_parametros = 1
                    periodo.save()
                    
                    # AUDITORIA
                    registrar_auditoria(request, "CREACION", "Periodo", periodo)
                    
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
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(periodo)
        form = PeriodoForm(request.POST, instance=periodo)
        if form.is_valid():
            try:
                periodo_guardado = form.save()
                
                # AUDITORIA
                registrar_auditoria(request, "EDICION", "Periodo", periodo_guardado, datos_antiguos)
                
                messages.success(request, f'El periodo "{periodo.nombre}" fue actualizado.')
                return redirect('administracionApp:lista_periodos')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
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
        
        with transaction.atomic():
            datos_antiguos = model_to_dict(periodo)
            nuevo_estado = not periodo.estado
            periodo.estado = nuevo_estado
            periodo.save()
            
            # AUDITORIA
            registrar_auditoria(request, "CAMBIO_ESTADO", "Periodo", periodo, datos_antiguos)
                
        accion = "activado" if nuevo_estado else "desactivado"
        messages.success(request, f'El periodo "{periodo.nombre}" fue {accion}.')
        
    return redirect('administracionApp:lista_periodos')

@role_required('Administrador', 'Coordinador')
@login_required
def versionar_periodo(request, id_periodo):
    periodo_original = get_object_or_404(Periodo, id_periodo=id_periodo)
    try:
        with transaction.atomic():
            nueva_version = Periodo.objects.get(id_periodo=id_periodo)
            nueva_version.pk = None
            nueva_version.version_parametros += 1
            nueva_version.nombre = f"{periodo_original.nombre} (v{nueva_version.version_parametros})"
            nueva_version.estado = True
            nueva_version.save()
            
            # AUDITORIA
            registrar_auditoria(request, "NUEVA_VERSION", "Periodo", nueva_version)
            
            messages.success(request, f'Se generó la versión {nueva_version.version_parametros}. Por favor ajusta las nuevas fechas o umbrales y guarda los cambios.')
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
    query = request.GET.get('q', '')
    registros = Auditoria.objects.select_related('funcionario_id_funcionario').order_by('-fecha')
    
    if query:
        registros = registros.filter(
            Q(evento__icontains=query) | 
            Q(entidad__icontains=query) |
            Q(funcionario_id_funcionario__nombres__icontains=query) |
            Q(funcionario_id_funcionario__apellido_paterno__icontains=query)
        )
        
    return render(request, 'administrador/auditoria/lista_auditoria.html', {
        'registros': registros,
        'query': query
    })