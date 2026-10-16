from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages

def login_view(request):
    if request.user.is_authenticated:
        return redirect('inicio') 

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
                try:
                    nombre_cargo = user.profesional.id_cargo.nombre_cargo.upper()
                    
                    if 'DELEGADO' in nombre_cargo:
                        return redirect('monitoreoApp:dashboard_delegado')
                        
                    elif 'ADMINISTRADOR' in nombre_cargo:
                        return redirect('administracionApp:dashboard_admin') 
                        
                    elif 'COORDINADOR' in nombre_cargo:
                        return redirect('tuboApp:dashboard_coordinador') 
                    else:
                        return redirect('lista_actividades') 
                        
                except AttributeError:
                    return redirect('inicio')
            else:
                messages.error(request, 'Esta cuenta se encuentra desactivada por auditoría.')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')
    return render(request, 'login/login.html')