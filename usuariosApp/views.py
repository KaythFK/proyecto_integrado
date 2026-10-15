from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages

def login_view(request):
    if request.user.is_authenticated:
        return redirect('inicio') 

    if request.method == 'POST':
        usuario = request.POST.get('username')
        contrasena = request.POST.get('password')

        user = authenticate(request, username=usuario, password=contrasena)

        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect('inicio')
            else:
                messages.error(request, 'Esta cuenta se encuentra desactivada por auditoría.')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'login/login.html')