from django.shortcuts import render
from django.db.models import Q
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
    lista_profesionales = Profesional.objects.all()

    if query:
        lista_profesionales = lista_profesionales.filter(
            Q(rut__icontains=query) |
            Q(nombres__icontains=query) |
            Q(apellido_paterno__icontains=query) |
            Q(correo__icontains=query)
        ).distinct()
        
    return render(request, 'administrador/lista_profesionales.html', {
        'profesionales': lista_profesionales,
        'query': query
    })


def listar_actividades_admin(request):
    query = request.GET.get('q')
    actividades = Actividad.objects.all().order_by('-fecha')
    if query:
        actividades = actividades.filter(
            Q(codigo_unico__icontains=query) |
            Q(solicitud_problema__icontains=query) 
        ).distinct()
        
    return render(request, 'administrador/lista_actividades.html', {
        'actividades': actividades,
        'query': query
    })
