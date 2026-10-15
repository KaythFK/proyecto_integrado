from django.shortcuts import render
from django.db.models import Q  # Importante para la barra de búsqueda
from administracionApp.models import Delegacion, Profesional
from actividadApp.models import Actividad 


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
    query = request.GET.get('q')
    profesionales = Profesional.objects.filter(estado=True)
    if query:
        profesionales = profesionales.filter(
            Q(rut__icontains=query) |
            Q(nombres__icontains=query) |
            Q(apellido_paterno__icontains=query) |
            Q(correo__icontains=query)
        ).distinct()
    return render(request, 'administrador/lista_profesionales.html', {
        'profesionales': profesionales,
        'query': query
    })


def lista_actividades(request):
    query = request.GET.get('q')
    actividades = Actividad.objects.filter(estado=True).order_by('-fecha')
    if query:
        actividades = actividades.filter(
            Q(codigo_unico__icontains=query) |
            Q(solicitud_problema__icontains=query)
        ).distinct()
    context = {
        'actividades': actividades,
        'query': query,
    }
    
    return render(request, 'administrador/lista_actividades.html', context)