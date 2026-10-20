from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import logout

def role_required(role_name):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            # 1. Si ni siquiera está logueado, lo mandamos al login
            if not request.user.is_authenticated:
                return redirect('usuariosApp:login')
                
            # 2. Si es SUPERUSUARIO o TIENE el rol (sin importar mayúsculas/minúsculas), pasa
            if request.user.is_superuser or request.user.groups.filter(name__iexact=role_name).exists():
                return view_func(request, *args, **kwargs)
                
            # 3. Cierre de puerta estricto: Si está logueado pero NO TIENE EL ROL.
            logout(request)
            messages.error(request, f'No tienes permisos de {role_name} para acceder a esta sección.')
            return redirect('usuariosApp:login') 
            
        return wrapper
    return decorator