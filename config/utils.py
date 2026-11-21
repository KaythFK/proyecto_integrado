from django.core.exceptions import ValidationError
from datetime import date, timezone, timedelta

from django.db import models

from administracionApp.models import Delegacion, Periodo, Profesional
from actividadApp.models import Evidencia, Actividad
from django.db.models import Q
from django.utils.timezone import localdate
from decimal import Decimal, InvalidOperation
def validar_y_formatear_rut(rut_ingresado):
    """
    Valida un RUT chileno usando el algoritmo Módulo 11 de forma global 
    y lo devuelve formateado con puntos y guion (Ej: 12.345.678-9).
    """
    if not rut_ingresado:
        raise ValidationError("El RUT no puede estar vacío.")
    rut_limpio = str(rut_ingresado).strip().replace(".", "").replace("-", "").upper()
    
    if len(rut_limpio) < 2:
        raise ValidationError("El RUT ingresado no es válido.")
        
    cuerpo = rut_limpio[:-1]
    dv = rut_limpio[-1]
    
    if not cuerpo.isdigit():
        raise ValidationError("El cuerpo del RUT debe contener solo números.")
        
    # Algoritmo Módulo 11
    suma = 0
    multiplo = 2
    
    for r in reversed(cuerpo):
        suma += int(r) * multiplo
        multiplo += 1
        if multiplo > 7:
            multiplo = 2
            
    esperado = 11 - (suma % 11)
    if esperado == 11:
        dv_calculado = '0'
    elif esperado == 10:
        dv_calculado = 'K'
    else:
        dv_calculado = str(esperado)
        
    if dv_calculado != dv:
        raise ValidationError("El dígito verificador del RUT es incorrecto (Módulo 11 inválido).")
        
    # Formateo automático con puntos y guion
    cuerpo_invertido = cuerpo[::-1]
    cuerpo_con_puntos = '.'.join(cuerpo_invertido[i:i+3] for i in range(0, len(cuerpo_invertido), 3))
    rut_formateado = cuerpo_con_puntos[::-1] + '-' + dv
    
    return rut_formateado

def validar_texto_no_vacio(texto, nombre_campo="El campo"):
    """Valida que un texto no sea solo espacios en blanco."""
    if not texto or not str(texto).strip():
        raise ValidationError(f"{nombre_campo} no puede estar vacío o contener solo espacios.")
    return str(texto).strip()

def validar_fecha_no_futura(fecha):
    """Valida que una fecha (como nacimiento) no sea en el futuro."""
    if fecha and fecha > date.today():
        raise ValidationError("La fecha no puede ser en el futuro.")
    return fecha

def validar_rango_fechas(fecha_inicio, fecha_termino):
    """Valida que la fecha de término no sea anterior a la de inicio."""
    if fecha_inicio and fecha_termino and fecha_termino < fecha_inicio:
        raise ValidationError("La fecha de término no puede ser anterior a la fecha de inicio.")



def validar_que_sea_delegado(profesional):
    """Valida que el profesional receptor esté vinculado como delegado o responsable en alguna delegación."""
    if profesional:
        # Usamos los campos reales que existen en el modelo Delegacion según el traceback
        es_delegado = Delegacion.objects.filter(
            Q(profesional=profesional) | Q(responsable=profesional)
        ).exists()
        
        if not es_delegado:
            raise ValidationError("El profesional seleccionado no figura como delegado y no puede recibir retroalimentaciones.")
    return profesional

def validar_profesionales_distintos(receptor, retroalimentado):
    """Valida que el profesional receptor y el retroalimentado no sean la misma persona."""
    if receptor and retroalimentado and receptor == retroalimentado:
        raise ValidationError("El profesional receptor y el profesional retroalimentado no pueden ser la misma persona.")



def validar_entero_positivo(valor, nombre_campo="El valor"):
    """Valida que un número sea un entero positivo mayor a 0."""
    if valor is not None:
        try:
            val_int = int(valor)
            if val_int < 1:
                raise ValidationError(f"{nombre_campo} debe ser un número entero positivo mayor o igual a 1.")
        except (TypeError, ValueError):
            raise ValidationError(f"{nombre_campo} debe ser un número entero válido.")
    return valor


def validar_evidencia_no_duplicada(evidencia):
    """
    [KAN-170] Valida que la evidencia no haya sido aprobada previamente
    para evitar sumas duplicadas en el indicador.
    """
    if evidencia and evidencia.estado_revision == 'APROBADO':
        raise ValidationError("Esta evidencia ya fue validada y contabilizada.")
    return evidencia

def limitar_a_opciones_activas(campo, valor_actual=None):
    """Deja solo opciones activas del catálogo; al editar conserva la que ya tenía el registro."""
    filtro = Q(estado=True)
    if valor_actual is not None:
        filtro |= Q(pk=valor_actual)
    campo.queryset = campo.queryset.filter(filtro).order_by('nombre')


def validar_acceso_actividad(user, actividad):
    """Admin y Coordinador: todas. Delegado: las de su delegación. Profesional: las suyas. Si no, 403."""
    from django.core.exceptions import PermissionDenied
    if user.groups.filter(name__in=['Administrador', 'Coordinador']).exists():
        return
    profesional = getattr(user, 'profesional', None)
    if profesional is not None:
        if user.groups.filter(name='Delegado').exists() and actividad.id_profesional.id_delegacion_id == profesional.id_delegacion_id:
            return
        if user.groups.filter(name='Profesional').exists() and actividad.id_profesional_id == profesional.pk:
            return
    raise PermissionDenied('No tienes permiso para acceder a esta actividad: está asignada a otro funcionario o delegación.')


def puede_modificar_compromiso(user, compromiso):
    """Admin y Coordinador: todos. Delegado: los de su delegación. Profesional: los suyos."""
    if user.groups.filter(name__in=['Administrador', 'Coordinador']).exists():
        return True

    profesional = getattr(user, 'profesional', None)
    if profesional is None:
        return False

    if user.groups.filter(name='Delegado').exists():
        if compromiso.id_funcionario.id_delegacion_id == profesional.id_delegacion_id:
            return True

    if user.groups.filter(name='Profesional').exists():
        if compromiso.id_funcionario_id == profesional.pk:
            return True

    return False


def validar_periodo_abierto(meta):
    """
    [HU-25 / KAN-100] Valida que el período asociado a la meta o indicador 
    no haya finalizado (comparando la fecha actual con la fecha de término).
    Si el período ya expiró/cerró por fecha, bloquea la modificación.
    """
    if meta and hasattr(meta, 'id_periodo') and meta.id_periodo:
        periodo = meta.id_periodo
        
        # Verificamos si la fecha actual es posterior a la fecha de término del período
        if hasattr(periodo, 'fecha_termino') and periodo.fecha_termino:
            if date.today() > periodo.fecha_termino:
                raise ValidationError("No se pueden modificar indicadores o metas de un período que ya ha finalizado.")

        if not periodo.estado:
            raise ValidationError(f'El período "{periodo.nombre}" está cerrado. Debe reabrirse antes de modificar sus resultados.')
                
    return meta


def rol_usuario(request):
    """Entrega rol_menu y permisos de validación a todas las plantillas para el menú lateral de base.html."""
    usuario = getattr(request, 'user', None)
    if not usuario or not usuario.is_authenticated:
        return {'rol_menu': None, 'puede_validar': False}

    grupos = set(usuario.groups.values_list('name', flat=True))
    
    if 'Administrador' in grupos or (usuario.is_superuser and not grupos):
        rol = 'administrador'
    elif 'Coordinador' in grupos:
        rol = 'coordinador'
    elif 'Delegado' in grupos:
        rol = 'delegado'
    elif 'Profesional' in grupos:
        rol = 'profesional'
    else:
        rol = None

    # --- AQUÍ ESTABA EL DETALLE ---
    # Aseguramos que Administrador, Delegado o Superusuario tengan permitido validar
    puede_validar = usuario.is_superuser or 'Administrador' in grupos or 'Delegado' in grupos

    return {
        'rol_menu': rol,
        'puede_validar': puede_validar
    }

def validar_imagen_evidencia(archivo):
    """
    Valida que el archivo subido sea una imagen permitida (JPG, PNG, WEBP)
    y que no supere el tamaño máximo de 10 MB para fotos de terreno.
    """
    if not archivo:
        raise ValidationError("Debe seleccionar un archivo de imagen válido.")

    # 1. Validar extensiones permitidas
    extensiones_permitidas = ['.jpg', '.jpeg', '.png', '.webp']
    nombre_archivo = archivo.name.lower()
    
    if not any(nombre_archivo.endswith(ext) for ext in extensiones_permitidas):
        raise ValidationError(
            "Formato de archivo no permitido. Solo se aceptan imágenes en formato JPG, PNG o WEBP."
        )

    # 2. Validar tamaño máximo (10 MB = 10 * 1024 * 1024 bytes)
    tamano_maximo = 10 * 1024 * 1024 
    if archivo.size > tamano_maximo:
        raise ValidationError(
            "El archivo es demasiado pesado. El tamaño máximo permitido para las fotografías es de 10 MB."
        )
        
    return archivo



def filtrar_evidencias_por_rol(user):
    """
    Retorna el queryset de evidencias filtrado estrictamente según el rol del usuario:
    - Administrador: Ve todo.
    - Delegado: Ve las evidencias de los profesionales de su delegación.
    - Profesional: Ve únicamente sus propias evidencias.
    """
    evidencias = Evidencia.objects.all().select_related('id_actividad').order_by('-id_evidencia')
    profesional_actual = getattr(user, 'profesional', None)

    if user.groups.filter(name='Administrador').exists():
        return evidencias
    
    if user.groups.filter(name='Delegado').exists():
        if profesional_actual and profesional_actual.id_delegacion:
            return evidencias.filter(id_actividad__id_profesional__id_delegacion=profesional_actual.id_delegacion)
        return Evidencia.objects.none()

    # Si es un profesional normal
    if profesional_actual:
        return evidencias.filter(id_actividad__id_profesional=profesional_actual)
    
    return Evidencia.objects.none()



def validar_actividad_permite_evidencias(actividad):
    """
    Valida que la actividad no tenga ya una evidencia aprobada.
    Bloquea la subida de nuevos respaldos si ya fue auditada positivamente.
    """
    ya_aprobada = Evidencia.objects.filter(id_actividad=actividad, estado_revision='APROBADO').exists()
    
    if ya_aprobada:
        raise ValidationError(
            f"La actividad {actividad.codigo_unico} ya cuenta con una evidencia validada y aprobada. No se pueden adjuntar más archivos."
        )
    return actividad


def validar_actividad_finalizada(actividad):
    """
    Bloquea el cambio de estado de progreso si la actividad ya fue marcada como FINALIZADA.
    """
    if actividad.estado_progreso == 'FINALIZADA':
        raise ValidationError(
            f"La actividad {actividad.codigo_unico} ya se encuentra FINALIZADA. No es posible retroceder su estado de progreso."
        )
    return actividad



def validar_datos_vecino_actividad(vecino):
    if not vecino:
        raise ValidationError("Debe asociar un vecino solicitante a la actividad.")
    if not vecino.nombres or not vecino.telefono:
        raise ValidationError("El vecino no tiene nombre o teléfono registrado.")

def validar_tope_diario_actividades(profesional):
    # Usamos localdate() directo para evitar el choque de librerías
    hoy = localdate()
    
    cantidad_hoy = Actividad.objects.filter(
        id_profesional=profesional, 
        fecha_registro__date=hoy
    ).count()
    
    if cantidad_hoy >= 7:
        raise ValidationError("Superaste el tope máximo de 7 registros diarios.")

def validar_cierre_semanal(fecha_realizacion):
    hoy = localdate()
    fecha_date = fecha_realizacion.date() if hasattr(fecha_realizacion, 'date') else fecha_realizacion
    
    if hoy.weekday() == 0:
        # Si hoy es Lunes: El límite es el lunes de la SEMANA PASADA (hace 7 días)
        limite = hoy - timedelta(days=7)
    else:
        # Si es Martes a Domingo: El límite es el lunes de ESTA SEMANA
        limite = hoy - timedelta(days=hoy.weekday())
    
    if fecha_date < limite:
        raise ValidationError(f"Fecha bloqueada. El límite máximo para registrar gestiones atrasadas hoy es desde el {limite.strftime('%d/%m/%Y')}.")

LISTADO_ACTIVIDADES_POR_ROL = {
    'Administrador': 'administracionApp:admin-actividades',
    'Coordinador': 'tuboApp:listar_todas',
    'Delegado': 'actividadApp:actividades_delegacion',
    'Profesional': 'actividadApp:listar_actividades',
}


def recordar_filtros(request, nombre_url):
    request.session[f'filtros:{nombre_url}'] = request.GET.urlencode()


def url_con_filtros(request, nombre_url):
    from django.urls import reverse
    filtros = request.session.get(f'filtros:{nombre_url}', '')
    return reverse(nombre_url) + (f'?{filtros}' if filtros else '')


def url_listado_actividades(request):
    for rol, nombre_url in LISTADO_ACTIVIDADES_POR_ROL.items():
        if request.user.groups.filter(name=rol).exists():
            return url_con_filtros(request, nombre_url)
    return '/'


def delegacion_del_delegado(user):
    """Delegación del usuario si su rol es Delegado; None para los roles con alcance global."""
    if user.groups.filter(name='Delegado').exists() and hasattr(user, 'profesional'):
        return user.profesional.id_delegacion
    return None


def validar_suma_ponderaciones(lista_ponderaciones):
    """
    Recibe una lista de ponderaciones (strings, enteros o floats) provenientes del request.
    Valida que sean números válidos y que sumen exactamente 100.
    """
    if not lista_ponderaciones:
        raise ValidationError("Debe asignar al menos un ítem con ponderación al cargo.")

    suma_total = Decimal('0.00')
    
    for valor in lista_ponderaciones:
        try:
            # Convertimos a string primero para una conversión segura a Decimal
            ponderacion = Decimal(str(valor))
            if ponderacion < 0:
                raise ValidationError("Las ponderaciones no pueden ser negativas.")
            suma_total += ponderacion
        except InvalidOperation:
            raise ValidationError(f"El valor '{valor}' no es un número válido.")

    # Comparamos contra 100 exacto
    if suma_total != Decimal('100.00'):
        raise ValidationError(f"La suma de las ponderaciones debe ser exactamente 100%. Suma actual: {suma_total}%.")


def calcular_porcentaje_cumplimiento(avance, meta_periodo, tope_maximo=Decimal('120.00')):
    avance_dec = Decimal(str(avance or 0))
    meta_dec = Decimal(str(meta_periodo or 0))

    if meta_dec <= 0:
        raise ValidationError("La meta del período debe ser mayor que cero para calcular el cumplimiento.")

    cumplimiento = (avance_dec / meta_dec) * Decimal('100.00')
    if tope_maximo is not None:
        cumplimiento = min(cumplimiento, Decimal(str(tope_maximo)))
    return cumplimiento.quantize(Decimal('0.01'))


def calcular_cumplimiento_ponderado(porcentaje_cumplimiento, ponderador_item, tope_maximo=Decimal('150.00')):
    """
    [RN-005 / Sección 13.1] Calcula el cumplimiento ponderado:
    resultado ponderado = ponderador x (% de cumplimiento / 100).
    Respeta de forma opcional el tope máximo configurado (ej. 150%).
    """
    cump_dec = Decimal(str(porcentaje_cumplimiento or 0))
    ponderador_dec = Decimal(str(ponderador_item or 0))
    
    # Aplicamos la fórmula: Ponderador * (% Cumplimiento / 100)
    resultado = ponderador_dec * (cump_dec / Decimal('100.00'))
    
    # Aplicar tope académico configurado si corresponde (por defecto 150%)[cite: 27]
    if tope_maximo and resultado > Decimal(str(tope_maximo)):
        resultado = Decimal(str(tope_maximo))
        
    return resultado.quantize(Decimal('0.01'))


def semaforo_segun_umbral(cumplimiento, periodo):
    """Reglas de negocio institucionales para el color del semáforo."""
    regular = float(periodo.umbral_regular)
    excelencia = float(periodo.umbral_exelencia)
    if excelencia <= 1:
        regular, excelencia = regular * 100, excelencia * 100
    if cumplimiento >= excelencia:
        return 'VERDE'
    if cumplimiento >= regular:
        return 'AMARILLO'
    return 'ROJO'


def estado_desviacion(real, esperado, periodo):
    """Regla de la matriz del cliente para calcular desviaciones al día."""
    regular = float(periodo.umbral_regular)
    if regular > 1:
        regular = regular / 100
    if real >= esperado:
        return 'VERDE'
    if real >= esperado * regular:
        return 'AMARILLO'
    return 'ROJO'


def procesar_resumen_dashboard(metas, indicadores, periodo, esperado, modo_agrupacion='delegacion'):
    """
    Motor matemático: Calcula el cumplimiento ponderado (topando la base en 120%,
    aplicando el ajuste de retroalimentaciones y acotando entre 0% y 120%)
    y agrupa por Delegación o Funcionario.
    """
    metas_dict = {m.pk: m for m in metas}
    por_agrupacion = {}
    metas_en_rojo = 0

    for ind in indicadores:
        meta = metas_dict.get(ind.meta_id_meta_id)
        if not meta:
            continue

        if modo_agrupacion == 'delegacion':
            clave = ind.id_funcionario.id_delegacion.pk
            nombre = ind.id_funcionario.id_delegacion.nombre
        else:
            clave = ind.id_funcionario.pk
            nombre = f"{ind.id_funcionario.nombres} {ind.id_funcionario.apellido_paterno}"

        fila = por_agrupacion.setdefault(clave, {
            'nombre': nombre,
            'metas': 0,
            'suma': 0,
            'peso': 0
        })

        objetivo = float(meta.valor_objetivo)
        cumplimiento_base = min((float(ind.avance) / objetivo * 100), 120.0) if objetivo else 0.0
        ajuste_ind = float(ind.ajuste or 0)
        cumplimiento = max(0.0, min(cumplimiento_base + ajuste_ind, 120.0))

        if semaforo_segun_umbral(cumplimiento, periodo) == 'ROJO':
            metas_en_rojo += 1

        fila['metas'] += 1
        fila['suma'] += cumplimiento * float(meta.ponderador)
        fila['peso'] += float(meta.ponderador)

    filas = []
    for fila in por_agrupacion.values():
        fila['cumplimiento'] = round(fila['suma'] / fila['peso'], 1) if fila['peso'] else 0
        fila['semaforo'] = semaforo_segun_umbral(fila['cumplimiento'], periodo)
        fila['esperado'] = esperado
        fila['diferencia'] = round(fila['cumplimiento'] - esperado, 1)
        fila['desviacion'] = estado_desviacion(fila['cumplimiento'], esperado, periodo)
        filas.append(fila)

    filas.sort(key=lambda f: f['cumplimiento'])

    if not filas:
        return [], None, None, 0

    cumplimiento_global = round(sum(f['cumplimiento'] for f in filas) / len(filas), 1)
    return filas, cumplimiento_global, semaforo_segun_umbral(cumplimiento_global, periodo), metas_en_rojo



def verificar_periodo_activo():
    """
    KAN-200: Valida si el período actual está abierto para permitir modificaciones.
    Retorna (True, "") si está ok, o (False, "mensaje de error") si está cerrado.
    """
    hoy = timezone.now().date()
    # Buscamos el período activo que abarque la fecha actual o el último creado
    periodo = Periodo.objects.filter(estado=True, fecha_inicio__lte=hoy, fecha_termino__gte=hoy).first()
    if not periodo:
        periodo = Periodo.objects.filter(estado=True).order_by('-fecha_inicio').first()
        
    if not periodo:
        return False, "No existe ningún período de medición activo registrado en el sistema."
        
    # Usamos la propiedad 'esta_abierto' definida en tu modelo Periodo
    if not periodo.esta_abierto:
        return False, f"El período '{periodo.nombre}' se encuentra cerrado. No se permiten modificaciones."
        
    return True, ""


def validar_vigencia_fecha_actual():
    """
    KAN-199: Comprueba si la fecha actual se encuentra dentro del rango 
    de vigencia operativa del período activo.
    """
    hoy = timezone.now().date()
    periodo_vigente = Periodo.objects.filter(
        estado=True, 
        fecha_inicio__lte=hoy, 
        fecha_termino__gte=hoy
    ).exists()
    
    return periodo_vigente


def validar_datos_meta(valor_objetivo, unidad, ponderador):
    """
    [HU-05 / KAN-203] Valida en backend que los valores numéricos y la unidad
    de una meta sean válidos antes de crearla o editarla.
    """
    if valor_objetivo is None:
        raise ValidationError("El valor objetivo es obligatorio.")
    try:
        objetivo_dec = Decimal(str(valor_objetivo))
    except InvalidOperation:
        raise ValidationError("El valor objetivo debe ser un número válido.")
    if objetivo_dec <= Decimal('0'):
        raise ValidationError("El valor objetivo debe ser estrictamente mayor a cero.")

    unidad_limpia = validar_texto_no_vacio(unidad, "La unidad de medida")
    if len(unidad_limpia) < 2:
        raise ValidationError("El nombre de la unidad es demasiado corto.")

    if ponderador is None:
        raise ValidationError("El porcentaje de ponderación es obligatorio.")
    try:
        ponderador_dec = Decimal(str(ponderador))
    except InvalidOperation:
        raise ValidationError("La ponderación debe ser un número válido.")
    if ponderador_dec <= Decimal('0') or ponderador_dec > Decimal('100'):
        raise ValidationError("La ponderación debe ser un valor mayor a 0 y menor o igual a 100.")


def validar_fechas_meta_en_periodo(fecha_inicio, fecha_termino, periodo):
    """
    [HU-05 / KAN-203] Valida coherencia entre fecha_inicio y fecha_termino de la meta
    y que ambas estén dentro del rango del período seleccionado.
    """
    if fecha_inicio and fecha_termino:
        validar_rango_fechas(fecha_inicio, fecha_termino)

    if periodo:
        if fecha_inicio and getattr(periodo, 'fecha_inicio', None) and fecha_inicio < periodo.fecha_inicio:
            raise ValidationError(
                f'La fecha de inicio de la meta no puede ser anterior al inicio del período ({periodo.fecha_inicio.strftime("%d/%m/%Y")}).'
            )
        if fecha_inicio and getattr(periodo, 'fecha_termino', None) and fecha_inicio > periodo.fecha_termino:
            raise ValidationError(
                f'La fecha de inicio de la meta no puede ser posterior al término del período ({periodo.fecha_termino.strftime("%d/%m/%Y")}).'
            )
        if fecha_termino and getattr(periodo, 'fecha_termino', None) and fecha_termino > periodo.fecha_termino:
            raise ValidationError(
                f'La fecha de término de la meta no puede exceder el término del período ({periodo.fecha_termino.strftime("%d/%m/%Y")}).'
            )



def calcular_avance_actividades_aprobadas(meta, profesional=None):
    """
    Contabiliza las actividades activas asociadas a la meta que tengan
    al menos una evidencia activa con estado_revision='APROBADO'.
    """
    if meta is None:
        return Decimal('0.00')

    qs = Actividad.objects.filter(
        id_meta=meta,
        estado=True,
        evidencia__estado=True,
        evidencia__estado_revision='APROBADO',
    )

    if profesional is not None:
        qs = qs.filter(id_profesional=profesional)

    total = qs.distinct().count()
    return Decimal(str(total)).quantize(Decimal('0.01'))


def sincronizar_calculos_indicador(indicador, guardar=True):
    """
    Calcula avance desde actividades aprobadas, aplica el ajuste acumulado
    sobre el cumplimiento base topado en 120%, acota entre 0% y 120%,
    actualiza semáforo y guarda si guardar=True.
    """
    meta = indicador.meta_id_meta
    indicador.avance = calcular_avance_actividades_aprobadas(
        meta,
        profesional=indicador.id_funcionario,
    )
    ajuste_actual = Decimal(str(indicador.ajuste or '0.00')).quantize(Decimal('0.01'))
    indicador.ajuste = ajuste_actual

    if meta and meta.valor_objetivo is not None and Decimal(str(meta.valor_objetivo)) > Decimal('0'):
        cumplimiento_base = calcular_porcentaje_cumplimiento(
            indicador.avance,
            meta.valor_objetivo,
            tope_maximo=Decimal('120.00'),
        )
        cumplimiento_final = max(
            Decimal('0.00'),
            min(cumplimiento_base + ajuste_actual, Decimal('120.00'))
        ).quantize(Decimal('0.01'))
        indicador.cumplimiento = cumplimiento_final

        if getattr(meta, 'id_periodo', None):
            indicador.semaforo = semaforo_segun_umbral(
                indicador.cumplimiento,
                meta.id_periodo,
            )

    if guardar:
        indicador.save()

    return indicador



def filtrar_funcionarios_por_delegacion(user, form, nombre_campo='id_funcionario'):
    """
    Filtra dinámicamente el queryset de un campo de funcionario en el formulario 
    para que solo muestre a los profesionales activos de la delegación del usuario.
    Si el usuario es administrador/coordinador global (sin delegación), ve a todos.
    """
    delegacion = delegacion_del_delegado(user)
    if delegacion is not None and nombre_campo in form.fields:
        form.fields[nombre_campo].queryset = Profesional.objects.filter(
            id_delegacion=delegacion,
            estado=True
        ).order_by('nombres')

def validar_meta_corresponde_a_profesional(profesional, meta):
    """
    Valida que una meta pertenezca al cargo asignado al profesional.
    """
    if not profesional or not meta:
        return meta

    cargo_prof_id = getattr(profesional, 'id_cargo_id', None)
    cargo_meta_id = getattr(getattr(meta, 'id_cargo_item', None), 'id_cargo_id', None)

    if cargo_prof_id and cargo_meta_id and cargo_prof_id != cargo_meta_id:
        raise ValidationError("La meta seleccionada no corresponde al cargo del profesional elegido.")

    return meta
def validar_acceso_observaciones(user, actividad):
    """Regla exclusiva para bitácora de observaciones (HU-24)."""
    from django.core.exceptions import PermissionDenied

    if user.groups.filter(name__in=['Administrador', 'Coordinador']).exists():
        return

    profesional = getattr(user, 'profesional', None)
    creador = getattr(actividad, 'id_profesional', None)

    if profesional is None or creador is None:
        raise PermissionDenied('No tienes permiso para acceder a las observaciones de esta actividad.')

    if user.groups.filter(name='Delegado').exists() and creador.id_delegacion_id == profesional.id_delegacion_id:
        return

    if user.groups.filter(name='Profesional').exists() and creador.pk == profesional.pk:
        return

    raise PermissionDenied('No tienes permiso para acceder a las observaciones de esta actividad.')
