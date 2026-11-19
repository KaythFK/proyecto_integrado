from django.urls import reverse

from .utils import rol_usuario

MENU_POR_ROL = {
    'administrador': [
        ('Inicio', 'house-door', 'administracionApp:dashboard_admin'),
        ('Supervisión', 'shield-check', [
            ('Auditoría', 'journal-text', 'administracionApp:lista_auditoria'),
            ('Reglas de alerta', 'bell', 'monitoreoApp:lista_reglas_alerta'),
        ]),
    ],
    'coordinador': [
        ('Visión global', 'globe2', 'tuboApp:dashboard_coordinador'),
        ('Mis alertas', 'bell', 'monitoreoApp:mis_alertas'),
        ('Configuración', 'gear', [
            ('Delegaciones', 'building', 'administracionApp:delegaciones'),
            ('Períodos', 'calendar-range', 'administracionApp:lista_periodos'),
            ('Cargos', 'briefcase', 'administracionApp:lista_cargos'),
            ('Catálogos', 'book', 'administracionApp:panel_catalogos'),
        ]),
        ('Seguimiento', 'graph-up', [
            ('Metas', 'bullseye', 'monitoreoApp:tablero_metas_coordinador'),
            ('Gestión de indicadores', 'bar-chart-line', 'monitoreoApp:tablero_indicadores_coordinador'),
            ('Todas las actividades', 'list-check', 'tuboApp:listar_todas'),
        ]),
    ],
    'delegado': [
        ('Mi delegación', 'speedometer2', 'monitoreoApp:dashboard_delegado'),
        ('Mis alertas', 'bell', 'monitoreoApp:mis_alertas'),
        ('Mi equipo', 'people', [
            ('Actividades del equipo', 'clipboard-check', 'actividadApp:actividades_delegacion'),
            ('Tubo de compromisos', 'kanban', 'monitoreoApp:tubo_delegacion'),
            ('Revisar evidencias', 'camera', 'actividadApp:lista_evidencias'),
            ('Metas', 'bullseye', 'monitoreoApp:listar_metas'),
        ]),
    ],
    'profesional': [
        ('Mi panel', 'speedometer2', 'actividadApp:dashboard_profesional'),
        ('Mi trabajo', 'briefcase', [
            ('Registrar actividad', 'plus-circle', 'actividadApp:registrar_actividad'),
            ('Mis actividades', 'clipboard-check', 'actividadApp:listar_actividades'),
            ('Mis gestiones', 'list-task', 'actividadApp:mis_gestiones'),
            ('Mis evidencias', 'camera', 'actividadApp:lista_evidencias'),
        ]),
    ],
}


def _enlace(texto, icono, nombre_url, vista_actual):
    return {'texto': texto, 'icono': icono, 'url': reverse(nombre_url) if nombre_url else '#',
            'activo': nombre_url == vista_actual}


def alertas_pendientes(request):
    from monitoreoApp.models import Alerta
    from monitoreoApp.services import generar_alertas_periodicamente
    generar_alertas_periodicamente()
    profesional = getattr(request.user, 'profesional', None)
    if profesional is None:
        return 0
    return Alerta.objects.filter(id_destinatario=profesional, estado=True, revision=False).count()


def menu_lateral(request):
    rol = rol_usuario(request)['rol_menu']
    if rol not in MENU_POR_ROL:
        return {'menu_lateral': []}
    coincidencia = getattr(request, 'resolver_match', None)
    vista_actual = coincidencia.view_name if coincidencia else None
    menu = []
    for texto, icono, destino in MENU_POR_ROL[rol]:
        if isinstance(destino, list):
            hijos = [_enlace(t, i, n, vista_actual) for t, i, n in destino]
            menu.append({'texto': texto, 'icono': icono, 'hijos': hijos, 'abierto': any(h['activo'] for h in hijos)})
        else:
            enlace = _enlace(texto, icono, destino, vista_actual)
            if destino == 'monitoreoApp:mis_alertas':
                enlace['contador'] = alertas_pendientes(request)
            menu.append(enlace)
    menu.append(_enlace('Mi perfil', 'person-circle', 'usuariosApp:mi_perfil', vista_actual))
    return {'menu_lateral': menu}
