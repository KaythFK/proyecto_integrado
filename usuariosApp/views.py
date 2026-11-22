from django.http import request
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from administracionApp.models import Profesional
import re
from django.urls import reverse
from django.contrib.auth.models import User
from administracionApp.models import Profesional, FotoPerfil 
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import re
import os
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.db.models import Q
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from .correo import enviar_correo
from django.db import transaction
from django.forms.models import model_to_dict
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from .decorators import role_required
from .forms import CambioClaveInicialForm, RecuperarClaveForm, RestablecerClaveForm, RolForm
from .models import ClaveTemporal, RolSistema, asegurar_roles_base, asignar_rol


def destino_segun_rol(user):
    roles = set(user.groups.values_list('name', flat=True))
    if user.is_superuser or 'Administrador' in roles:
        return 'administracionApp:dashboard_admin'
    if 'Delegado' in roles:
        return 'monitoreoApp:dashboard_delegado'
    if 'Coordinador' in roles:
        return 'tuboApp:dashboard_coordinador'
    if 'Profesional' in roles:
        return 'actividadApp:dashboard_profesional'
    return 'usuariosApp:mi_perfil'


@login_required
def cambiar_clave_inicial(request):
    usuario = request.user
    pendiente = ClaveTemporal.objects.filter(usuario=usuario)
    if not pendiente.exists():
        return redirect(destino_segun_rol(usuario))

    if request.method == 'POST':
        form = CambioClaveInicialForm(usuario, request.POST)
        if form.is_valid():
            form.save()
            pendiente.delete()
            update_session_auth_hash(request, usuario)
            profesional = Profesional.objects.filter(usuario=usuario).first()
            if profesional:
                from administracionApp.models import Auditoria
                Auditoria.objects.create(evento='CAMBIO_CLAVE_INICIAL', entidad='Usuario', identificador=usuario.pk,
                                         valor_nuevo={'descripcion_legible': f'{usuario.get_username()} reemplazó su contraseña temporal'},
                                         funcionario_id_funcionario=profesional)
            messages.success(request, 'Tu contraseña fue actualizada. Ya puedes usar el sistema.')
            return redirect(destino_segun_rol(usuario))
    else:
        form = CambioClaveInicialForm(usuario)

    return render(request, 'login/cambiar_clave_inicial.html', {'form': form})

def login_view(request):
    
    if request.user.is_authenticated:
        return redirect('administracionApp:dashboard_admin') 


    if request.method == 'POST':
        usuario = request.POST.get('username')
        contrasena = request.POST.get('password')
        
        if not usuario or not contrasena:
            messages.warning(request, 'Por favor, ingresa tu usuario y tu contraseña.')
            return render(request, 'login/login.html')

        user = authenticate(request, username=usuario, password=contrasena)
        
        if user is not None:
            login(request, user)
            if ClaveTemporal.objects.filter(usuario=user).exists():
                return redirect('usuariosApp:cambiar_clave_inicial')
            return redirect(destino_segun_rol(user))
                
        else:
            try:
                usuario_db = User.objects.get(username=usuario)
                
                if not usuario_db.is_active and usuario_db.check_password(contrasena):
                    messages.error(request, 'Esta cuenta se encuentra desactivada por auditoría.')
                else:
                    messages.error(request, 'Usuario o contraseña incorrectos.')
                    
            except User.DoesNotExist:
                messages.error(request, 'Usuario o contraseña incorrectos.')
                
    return render(request, 'login/login.html')

def logout_view(request):
    list(messages.get_messages(request))
    logout(request)
    return redirect('usuariosApp:login')


@login_required
def mi_perfil(request):
    # 1. Buscar datos del profesional
    try:
        profesional = Profesional.objects.get(usuario=request.user)
    except Profesional.DoesNotExist:
        profesional = None

    if request.method == 'POST':
        # ACCIÓN A: EL USUARIO ESTÁ SUBIENDO UNA FOTO
        if 'nueva_foto' in request.FILES:
            perfil_foto, creado = FotoPerfil.objects.get_or_create(usuario=request.user)
            perfil_foto.foto = request.FILES['nueva_foto']
            perfil_foto.save()
            messages.success(request, 'Tu foto de perfil ha sido actualizada.')
            return redirect('usuariosApp:mi_perfil')

        if 'eliminar_foto' in request.POST:
            perfil_foto = FotoPerfil.objects.filter(usuario=request.user).first()
            if perfil_foto is not None:
                if perfil_foto.foto and perfil_foto.foto.name != FotoPerfil._meta.get_field('foto').default:
                    perfil_foto.foto.delete(save=False)
                perfil_foto.delete()
                messages.success(request, 'Tu foto de perfil fue eliminada.')
            return redirect('usuariosApp:mi_perfil')

        # ACCIÓN B: EL USUARIO ESTÁ CAMBIANDO SU CONTRASEÑA
        nueva_clave = request.POST.get('nueva_clave')
        confirmar_clave = request.POST.get('confirmar_clave')
        
        if nueva_clave and confirmar_clave:
            if nueva_clave != confirmar_clave:
                messages.error(request, 'Las contraseñas no coinciden.')
            elif len(nueva_clave) < 8 or not any(c.isupper() for c in nueva_clave) or not re.search(r"[!@#$%^&*(),.?\":{}|<>]", nueva_clave):
                messages.error(request, 'La contraseña no cumple con los requisitos.')
            else:
                user = request.user
                user.set_password(nueva_clave)
                user.save()
                ClaveTemporal.objects.filter(usuario=user).delete()
                update_session_auth_hash(request, user)
                messages.success(request, 'Tu contraseña ha sido actualizada con éxito.')
                return redirect('usuariosApp:mi_perfil') 

    # 2. Lógica dinámica para el botón de "Volver"
    url_retorno = '/' 
    if request.user.groups.filter(name='Administrador').exists():
        url_retorno = reverse('administracionApp:dashboard_admin')
    elif request.user.groups.filter(name='Profesional').exists():
        url_retorno = reverse('actividadApp:dashboard_profesional')
    elif request.user.groups.filter(name='Delegado').exists():
        url_retorno = reverse('monitoreoApp:dashboard_delegado')  # Ajusta el nombre de la app/ruta si es distinto
    elif request.user.groups.filter(name='Coordinador').exists():
        url_retorno = reverse('tuboApp:dashboard_coordinador')

    # 3. Rescatar la URL de la foto de forma segura
    foto_url = None
    if hasattr(request.user, 'foto_perfil') and request.user.foto_perfil.foto:
        foto_url = request.user.foto_perfil.foto.url

    return render(request, 'mi_perfil.html', {
        'profesional': profesional,
        'foto_url': foto_url,
        'url_retorno': url_retorno  
    })

# ==========================================
# RECUPERACIÓN DE CONTRASEÑA (TOKEN + PHPMAILER)
# ==========================================

def recuperar_clave(request):
    enviado = False

    if request.method == 'POST':
        form = RecuperarClaveForm(request.POST)
        if form.is_valid():
            correo = form.cleaned_data['correo']
            usuario = User.objects.filter(
                Q(email__iexact=correo) | Q(username__iexact=correo), is_active=True
            ).first()

            # Si el correo no existe mostramos el mismo mensaje, para no revelar qué cuentas existen
            if usuario is not None:
                uidb64 = urlsafe_base64_encode(force_bytes(usuario.pk))
                token = default_token_generator.make_token(usuario)
                ruta = reverse('usuariosApp:restablecer_clave', args=[uidb64, token])

                # SITIO_URL permite fijar el dominio/IP pública de AWS si el servidor está detrás de un proxy
                sitio_url = os.getenv('SITIO_URL')
                enlace = sitio_url.rstrip('/') + ruta if sitio_url else request.build_absolute_uri(ruta)

                if not enviar_correo(usuario.email or usuario.username, enlace):
                    messages.error(request, 'No se pudo enviar el correo. Intenta nuevamente más tarde.')
                    return render(request, 'login/recuperar_clave.html', {'form': form, 'enviado': False})

            enviado = True
    else:
        form = RecuperarClaveForm()

    return render(request, 'login/recuperar_clave.html', {'form': form, 'enviado': enviado})


def restablecer_clave(request, uidb64, token):
    # 1. Recuperar el usuario a partir del identificador del enlace
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        usuario = User.objects.get(pk=uid, is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        usuario = None

    # 2. Validar el token (expira y deja de servir apenas se cambia la contraseña)
    if usuario is None or not default_token_generator.check_token(usuario, token):
        return render(request, 'login/restablecer_clave.html', {'token_valido': False})

    # 3. Establecer la nueva contraseña
    if request.method == 'POST':
        form = RestablecerClaveForm(usuario, request.POST)
        if form.is_valid():
            form.save()
            ClaveTemporal.objects.filter(usuario=usuario).delete()
            messages.success(request, 'Tu contraseña fue restablecida con éxito. Ya puedes iniciar sesión.')
            return redirect('usuariosApp:login')
    else:
        form = RestablecerClaveForm(usuario)

    return render(request, 'login/restablecer_clave.html', {'token_valido': True, 'form': form})


# --- ROLES DEL SISTEMA ---
def accesos_de_perfil(perfil):
    """Lo que ve en su menú un usuario con ese perfil base."""
    from config.menu import MENU_POR_ROL
    if perfil == 'Administrador':
        return ['Acceso completo al sistema']
    accesos = []
    for texto, _, destino in MENU_POR_ROL.get(perfil.lower(), []):
        if isinstance(destino, list):
            accesos += [hijo for hijo, _, _ in destino]
        elif texto != 'Mis alertas':
            accesos.append(texto)
    return accesos


def usuarios_del_rol(rol):
    usuarios = User.objects.filter(groups=rol.grupo)
    if rol.es_base:
        usuarios = usuarios.exclude(groups__rol_sistema__es_base=False)
    return usuarios.select_related('profesional__id_delegacion', 'profesional__id_cargo').distinct().order_by('first_name', 'username')


def auditar_rol(request, evento, rol, datos_anteriores=None):
    from administracionApp.views import registrar_auditoria
    registrar_auditoria(request, evento, 'RolSistema', rol, datos_anteriores)


def datos_de_rol(rol):
    datos = model_to_dict(rol)
    datos['nombre'] = rol.grupo.name
    return datos


@login_required
@role_required('Administrador')
def lista_roles(request):
    asegurar_roles_base()
    roles = []
    for rol in RolSistema.objects.select_related('grupo').order_by('-es_base', 'grupo__name'):
        usuarios = usuarios_del_rol(rol)
        rol.accesos = accesos_de_perfil(rol.perfil_base)
        rol.total_usuarios = usuarios.count()
        rol.usuarios_activos = usuarios.filter(is_active=True).count()
        roles.append(rol)
    return render(request, 'administrador/roles/lista_roles.html', {'roles': roles})


@login_required
@role_required('Administrador')
def crear_rol(request):
    form = RolForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            with transaction.atomic():
                rol = form.save()
                auditar_rol(request, 'CREACION', rol)
            messages.success(request, f'El rol "{rol.nombre}" fue creado con los accesos del perfil {rol.perfil_base}.')
            return redirect('usuariosApp:lista_roles')
        messages.error(request, 'Por favor corrige los errores en el formulario.')
    return render(request, 'administrador/roles/form_rol.html', {'form': form, 'titulo': 'Registrar Rol'})


@login_required
@role_required('Administrador')
def editar_rol(request, id_rol):
    rol = get_object_or_404(RolSistema.objects.select_related('grupo'), pk=id_rol)
    datos_anteriores = datos_de_rol(rol)
    perfil_anterior = rol.perfil_base
    form = RolForm(request.POST or None, instance=rol)
    if request.method == 'POST':
        if form.is_valid():
            with transaction.atomic():
                rol = form.save()
                if rol.perfil_base != perfil_anterior:
                    for usuario in usuarios_del_rol(rol):
                        asignar_rol(usuario, rol.grupo)
                auditar_rol(request, 'EDICION', rol, datos_anteriores)
            messages.success(request, f'El rol "{rol.nombre}" fue actualizado correctamente.')
            return redirect('usuariosApp:lista_roles')
        messages.error(request, 'Por favor corrige los errores en el formulario.')
    return render(request, 'administrador/roles/form_rol.html', {
        'form': form,
        'titulo': f'Editar Rol: {rol.nombre}',
        'rol': rol,
        'accesos': accesos_de_perfil(rol.perfil_base),
        'usuarios': usuarios_del_rol(rol),
    })


@login_required
@role_required('Administrador')
@require_POST
def cambiar_estado_rol(request, id_rol):
    rol = get_object_or_404(RolSistema.objects.select_related('grupo'), pk=id_rol)
    if rol.es_base:
        messages.error(request, 'Los perfiles base del sistema no se pueden desactivar.')
        return redirect('usuariosApp:lista_roles')
    activos = usuarios_del_rol(rol).filter(is_active=True).count()
    if rol.estado and activos:
        messages.error(request, f'No se puede desactivar "{rol.nombre}": tiene {activos} usuario{"s" if activos != 1 else ""} activo{"s" if activos != 1 else ""}. Reasígnalos a otro rol primero.')
        return redirect('usuariosApp:lista_roles')
    datos_anteriores = datos_de_rol(rol)
    rol.estado = not rol.estado
    rol.save(update_fields=['estado'])
    auditar_rol(request, 'CAMBIO_ESTADO', rol, datos_anteriores)
    messages.success(request, f'El rol "{rol.nombre}" fue {"activado" if rol.estado else "desactivado"} correctamente.')
    return redirect('usuariosApp:lista_roles')
