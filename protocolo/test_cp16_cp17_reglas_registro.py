from datetime import timedelta
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.utils.timezone import localdate

from config.utils import validar_cierre_semanal, validar_datos_vecino_actividad
from protocolo.base import CasoProtocolo


def rechaza(funcion, *args):
    try:
        funcion(*args)
        return False
    except ValidationError:
        return True


class CasoCP16(CasoProtocolo):
    codigo = 'CP-16'
    nombre = 'Cierre semanal'

    def test_protocolo(self):
        hoy = localdate()
        lunes = hoy - timedelta(days=7 if hoy.weekday() == 0 else hoy.weekday())
        self.verificar('Acepta una gestión de hoy', not rechaza(validar_cierre_semanal, hoy))
        self.verificar(f'Acepta el lunes de la semana abierta ({lunes:%d-%m-%Y})', not rechaza(validar_cierre_semanal, lunes))
        anterior = lunes - timedelta(days=1)
        self.verificar(f'Rechaza el día anterior a la semana abierta ({anterior:%d-%m-%Y})', rechaza(validar_cierre_semanal, anterior))
        self.finalizar()


class CasoCP17(CasoProtocolo):
    codigo = 'CP-17'
    nombre = 'Datos del vecino obligatorios'

    def test_protocolo(self):
        self.verificar('Sin vecino solicitante: rechazado', rechaza(validar_datos_vecino_actividad, None))
        self.verificar('Vecino sin nombre: rechazado',
                       rechaza(validar_datos_vecino_actividad, SimpleNamespace(nombres='', telefono='912345678')))
        self.verificar('Vecino sin teléfono: rechazado',
                       rechaza(validar_datos_vecino_actividad, SimpleNamespace(nombres='Ana', telefono='')))
        self.verificar('Vecino con nombre y teléfono: aceptado',
                       not rechaza(validar_datos_vecino_actividad, SimpleNamespace(nombres='Ana', telefono='912345678')))
        self.finalizar()
