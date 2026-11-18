from decimal import Decimal
from django.core.exceptions import ObjectDoesNotExist

def calcular_indicadores_meta(avance_real, meta):
    """
    Calcula el cumplimiento, resultado ponderado y semáforo de una meta (KAN-205).
    Retorna un diccionario con los valores exactos para la vista o guardado.
    """
    avance_real = Decimal(str(avance_real))
    
    # Evitar división por cero en caso de configuraciones anómalas
    if meta.valor_objetivo == 0:
        return {
            'cumplimiento': Decimal('0.00'),
            'resultado_ponderado': Decimal('0.00'),
            'semaforo': 'ROJO'
        }

    # 1. Porcentaje de Cumplimiento (CA2)
    cumplimiento = (avance_real / meta.valor_objetivo) * Decimal('100.00')

    # 2. Resultado Ponderado según el peso de la meta (CA2)
    resultado_ponderado = (cumplimiento * meta.ponderador) / Decimal('100.00')

    # 3. Evaluación del Semáforo Institucional
    # Depende de los umbrales definidos en el Periodo asociado a la Meta
    periodo = meta.id_periodo
    semaforo = 'ROJO'
    
    if cumplimiento >= periodo.umbral_exelencia:
        semaforo = 'VERDE'
    elif cumplimiento >= periodo.umbral_regular:
        semaforo = 'AMARILLO'

    return {
        'cumplimiento': round(cumplimiento, 2),
        'resultado_ponderado': round(resultado_ponderado, 2),
        'semaforo': semaforo
    }