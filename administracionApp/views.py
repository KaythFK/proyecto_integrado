from django.shortcuts import render
from django.db.models import Q  # Importante para la barra de búsqueda
from administracionApp.models import Delegacion, Profesional, Cargo, CatalagoServicio, CatalagoItem, CatalagoAreaApoyo, Vecino, FotoPerfil, Periodo
from actividadApp.models import Actividad
from administracionApp.forms import ProfesionalForm, UsuarioSeguridadForm, DelegacionForm, CargoForm, VecinoForm
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
    # .all() permite al administrador ver tanto las habilitadas como deshabilitadas
    actividades = Actividad.objects.all().order_by('-fecha')
    
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
        # Se incluye request.FILES por si el formulario maneja subida de evidencias
        form = ActividadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                actividad = form.save(commit=False)
                actividad.estado = True
                actividad.save()
                messages.success(request, 'La actividad fue registrada con éxito en el sistema.')
                return redirect('administracionApp:actividades') # Ajusta el namespace si es necesario
            except Exception as e:
                messages.error(request, f'Error al guardar en base de datos: {str(e)}')
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
        form = ActividadForm(request.POST, request.FILES, instance=actividad)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f'La actividad {actividad.codigo_unico} fue actualizada correctamente.')
                return redirect('administracionApp:actividades')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = ActividadForm(instance=actividad)
        
    return render(request, 'administrador/actividades/form_actividad.html', {
        'form': form,
        'titulo': f'Editar Actividad {actividad.codigo_unico}'
    })

@role_required('Administrador')
@login_required
def desactivar_actividad(request, id_actividad):
    if request.method == 'POST':
        actividad = get_object_or_404(Actividad, id_actividad=id_actividad)
        
        with transaction.atomic():
            nuevo_estado = not actividad.estado
            actividad.estado = nuevo_estado
            actividad.save()
                
        accion = "habilitada" if nuevo_estado else "deshabilitada"
        messages.success(request, f'La actividad {actividad.codigo_unico} fue {accion}.')
        
    # Cambia 'administracionApp:actividades' según tu configuración de urls.py
    return redirect('administracionApp:actividades')

@role_required('Administrador')
@login_required
def directorio_profesional(request):
    query = request.GET.get('q')
    
    # Se llama "profesionales"
    profesionales = Profesional.objects.all().select_related('usuario', 'id_cargo', 'id_delegacion')
    
    if query:
        # Reemplazamos "lista_profesionales" por "profesionales" para filtrar sobre la misma variable
        profesionales = profesionales.filter(
            Q(rut__icontains=query) |
            Q(nombres__icontains=query) |
            Q(apellido_paterno__icontains=query) |
            Q(correo__icontains=query)
        ).distinct()
        
    return render(request, 'administrador/profesional/lista_profesionales.html', {
        'profesionales': profesionales, # Así el HTML recibe la lista filtrada correctamente
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
                    # Forzamos el correo a minúsculas y sin espacios
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
                    
                    # --- NUEVO CÓDIGO PARA LA FOTO ---
                    foto_archivo = request.FILES.get('foto_perfil')
                    if foto_archivo:
                        FotoPerfil.objects.create(usuario=nuevo_usuario, foto=foto_archivo)
                    # ---------------------------------
                    
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
                    
                    # --- NUEVO CÓDIGO PARA LA FOTO ---
                    foto_archivo = request.FILES.get('foto_perfil')
                    if foto_archivo:
                        # get_or_create previene errores si el profesional antiguo no tenía tabla de foto
                        perfil_foto, creado = FotoPerfil.objects.get_or_create(usuario=usuario_asociado)
                        perfil_foto.foto = foto_archivo
                        perfil_foto.save()
                    # ---------------------------------
                    
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
            # Invertimos el estado actual (Si es True pasa a False, si es False pasa a True)
            nuevo_estado = not profesional.estado
            profesional.estado = nuevo_estado
            profesional.save()
            
            # Replicamos el estado en el acceso al sistema
            if profesional.usuario:
                profesional.usuario.is_active = nuevo_estado
                profesional.usuario.save()
                
        accion = "activado y con acceso al sistema" if nuevo_estado else "desactivado y bloqueado"
        messages.success(request, f'El profesional {profesional.nombres} fue {accion}.')
        
    return redirect('administracionApp:directorio_profesional')

### VIEWS PARA DELEGACIONES ###
@role_required('Administrador')
@login_required
def delegaciones(request):
    query = request.GET.get('q')
    # Traemos todas, incluyendo las inactivas para el switch, y optimizamos la consulta del responsable
    lista_delegaciones = Delegacion.objects.all().select_related('responsable')
    
    if query:
        lista_delegaciones = lista_delegaciones.filter(
            Q(nombre__icontains=query) |
            Q(territorio__icontains=query) |
            Q(calle__icontains=query)
        ).distinct()
        
    return render(request, 'administrador/delegaciones/lista_delegaciones.html', {
        'delegaciones': lista_delegaciones,
        'query': query
    })

@role_required('Administrador')
@login_required
def crear_delegacion(request):
    if request.method == 'POST':
        form = DelegacionForm(request.POST)
        if form.is_valid():
            try:
                delegacion = form.save(commit=False)
                delegacion.estado = True
                delegacion.save()
                messages.success(request, f'La delegación "{delegacion.nombre}" fue registrada con éxito.')
                return redirect('administracionApp:delegaciones')
            except Exception as e:
                messages.error(request, f'Error al guardar en base de datos: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = DelegacionForm()
        
    return render(request, 'administrador/delegaciones/form_delegaciones.html', {
        'form': form,
        'titulo': 'Registrar Nueva Delegación'
    })

@role_required('Administrador')
@login_required
def editar_delegacion(request, id_delegacion):
    delegacion = get_object_or_404(Delegacion, id_delegacion=id_delegacion)
    
    if request.method == 'POST':
        form = DelegacionForm(request.POST, instance=delegacion)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f'La delegación "{delegacion.nombre}" fue actualizada.')
                return redirect('administracionApp:delegaciones')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = DelegacionForm(instance=delegacion)
        
    return render(request, 'administrador/delegaciones/form_delegacion.html', {
        'form': form,
        'titulo': 'Editar Delegación'
    })

@role_required('Administrador')
@login_required
def cambiar_estado_delegacion(request, id_delegacion):
    if request.method == 'POST':
        delegacion = get_object_or_404(Delegacion, id_delegacion=id_delegacion)
        
        with transaction.atomic():
            nuevo_estado = not delegacion.estado
            delegacion.estado = nuevo_estado
            delegacion.save()
                
        accion = "activada" if nuevo_estado else "desactivada"
        messages.success(request, f'La delegación "{delegacion.nombre}" fue {accion}.')
        
    return redirect('administracionApp:delegaciones')

# --- CRUD DE CARGOS ---

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
        form = CargoForm(request.POST, instance=cargo)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f'El cargo "{cargo.nombre}" fue actualizado.')
                return redirect('administracionApp:lista_cargos')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = CargoForm(instance=cargo)
        
    return render(request, 'administrador/cargos/form_cargo.html', {
        'form': form,
        'titulo': 'Editar Cargo'
    })

@role_required('Administrador')
@login_required
def cambiar_estado_cargo(request, id_cargo):
    if request.method == 'POST':
        cargo = get_object_or_404(Cargo, id_cargo=id_cargo)
        
        with transaction.atomic():
            nuevo_estado = not cargo.estado
            cargo.estado = nuevo_estado
            cargo.save()
                
        accion = "activado" if nuevo_estado else "desactivado"
        messages.success(request, f'El cargo "{cargo.nombre}" fue {accion}.')
        
    return redirect('administracionApp:lista_cargos')



# 1. Dibuja la pantalla y las tablas
@role_required('Administrador')
@login_required
def panel_catalogos(request):
    # La URL nos dirá en qué pestaña estábamos (ej: ?tab=item)
    tab_activa = request.GET.get('tab', 'servicio')
    
    context = {
        'servicios': CatalagoServicio.objects.all(),
        'items': CatalagoItem.objects.all(),
        'areas': CatalagoAreaApoyo.objects.all(),
        'tab_activa': tab_activa
    }
    return render(request, 'administrador/catalogos/panel_catalogos.html', context)

# 2. Recibe los datos del modal oculto y decide a qué tabla enviarlos
@role_required('Administrador')
@login_required
def gestionar_catalogo(request):
    if request.method == 'POST':
        accion = request.POST.get('accion')
        tipo = request.POST.get('tipo')
        id_obj = request.POST.get('id_obj')
        nombre = request.POST.get('nombre')
        
        modelos = {
            'servicio': CatalagoServicio,
            'item': CatalagoItem,
            'area': CatalagoAreaApoyo
        }
        
        ModeloActivo = modelos.get(tipo)
        
        if ModeloActivo:
            try:
                with transaction.atomic():
                    if accion == 'crear':
                        if ModeloActivo.objects.filter(nombre__iexact=nombre).exists():
                            messages.error(request, f'Error: Ya existe un registro llamado "{nombre}".')
                        else:
                            # 1. Se instancia sin guardar
                            nuevo_registro = ModeloActivo(nombre=nombre, estado=True)
                            
                            # 2. SE APLICA EL ARREGLO: full_clean() lee el max_length real de tu modelo y limpia el dato
                            nuevo_registro.full_clean() 
                            
                            # 3. Se guarda de forma segura
                            nuevo_registro.save()
                            messages.success(request, 'Registro creado con éxito.')

                    elif accion == 'editar':
                        obj = ModeloActivo.objects.get(pk=id_obj)
                        if ModeloActivo.objects.filter(nombre__iexact=nombre).exclude(pk=id_obj).exists():
                            messages.error(request, f'Error: No puedes renombrarlo a "{nombre}" porque ya existe otro igual.')
                        else:
                            obj.nombre = nombre
                            # SE APLICA EL ARREGLO TAMBIÉN EN LA EDICIÓN
                            obj.full_clean() 
                            obj.save()
                            messages.success(request, 'Registro actualizado correctamente.')

                    elif accion == 'estado':
                        obj = ModeloActivo.objects.get(pk=id_obj)
                        obj.estado = not obj.estado
                        obj.save()
                        txt = "activado" if obj.estado else "desactivado"
                        messages.success(request, f'El registro fue {txt}.')

            except Exception as e:
                # Si full_clean() detecta que el nombre es muy largo, arroja el error aquí pacíficamente
                messages.error(request, f'Error de validación: {str(e)}')
                
        # Retornos correctos para evitar el error "None"
        base_url = reverse('administracionApp:panel_catalogos')
        return redirect(f"{base_url}?tab={tipo}")
        
    return redirect('administracionApp:panel_catalogos')


from administracionApp.forms import PeriodoForm
from .models import Periodo

# --- CRUD DE PERIODOS ---

@role_required('Administrador')
@login_required
def lista_periodos(request):
    query = request.GET.get('q')
    periodos = Periodo.objects.all().order_by('-fecha_inicio')
    
    if query:
        periodos = periodos.filter(nombre__icontains=query).distinct()
        
    return render(request, 'administrador/periodos/lista_periodos.html', {
        'periodos': periodos,
        'query': query
    })

@role_required('Administrador')
@login_required
def crear_periodo(request):
    if request.method == 'POST':
        form = PeriodoForm(request.POST)
        if form.is_valid():
            try:
                periodo = form.save(commit=False)
                periodo.estado = True
                periodo.save()
                messages.success(request, f'El periodo "{periodo.nombre}" fue registrado con éxito.')
                return redirect('administracionApp:lista_periodos')
            except Exception as e:
                messages.error(request, f'Error al guardar en base de datos: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = PeriodoForm()
        
    return render(request, 'administrador/periodos/form_periodo.html', {
        'form': form,
        'titulo': 'Registrar Nuevo Periodo'
    })

@role_required('Administrador')
@login_required
def editar_periodo(request, id_periodo):
    periodo = get_object_or_404(Periodo, id_periodo=id_periodo)
    
    if request.method == 'POST':
        form = PeriodoForm(request.POST, instance=periodo)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f'El periodo "{periodo.nombre}" fue actualizado.')
                return redirect('administracionApp:lista_periodos')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = PeriodoForm(instance=periodo)
        
    return render(request, 'administrador/periodos/form_periodo.html', {
        'form': form,
        'titulo': 'Editar Periodo'
    })

@role_required('Administrador')
@login_required
def cambiar_estado_periodo(request, id_periodo):
    if request.method == 'POST':
        periodo = get_object_or_404(Periodo, id_periodo=id_periodo)
        
        with transaction.atomic():
            nuevo_estado = not periodo.estado
            periodo.estado = nuevo_estado
            periodo.save()
                
        accion = "activado" if nuevo_estado else "desactivado"
        messages.success(request, f'El periodo "{periodo.nombre}" fue {accion}.')
        
    return redirect('administracionApp:lista_periodos')



@role_required('Administrador')
@login_required
def lista_vecinos(request):
    query = request.GET.get('q')
    vecinos = Vecino.objects.all().order_by('nombres')
    
    if query:
        # Permite buscar por nombre, apellido paterno o RUT
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
        form = VecinoForm(request.POST, instance=vecino)
        if form.is_valid():
            try:
                form.save()
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
            nuevo_estado = not vecino.estado
            vecino.estado = nuevo_estado
            vecino.save()
                
        accion = "habilitado" if nuevo_estado else "inhabilitado"
        messages.success(request, f'El registro de "{vecino.nombres} {vecino.apellido_paterno}" fue {accion}.')
        
    return redirect('administracionApp:lista_vecinos')

