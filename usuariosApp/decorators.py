from django.shortcuts import redirect
from django.contrib import messages

def role_required(role_name):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            # 1. Si ni siquiera está logueado, lo mandamos al login
            if not request.user.is_authenticated:
                return redirect('login')
                
            # 2. Si está logueado y TIENE el rol, lo dejamos pasar
            if request.user.groups.filter(name=role_name).exists():
                return view_func(request, *args, **kwargs)
                
            # 3. Si está logueado pero NO TIENE EL ROL:
            # NO LO MANDES AL LOGIN. Mándalo a una vista pública o de error.
            messages.error(request, 'No tienes permisos para acceder a esta sección.')
            # Cambia 'administracionApp:inicio' por la ruta de tu vista sin restricciones
            return redirect('administracionApp:inicio') 
            
        return wrapper
    return decorator