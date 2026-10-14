from django.shortcuts import render
from .models import Compromiso, ObservacionCompromiso
# Create your views here.

def agenda(request):
    compromisos = Compromiso.objects.all()
    observaciones = ObservacionCompromiso.objects.all()
    context = {
        'compromisos': compromisos,
        'observaciones': observaciones,
    }
    return render(request, 'administrador/lista_tubo.html', context)
