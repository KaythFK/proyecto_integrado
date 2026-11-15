from django.core.exceptions import ValidationError
from datetime import date

from django.db import models

from administracionApp.models import Delegacion
from django.db.models import Q



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
    """Entrega rol_menu a todas las plantillas para el menú lateral de base.html."""
    usuario = getattr(request, 'user', None)
    if not usuario or not usuario.is_authenticated:
        return {'rol_menu': None}

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
    return {'rol_menu': rol}
