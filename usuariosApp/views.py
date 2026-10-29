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
from .forms import RecuperarClaveForm, RestablecerClaveForm

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
            
            roles = [grupo.name.upper() for grupo in user.groups.all()]
            
            if user.is_superuser or any('ADMINISTRADOR' in rol for rol in roles):
                return redirect('administracionApp:dashboard_admin')  
            elif any('DELEGADO' in rol for rol in roles):
                return redirect('monitoreoApp:dashboard_delegado')  
            elif any('COORDINADOR' in rol for rol in roles):
                return redirect('tuboApp:dashboard_coordinador')
            elif any('PROFESIONAL' in rol for rol in roles):
                return redirect('actividadApp:dashboard_profesional')
            else:
                return redirect('lista_actividades') 
                
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
            messages.success(request, 'Tu contraseña fue restablecida con éxito. Ya puedes iniciar sesión.')
            return redirect('usuariosApp:login')
    else:
        form = RestablecerClaveForm(usuario)

    return render(request, 'login/restablecer_clave.html', {'token_valido': True, 'form': form})
