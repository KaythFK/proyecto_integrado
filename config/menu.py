from django.urls import reverse

from .utils import rol_usuario

MENU_POR_ROL = {
    'administrador': [
        ('Inicio', 'house-door', 'administracionApp:dashboard_admin'),
        ('Supervisión', 'shield-check', [
            ('Auditoría', 'journal-text', 'administracionApp:lista_auditoria'),
            ('Roles y permisos', 'shield-lock', 'usuariosApp:lista_roles'),
            ('Reglas de alerta', 'bell', 'monitoreoApp:lista_reglas_alerta'),
            ('Frecuencia de registros', 'activity', 'monitoreoApp:frecuencia_registros'),
            ('Informe de gestión', 'file-earmark-bar-graph', 'monitoreoApp:informe_gestion'),
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
            ('Celebraciones globales', 'calendar-event', 'comunidadApp:lista_celebraciones'),
        ]),
        ('Seguimiento', 'graph-up', [
            ('Metas', 'bullseye', 'monitoreoApp:tablero_metas_coordinador'),
            ('Gestión de indicadores', 'bar-chart-line', 'monitoreoApp:tablero_indicadores_coordinador'),
            ('Tendencias por cargo', 'graph-up-arrow', 'monitoreoApp:tendencias_cargo'),
            ('Frecuencia de registros', 'activity', 'monitoreoApp:frecuencia_registros'),
            ('Informe de gestión', 'file-earmark-bar-graph', 'monitoreoApp:informe_gestion'),
            ('Todas las actividades', 'list-check', 'tuboApp:listar_todas'),
            ('Tubo de cartas', 'envelope-paper', 'tuboApp:lista_cartas'),
        ]),
    ],
    'delegado': [
        ('Mi delegación', 'speedometer2', 'monitoreoApp:dashboard_delegado'),
        ('Mis alertas', 'bell', 'monitoreoApp:mis_alertas'),
        ('Mi equipo', 'people', [
            ('Actividades del equipo', 'clipboard-check', 'actividadApp:actividades_delegacion'),
            ('Tubo de compromisos', 'kanban', 'monitoreoApp:tubo_delegacion'),
            ('Tubo de cartas', 'envelope-paper', 'tuboApp:lista_cartas'),
            ('Revisar evidencias', 'camera', 'actividadApp:lista_evidencias'),
            ('Metas', 'bullseye', 'monitoreoApp:listar_metas'),
            ('Ausencias del equipo', 'calendar-x', 'actividadApp:lista_ausencias'),
            ('Celebraciones locales', 'calendar-check', 'comunidadApp:panel_celebraciones_delegacion'),
            ('Frecuencia de registros', 'activity', 'monitoreoApp:frecuencia_registros'),
            ('Informe de gestión', 'file-earmark-bar-graph', 'monitoreoApp:informe_gestion'),
        ]),
    ],
    'profesional': [
        ('Mi panel', 'speedometer2', 'actividadApp:dashboard_profesional'),
        ('Mis alertas', 'bell', 'monitoreoApp:mis_alertas'),
        ('Mi trabajo', 'briefcase', [
            ('Registrar actividad', 'plus-circle', 'actividadApp:registrar_actividad'),
            ('Mis actividades', 'clipboard-check', 'actividadApp:listar_actividades'),
            ('Mis gestiones', 'list-task', 'actividadApp:mis_gestiones'),
            ('Catalogos', 'book', 'administracionApp:panel_catalogos'),
            ('Mis evidencias', 'camera', 'actividadApp:lista_evidencias'),
            ('Tubo de la delegación', 'kanban', 'monitoreoApp:tubo_delegacion'),
            ('Tubo de cartas', 'envelope-paper', 'tuboApp:lista_cartas'),
            ('Organizaciones Comunitarias', 'diagram-3', 'comunidadApp:lista_organizaciones'),
            ('Vecinos', 'person', 'administracionApp:lista_vecinos'),
            ('Vínculos y Cargas', 'person-hearts', 'comunidadApp:panel_profesional'),
            ('Beneficiarios celebraciones', 'gift', 'comunidadApp:panel_beneficiarios_celebracion'),
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


def _enlaces_del_rol(rol):
    enlaces = []
    for texto, icono, destino in MENU_POR_ROL[rol]:
        if isinstance(destino, list):
            enlaces += [(texto, t, n) for t, i, n in destino]
        else:
            enlaces.append((None, texto, destino))
    if rol == 'administrador':
        from administracionApp.views import SECCIONES_PANEL_ADMIN
        for seccion, tarjetas in SECCIONES_PANEL_ADMIN:
            enlaces += [(seccion, texto, nombre) for texto, descripcion, icono, nombre in tarjetas]
    enlaces.append((None, 'Mi perfil', 'usuariosApp:mi_perfil'))
    return enlaces


def migas_de_pan(rol, vista_actual, ruta):
    """Ruta de navegación: Inicio, la sección del menú y la página actual (si no está en el menú, se toma del título)."""
    inicio_nombre = MENU_POR_ROL[rol][0][2]
    if vista_actual == inicio_nombre:
        return []
    inicio = {'texto': 'Inicio', 'url': reverse(inicio_nombre)}
    enlaces = _enlaces_del_rol(rol)
    exacto = next((e for e in enlaces if e[2] == vista_actual), None)
    if exacto:
        grupo, texto, _ = exacto
        return [inicio] + ([{'texto': grupo}] if grupo else []) + [{'texto': texto, 'actual': True}]
    candidatos = []
    for grupo, texto, nombre in enlaces:
        url = reverse(nombre)
        if nombre != inicio_nombre and url.count('/') > 2 and ruta.startswith(url):
            candidatos.append((len(url), grupo or '', texto, url))
    migas = [inicio]
    if candidatos:
        _, grupo, texto, url = max(candidatos)
        if grupo:
            migas.append({'texto': grupo})
        migas.append({'texto': texto, 'url': url})
    migas.append({'texto': '', 'actual': True, 'desde_titulo': True})
    return migas


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
    ruta = request.path if hasattr(request, 'path') else ''
    return {'menu_lateral': menu, 'migas': migas_de_pan(rol, vista_actual, ruta) if vista_actual else []}
