from datetime import date, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.utils import timezone

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



# --- ALERTAS (HU-31) ---
SEGUNDOS_ENTRE_REVISIONES = 300
PREFIJO_POR_TIPO = {'VENCIMIENTO': 'Compromiso', 'EVIDENCIA_PENDIENTE': 'Evidencia', 'AVANCE_BAJO': 'Avance'}


def tipo_de_alerta(alerta):
    for tipo, prefijo in PREFIJO_POR_TIPO.items():
        if alerta.motivo.startswith(prefijo):
            return tipo
    return ''


def numero(valor):
    return f'{valor:.2f}'.rstrip('0').rstrip('.')


def destinatarios_alerta(regla, delegacion):
    """Delegados de la delegación afectada y/o coordinadores, según la regla. Devuelve (profesional, rol)."""
    from administracionApp.models import Profesional
    resultado = []
    if regla.notificar_delegado and delegacion is not None:
        delegados = Profesional.objects.filter(estado=True, id_delegacion=delegacion, usuario__groups__name='Delegado').distinct()
        resultado += [(p, 'Delegado') for p in delegados]
    if regla.notificar_coordinador:
        ya_incluidos = {p.pk for p, _ in resultado}
        coordinadores = Profesional.objects.filter(estado=True, usuario__groups__name='Coordinador').distinct()
        resultado += [(p, 'Coordinador') for p in coordinadores if p.pk not in ya_incluidos]
    return resultado


def emitir_alerta(regla, motivo, responsable, enlaces):
    """Crea una alerta por destinatario, sin repetir la misma alerta para el mismo caso."""
    from .models import Alerta
    delegacion = responsable.id_delegacion if responsable else None
    creadas = 0
    for destinatario, rol in destinatarios_alerta(regla, delegacion):
        _, creada = Alerta.objects.get_or_create(
            id_destinatario=destinatario, enlace_referencia=enlaces[rol], motivo=motivo[:255],
            defaults={'id_responsable': responsable, 'id_delegacion': delegacion},
        )
        creadas += creada
    return creadas


def alertas_de_vencimiento(regla, hoy):
    from tuboApp.models import Compromiso
    limite = hoy + timedelta(days=int(regla.umbral))
    compromisos = (Compromiso.objects
                   .filter(estado=True, fecha_comprometida__lte=limite)
                   .exclude(estado_progreso='REALIZADO')
                   .select_related('id_funcionario__id_delegacion', 'id_actividad'))
    creadas = 0
    for compromiso in compromisos:
        fecha = compromiso.fecha_comprometida.strftime('%d/%m/%Y')
        codigo = compromiso.id_actividad.codigo_unico
        vencido = compromiso.fecha_comprometida < hoy
        motivo = f'Compromiso {codigo} vencido el {fecha}' if vencido else f'Compromiso {codigo} vence el {fecha}'
        enlace = reverse('tuboApp:detalle_actividad', args=[compromiso.id_actividad_id])
        creadas += emitir_alerta(regla, motivo, compromiso.id_funcionario, {'Delegado': enlace, 'Coordinador': enlace})
    return creadas


def alertas_de_evidencia_pendiente(regla, hoy):
    from actividadApp.models import Evidencia
    dias = int(regla.umbral)
    evidencias = (Evidencia.objects
                  .filter(estado=True, estado_revision='PENDIENTE', fecha__lte=timezone.now() - timedelta(days=dias))
                  .select_related('id_actividad__id_profesional__id_delegacion'))
    creadas = 0
    for evidencia in evidencias:
        actividad = evidencia.id_actividad
        motivo = f'Evidencia #{evidencia.pk} de la actividad {actividad.codigo_unico} lleva más de {dias} días sin revisar'
        enlaces = {
            'Delegado': reverse('actividadApp:crear_validacion') + f'?evidencia={evidencia.pk}',
            'Coordinador': reverse('tuboApp:detalle_actividad', args=[actividad.pk]),
        }
        creadas += emitir_alerta(regla, motivo, actividad.id_profesional, enlaces)
    return creadas


def alertas_de_avance_bajo(regla, hoy):
    """Solo lee el cumplimiento ya guardado en cada Indicador; no lo calcula."""
    from administracionApp.models import Periodo
    from .models import Indicador
    periodos = [p for p in Periodo.objects.filter(estado=True) if p.esta_vigente]
    indicadores = (Indicador.objects
                   .filter(estado=True, meta_id_meta__estado=True, meta_id_meta__id_periodo__in=periodos,
                           cumplimiento__lt=regla.umbral)
                   .select_related('id_funcionario__id_delegacion', 'meta_id_meta__id_cargo_item__id_item'))
    creadas = 0
    for indicador in indicadores:
        profesional = indicador.id_funcionario
        item = indicador.meta_id_meta.id_cargo_item.id_item.nombre
        motivo = f'Avance de {profesional.nombres} {profesional.apellido_paterno} en {item} bajo el umbral de {numero(regla.umbral)}%'
        enlaces = {
            'Delegado': reverse('monitoreoApp:dashboard_delegado'),
            'Coordinador': reverse('monitoreoApp:tablero_indicadores_coordinador'),
        }
        creadas += emitir_alerta(regla, motivo, profesional, enlaces)
    return creadas


GENERADORES_ALERTA = {
    'VENCIMIENTO': alertas_de_vencimiento,
    'EVIDENCIA_PENDIENTE': alertas_de_evidencia_pendiente,
    'AVANCE_BAJO': alertas_de_avance_bajo,
}


def generar_alertas(hoy=None):
    """Revisa las condiciones de cada regla vigente y crea las alertas nuevas. Devuelve cuántas creó."""
    from .models import ReglaAlerta
    hoy = hoy or date.today()
    registrar_incumplimientos(hoy)
    creadas = 0
    for tipo, generador in GENERADORES_ALERTA.items():
        regla = ReglaAlerta.vigente(tipo, hoy)
        if regla is not None:
            creadas += generador(regla, hoy)
    return creadas


def generar_alertas_periodicamente():
    """Como no hay tareas programadas, se revisa al navegar, a lo más una vez cada SEGUNDOS_ENTRE_REVISIONES."""
    if cache.add('alertas_revisadas_recientemente', True, SEGUNDOS_ENTRE_REVISIONES):
        generar_alertas()


# --- SEGUIMIENTO DE COMPROMISOS (HU-14) ---
DIAS_AVISO_POR_DEFECTO = 2


def dias_aviso_vencimiento(hoy=None):
    """Días de anticipación de la regla de alerta de vencimiento vigente."""
    from .models import ReglaAlerta
    regla = ReglaAlerta.vigente(ReglaAlerta.VENCIMIENTO, hoy or date.today())
    return int(regla.umbral) if regla else DIAS_AVISO_POR_DEFECTO


def resumen_compromisos(compromisos, hoy=None):
    """Conteo por estado en una sola consulta: pendientes, próximos a vencer, vencidos y realizados."""
    from django.db.models import Count, Q
    hoy = hoy or date.today()
    limite = hoy + timedelta(days=dias_aviso_vencimiento(hoy))
    abierto = ~Q(estado_progreso='REALIZADO')
    return compromisos.aggregate(
        total=Count('pk'),
        realizados=Count('pk', filter=Q(estado_progreso='REALIZADO')),
        vencidos=Count('pk', filter=abierto & Q(fecha_comprometida__lt=hoy)),
        proximos=Count('pk', filter=abierto & Q(fecha_comprometida__gte=hoy, fecha_comprometida__lte=limite)),
        pendientes=Count('pk', filter=abierto & Q(fecha_comprometida__gt=limite)),
    )


def registrar_incumplimiento(compromiso, hoy=None):
    """Deja constancia del vencimiento; la fecha original se conserva aunque el compromiso se realice o se reprograme."""
    from tuboApp.models import HistorialIncumplimiento
    hoy = hoy or date.today()
    if compromiso.estado_progreso == 'REALIZADO' or not compromiso.fecha_comprometida or compromiso.fecha_comprometida >= hoy:
        return None
    registro, creado = HistorialIncumplimiento.objects.get_or_create(
        compromiso=compromiso, estado=True,
        defaults={'actividad_id': compromiso.id_actividad_id, 'profesional_id': compromiso.id_funcionario_id,
                  'fecha_vencimiento': compromiso.fecha_comprometida,
                  'dias_retraso': (hoy - compromiso.fecha_comprometida).days},
    )
    if not creado:
        dias = (hoy - registro.fecha_vencimiento).days
        if dias != registro.dias_retraso:
            registro.dias_retraso = dias
            registro.save(update_fields=['dias_retraso'])
    return registro


def registrar_incumplimientos(hoy=None):
    from tuboApp.models import Compromiso
    hoy = hoy or date.today()
    vencidos = Compromiso.objects.filter(estado=True, fecha_comprometida__lt=hoy).exclude(estado_progreso='REALIZADO')
    for compromiso in vencidos:
        registrar_incumplimiento(compromiso, hoy)
