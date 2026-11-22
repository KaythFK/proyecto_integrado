from datetime import date, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.http import request
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError

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
PREFIJO_POR_TIPO = {'VENCIMIENTO': 'Compromiso', 'EVIDENCIA_PENDIENTE': 'Evidencia', 'AVANCE_BAJO': 'Avance', 'SIN_REGISTROS': 'Sin registros', 'RETROALIMENTACION': 'Recibiste un',}


def tipo_de_alerta(alerta):
    if alerta.motivo.startswith(('Recibiste una', 'Recibiste un')):
        return 'RETROALIMENTACION'
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


# --- FRECUENCIA DE REGISTROS ---
DIAS_SIN_REGISTROS_POR_DEFECTO = 3


def dias_umbral_sin_registros(hoy=None):
    """Días hábiles sin registros que tolera la regla vigente."""
    from .models import ReglaAlerta
    regla = ReglaAlerta.vigente(ReglaAlerta.SIN_REGISTROS, hoy or date.today())
    return int(regla.umbral) if regla else DIAS_SIN_REGISTROS_POR_DEFECTO


def dias_habiles(desde, hasta, ausencias=()):
    """Días de lunes a viernes entre desde y hasta (ambos incluidos), sin contar los días de ausencia."""
    dias = 0
    dia = desde
    while dia <= hasta:
        if dia.weekday() < 5 and not any(inicio <= dia <= termino for inicio, termino in ausencias):
            dias += 1
        dia += timedelta(days=1)
    return dias


def funcionarios_a_monitorear(delegacion=None):
    from administracionApp.models import Profesional
    profesionales = (Profesional.objects
                     .filter(estado=True, usuario__is_active=True, usuario__groups__name='Profesional')
                     .select_related('id_delegacion').distinct().order_by('nombres', 'apellido_paterno'))
    if delegacion is not None:
        profesionales = profesionales.filter(id_delegacion=delegacion)
    return profesionales


def uso_de_funcionarios(profesionales, periodo, umbral, hoy=None):
    """
    Por funcionario: último registro válido, registros del período, promedio diario y días hábiles sin registrar.
    Un registro válido es una actividad o una gestión activa. Se mide hasta ayer, o hasta el cierre si el período ya terminó,
    y los días con ausencia registrada no cuentan.
    """
    from django.db.models import Count, F, Max, Q
    from actividadApp.models import Actividad, Ausencia, GestionActividad
    from config.utils import inicio_del_dia
    hoy = hoy or date.today()
    profesionales = list(profesionales)
    if periodo is None or not profesionales:
        return []

    ultimo_dia = min(hoy - timedelta(days=1), periodo.fecha_termino)
    corte = inicio_del_dia(ultimo_dia + timedelta(days=1))
    del_periodo = Q(fecha_registro__gte=inicio_del_dia(periodo.fecha_inicio), fecha_registro__lt=corte)
    ids = [p.pk for p in profesionales]
    consultas = (
        Actividad.objects.filter(id_profesional__in=ids, estado=True).values(funcionario=F('id_profesional')),
        GestionActividad.objects.filter(profesional__in=ids, estado=True).values(funcionario=F('profesional')),
    )
    ultimos, totales = {}, {}
    for consulta in consultas:
        for fila in consulta.order_by().annotate(ultimo=Max('fecha_registro', filter=Q(fecha_registro__lt=corte)),
                                                  total=Count('pk', filter=del_periodo)):
            pk = fila['funcionario']
            if fila['ultimo'] and (pk not in ultimos or fila['ultimo'] > ultimos[pk]):
                ultimos[pk] = fila['ultimo']
            totales[pk] = totales.get(pk, 0) + fila['total']

    ausencias = {}
    for pk, inicio, termino in (Ausencia.objects
                                .filter(profesional_ausente__in=ids, estado=True,
                                        fecha_inicio__lte=ultimo_dia, fecha_termino__gte=periodo.fecha_inicio)
                                .values_list('profesional_ausente_id', 'fecha_inicio', 'fecha_termino')):
        ausencias.setdefault(pk, []).append((inicio, termino))

    filas = []
    for profesional in profesionales:
        ultimo = ultimos.get(profesional.pk)
        if ultimo is not None and timezone.is_aware(ultimo):
            ultimo = timezone.localtime(ultimo)
        dias_ausente = ausencias.get(profesional.pk, [])
        dias_transcurridos = dias_habiles(periodo.fecha_inicio, ultimo_dia, dias_ausente)
        total = totales.get(profesional.pk, 0)
        desde = max(ultimo.date() + timedelta(days=1), periodo.fecha_inicio) if ultimo else periodo.fecha_inicio
        sin_registros = dias_habiles(desde, ultimo_dia, dias_ausente)
        filas.append({
            'funcionario': profesional,
            'ultimo_registro': ultimo,
            'total': total,
            'dias_transcurridos': dias_transcurridos,
            'promedio': round(total / dias_transcurridos, 2) if dias_transcurridos else None,
            'dias_sin_registros': sin_registros,
            'supera_umbral': sin_registros > umbral,
        })
    filas.sort(key=lambda f: (not f['supera_umbral'], -f['dias_sin_registros'], f['funcionario'].nombres))
    return filas


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


def alertas_sin_registros(regla, hoy):
    from administracionApp.models import Periodo
    periodo = next((p for p in Periodo.objects.filter(estado=True).order_by('-fecha_inicio') if p.esta_vigente), None)
    url = reverse('monitoreoApp:frecuencia_registros')
    creadas = 0
    for fila in uso_de_funcionarios(funcionarios_a_monitorear(), periodo, int(regla.umbral), hoy):
        if not fila['supera_umbral']:
            continue
        profesional = fila['funcionario']
        desde = f"desde el {fila['ultimo_registro']:%d/%m/%Y}" if fila['ultimo_registro'] else f'en el período {periodo.nombre}'
        motivo = (f'Sin registros de {profesional.nombres} {profesional.apellido_paterno} {desde}: '
                  f'supera los {numero(regla.umbral)} días hábiles')
        enlaces = {'Delegado': url, 'Coordinador': f'{url}?delegacion={profesional.id_delegacion_id}'}
        creadas += emitir_alerta(regla, motivo, profesional, enlaces)
    return creadas


GENERADORES_ALERTA = {
    'VENCIMIENTO': alertas_de_vencimiento,
    'EVIDENCIA_PENDIENTE': alertas_de_evidencia_pendiente,
    'AVANCE_BAJO': alertas_de_avance_bajo,
    'SIN_REGISTROS': alertas_sin_registros,
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





def sincronizar_indicador(indicador, guardar=True):
    """
    Calcula el avance desde actividades activas con evidencia aprobada
    para ese funcionario y meta, y actualiza cumplimiento y semáforo.
    """
    from actividadApp.models import Evidencia

    meta = indicador.meta_id_meta
    funcionario = indicador.id_funcionario

    if not meta or not funcionario:
        return indicador

    avance_real = Evidencia.objects.filter(
        estado=True,
        estado_revision='APROBADO',
        id_actividad__estado=True,
        id_actividad__id_meta=meta,
        id_actividad__id_profesional=funcionario,
    ).count()

    calculo = calcular_indicadores_meta(avance_real, meta)

    indicador.avance = Decimal(str(avance_real)).quantize(Decimal('0.01'))
    indicador.cumplimiento = Decimal(str(calculo['cumplimiento'])).quantize(Decimal('0.01'))
    indicador.semaforo = calculo['semaforo']
    if indicador.ponderacion is None:
        indicador.ponderacion = Decimal(str(meta.ponderador or 0)).quantize(Decimal('0.01'))
    if indicador.ajuste is None:
        indicador.ajuste = Decimal('0.00')

    if guardar:
        indicador.save(update_fields=['avance', 'cumplimiento', 'semaforo', 'ponderacion', 'ajuste'])

    return indicador


def _es_vigente_en_fecha(obj, fecha_ref):
    """
    [KAN-414 / KAN-415] Verifica si un Cargo o una Meta rige en la fecha_ref indicada
    (estado activo, fecha_inicio <= fecha_ref y fecha_termino nula o >= fecha_ref).
    """
    if not getattr(obj, 'estado', True):
        return False
    inicio = getattr(obj, 'fecha_inicio', None)
    termino = getattr(obj, 'fecha_termino', None)
    if inicio and inicio > fecha_ref:
        return False
    if termino and termino < fecha_ref:
        return False
    return True


def asegurar_indicadores_profesional(profesional, periodo_id=None, fecha_referencia=None):
    """
    [KAN-414 / KAN-415] Asegura indicadores en 0 para las metas activas del cargo
    del profesional cuya vigencia aplique en la fecha de referencia, sin alterar
    períodos cerrados ni aplicar cambios antes de su fecha de vigencia.
    """
    from django.db import DatabaseError, transaction
    from .models import Indicador, Meta

    if not profesional or not profesional.estado or not profesional.id_cargo_id:
        return []

    cargo = profesional.id_cargo
    if not cargo or not cargo.estado:
        return []

    metas_qs = Meta.objects.filter(
        estado=True,
        id_cargo_item__estado=True,
        id_cargo_item__id_cargo_id=profesional.id_cargo_id,
        id_periodo__estado=True,
    ).select_related('id_periodo', 'id_cargo_item__id_cargo', 'id_cargo_item__id_item')

    if periodo_id:
        metas_qs = metas_qs.filter(id_periodo_id=periodo_id)

    hoy = fecha_referencia or date.today()
    indicadores = []

    for meta in metas_qs:
        periodo = meta.id_periodo
        # CA3: Nunca crear ni modificar indicadores en períodos cerrados
        if not periodo or not periodo.esta_abierto:
            continue

        fecha_corte = max(periodo.fecha_inicio, hoy)
        if fecha_corte > periodo.fecha_termino:
            continue

        # CA2 y CA3: El Cargo y la Meta deben estar vigentes en fecha_corte
        if not _es_vigente_en_fecha(cargo, fecha_corte):
            continue
        if not _es_vigente_en_fecha(meta, fecha_corte):
            continue

        try:
            with transaction.atomic():
                indicador, _ = Indicador.objects.get_or_create(
                    meta_id_meta=meta,
                    id_funcionario=profesional,
                    defaults={
                        'avance': Decimal('0.00'),
                        'cumplimiento': Decimal('0.00'),
                        'ponderacion': Decimal(str(meta.ponderador or 0)).quantize(Decimal('0.01')),
                        'ajuste': Decimal('0.00'),
                        'semaforo': 'ROJO',
                        'estado': True,
                    },
                )
                sincronizar_indicador(indicador, guardar=True)
                indicadores.append(indicador)
        except (ValidationError, DatabaseError) as exc:
            print(f"Error asegurando indicador para {profesional} en meta {meta}: {exc}")

    return indicadores

def inicializar_items_vigentes_periodo(periodo):
    """
    [KAN-414 - CA2] Al iniciar o abrir un período, asigna automáticamente
    los ítems/metas vigentes de cada cargo a todos los profesionales activos.
    """
    from django.db import DatabaseError, transaction
    from administracionApp.models import Profesional

    if not periodo or not periodo.esta_abierto:
        return 0

    profesionales_activos = Profesional.objects.filter(
        estado=True,
        id_cargo__estado=True,
    ).select_related('id_cargo', 'id_delegacion')

    total_asignados = 0
    for prof in profesionales_activos:
        try:
            with transaction.atomic():
                asignados = asegurar_indicadores_profesional(
                    prof,
                    periodo_id=periodo.pk,
                    fecha_referencia=periodo.fecha_inicio,
                )
                total_asignados += len(asignados)
        except (ValidationError, DatabaseError) as exc:
            print(f"Error asegurando indicadores para {prof}: {exc}")

    return total_asignados

def asegurar_indicadores_para_tablero(periodo_param='', delegacion_param=''):
    """
    Asegura los indicadores vigentes según cargo para los profesionales activos
    antes de consultar el tablero (respeta vigencia y períodos cerrados).
    """
    from administracionApp.models import Profesional

    profesionales_qs = Profesional.objects.filter(estado=True).select_related('id_cargo', 'id_delegacion')
    if delegacion_param and str(delegacion_param).isdigit():
        profesionales_qs = profesionales_qs.filter(id_delegacion_id=int(delegacion_param))

    periodo_id = int(periodo_param) if periodo_param and str(periodo_param).isdigit() else None

    for prof in profesionales_qs:
        asegurar_indicadores_profesional(prof, periodo_id=periodo_id)


def registrar_avance_por_validacion_aprobada(validacion):
    """
    Cuando una validación se aprueba, marca la evidencia como APROBADO,
    asegura el indicador de (meta, funcionario) si el período está abierto
    y recalcula avance, cumplimiento y semáforo.
    """
    from .models import Indicador

    evidencia = validacion.id_evidencia
    if not evidencia:
        return None, True

    evidencia.estado_revision = 'APROBADO'
    evidencia.save(update_fields=['estado_revision'])

    actividad = evidencia.id_actividad
    meta = actividad.id_meta if actividad else None
    funcionario = actividad.id_profesional if actividad else None

    periodo_abierto = bool(meta and meta.id_periodo and meta.id_periodo.esta_abierto)
    if not (meta and funcionario and periodo_abierto):
        return None, periodo_abierto

    indicador, _ = Indicador.objects.get_or_create(
        meta_id_meta=meta,
        id_funcionario=funcionario,
        defaults={
            'avance': Decimal('0.00'),
            'cumplimiento': Decimal('0.00'),
            'ponderacion': Decimal(str(meta.ponderador or 0)).quantize(Decimal('0.01')),
            'ajuste': Decimal('0.00'),
            'semaforo': 'ROJO',
            'estado': True,
        },
    )
    sincronizar_indicador(indicador, guardar=True)
    return indicador, periodo_abierto


def calcular_ajuste_retroalimentaciones(meta, funcionario):
    """
    Suma los porcentajes de felicitaciones (+) y resta los de reclamos (-)
    activos registrados para el funcionario en la meta indicada.
    """
    from actividadApp.models import Retroalimentacion

    if not meta or not funcionario:
        return Decimal('0.00')

    retros = Retroalimentacion.objects.filter(
        estado=True,
        meta=meta,
        retroalimentado=funcionario,
    ).only('tipo', 'porcentaje_impacto')

    total_ajuste = Decimal('0.00')
    for r in retros:
        pct = Decimal(str(r.porcentaje_impacto or 0))
        if r.tipo == 'FELICITACION':
            total_ajuste += pct
        elif r.tipo == 'RECLAMO':
            total_ajuste -= pct

    return total_ajuste.quantize(Decimal('0.01'))


def sincronizar_indicador(indicador, guardar=True):
    """
    Calcula el avance desde evidencias aprobadas, topa el cumplimiento base en
    120%, aplica el ajuste por retroalimentaciones activas y actualiza
    cumplimiento, ajuste y semáforo.
    """
    from actividadApp.models import Evidencia

    meta = indicador.meta_id_meta
    funcionario = indicador.id_funcionario

    if not meta or not funcionario:
        return indicador

    avance_real = Evidencia.objects.filter(
        estado=True,
        estado_revision='APROBADO',
        id_actividad__estado=True,
        id_actividad__id_meta=meta,
        id_actividad__id_profesional=funcionario,
    ).count()

    calculo = calcular_indicadores_meta(avance_real, meta)
    ajuste_retro = calcular_ajuste_retroalimentaciones(meta, funcionario)

    cumplimiento_base = min(Decimal(str(calculo['cumplimiento'])), Decimal('120.00'))
    cumplimiento_ajustado = max(
        Decimal('0.00'),
        min(cumplimiento_base + ajuste_retro, Decimal('120.00'))
    )

    periodo = meta.id_periodo
    regular = Decimal(str(periodo.umbral_regular))
    excelencia = Decimal(str(periodo.umbral_exelencia))
    if excelencia <= Decimal('1'):
        regular *= Decimal('100')
        excelencia *= Decimal('100')

    if cumplimiento_ajustado >= excelencia:
        semaforo_final = 'VERDE'
    elif cumplimiento_ajustado >= regular:
        semaforo_final = 'AMARILLO'
    else:
        semaforo_final = 'ROJO'

    indicador.avance = Decimal(str(avance_real)).quantize(Decimal('0.01'))
    indicador.ajuste = ajuste_retro
    indicador.cumplimiento = cumplimiento_ajustado.quantize(Decimal('0.01'))
    indicador.semaforo = semaforo_final
    if indicador.ponderacion is None:
        indicador.ponderacion = Decimal(str(meta.ponderador or 0)).quantize(Decimal('0.01'))

    if guardar:
        indicador.save(update_fields=['avance', 'cumplimiento', 'semaforo', 'ponderacion', 'ajuste'])

    return indicador
