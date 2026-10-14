from django.shortcuts import render

from administracionApp.models import Delegacion, Profesional

# Create your views here.

def delegaciones(request):
    lista_delegaciones = Delegacion.objects.all()
    context = {
        'delegaciones': lista_delegaciones
    }
    return render(request, 'administrador/lista_delegaciones.html', context)

def main(request):
    return render(request, 'main.html')

def inicio(request):
    return render(request, 'administrador/dashboard_admin.html')

def directorio_profesional(request):
    lista_profesionales = Profesional.objects.all()
    return render(request, 'administrador/lista_profesionales.html', {'profesionales': lista_profesionales})