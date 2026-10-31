from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import logout

def role_required(*role_names):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            # 1. Si ni siquiera está logueado, lo mandamos al login
            if not request.user.is_authenticated:
                return redirect('usuariosApp:login')
            
            # Aplanar la lista por si los roles se pasan como ['Rol1', 'Rol2'] o separados por coma
            roles_permitidos = []
            for rol in role_names:
                if isinstance(rol, list):
                    roles_permitidos.extend(rol)
                else:
                    roles_permitidos.append(rol)
                    
            # 2. Si es SUPERUSUARIO o TIENE alguno de los roles permitidos, pasa
            if request.user.is_superuser or request.user.groups.filter(name__in=roles_permitidos).exists():
                return view_func(request, *args, **kwargs)
                
            # 3. Cierre de puerta estricto: Si está logueado pero NO TIENE EL ROL.
            logout(request)
            roles_str = " o ".join(roles_permitidos)
            messages.error(request, f'No tienes permisos de {roles_str} para acceder a esta sección.')
            return redirect('usuariosApp:login') 
            
        return wrapper
    return decorator