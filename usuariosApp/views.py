from django.http import request
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from administracionApp.models import Profesional
import re
from django.urls import reverse

def login_view(request):
    # 1. Si ya tiene sesión activa, lo redirigimos
    if request.user.is_authenticated:
        return redirect('administracionApp:dashboard_admin') 

    # 2. Si el usuario intenta iniciar sesión
    if request.method == 'POST':
        usuario = request.POST.get('username')
        contrasena = request.POST.get('password')
        
        if not usuario or not contrasena:
            messages.warning(request, 'Por favor, ingresa tu usuario y tu contraseña.')
            return render(request, 'login/login.html')

        user = authenticate(request, username=usuario, password=contrasena)

        if user is not None:
            if user.is_active:
                login(request, user)
                
                # Leemos los roles del usuario directamente de sus Grupos en Django
                roles = [grupo.name.upper() for grupo in user.groups.all()]
                
                # Evaluamos hacia dónde redirigir según el ROL o si es superusuario
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
                messages.error(request, 'Esta cuenta se encuentra desactivada por auditoría.')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')
            
    # 3. LA LÍNEA CLAVE: Si entra por primera vez (GET), le mostramos el formulario
    return render(request, 'login/login.html')

def logout_view(request):
    logout(request)
    return redirect('usuariosApp:login')


from administracionApp.models import Profesional, FotoPerfil # <-- Importamos la nueva tabla
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import re


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