from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse

from actividadApp.models import Actividad, Evidencia
from administracionApp.models import Cargo, CargoItem, CatalagoItem, Delegacion, Periodo, Profesional
from comunidadApp.models import OrganizacionComunitaria
from monitoreoApp.models import Indicador, Meta
from monitoreoApp.services import sincronizar_indicador
from protocolo.base import CasoProtocolo
from protocolo.datos import crear
from tuboApp.models import Compromiso


class CasoCP28(CasoProtocolo):
    codigo = 'CP-28'
    nombre = 'Compromisos realizados del Tubo alimentan el indicador'

    def test_protocolo(self):
        hoy = date.today()
        cargo, delegacion = crear(Cargo), crear(Delegacion)

        def persona(nombre, rol, rut):
            usuario = User.objects.create_user(nombre, password='x')
            usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
            return usuario, Profesional.objects.create(rut=rut, nombres=nombre, apellido_paterno='P', correo=f'{nombre}@p.cl',
                                                       id_cargo=cargo, id_delegacion=delegacion, usuario=usuario)

        _, profesional = persona('profesional', 'Profesional', '1-9')
        u_delegado, _ = persona('delegado', 'Delegado', '2-7')
        u_admin, _ = persona('admin', 'Administrador', '3-5')
        organizacion = crear(OrganizacionComunitaria)
        periodo = Periodo.objects.create(nombre='Q4 2026', fecha_inicio=hoy - timedelta(days=30), fecha_termino=hoy + timedelta(days=60),
                                         dias_computables=60, estado=True, umbral_regular=60, umbral_exelencia=90, version_parametros=1)
        item = CatalagoItem.objects.create(nombre='Compromisos vecinales', cuenta_compromisos=True)
        cargo_item = CargoItem.objects.create(id_cargo=cargo, id_item=item, ponderacion=100, estado=True)
        meta = Meta.objects.create(valor_objetivo=4, unidad='compromisos', ponderador=100, id_cargo_item=cargo_item,
                                   id_periodo=periodo, fecha_inicio=periodo.fecha_inicio)
        indicador = Indicador.objects.create(avance=0, cumplimiento=0, ponderacion=100, ajuste=0, meta_id_meta=meta, id_funcionario=profesional)

        def actividad(estado_compromiso, aprobada=False, **extra):
            registro = crear(Actividad, id_profesional=profesional, id_meta=meta, id_organizacion=organizacion, **extra)
            compromiso = Compromiso.objects.create(territorio='Centro', fecha_comprometida=hoy, id_funcionario=profesional,
                                                   id_actividad=registro, organizacion=organizacion, estado_progreso=estado_compromiso)
            if aprobada:
                Evidencia.objects.bulk_create([Evidencia(archivo_foto='evidencias/prueba.png', estado_revision='APROBADO', id_actividad=registro)])
            return compromiso

        def avance():
            sincronizar_indicador(indicador)
            indicador.refresh_from_db()
            return indicador.avance

        actividad('REALIZADO')
        self.verificar('Un compromiso realizado suma 1 al avance cuando el ítem lo configura', avance() == Decimal('1'))
        actividad('REALIZADO', aprobada=True)
        self.verificar('Una actividad con compromiso realizado y evidencia aprobada suma una sola vez', avance() == Decimal('2'))
        actividad('EN_PROCESO')
        self.verificar('Un compromiso en proceso no suma', avance() == Decimal('2'))
        actividad('REALIZADO', es_coordinacion_preparatoria=True)
        self.verificar('Un compromiso realizado de una coordinación preparatoria no suma', avance() == Decimal('2'))
        self.verificar('El cumplimiento refleja los compromisos (2 de 4 = 50 %)', indicador.cumplimiento == Decimal('50.00'))

        pendiente = actividad('PENDIENTE')
        cliente_delegado = Client()
        cliente_delegado.force_login(u_delegado)
        cliente_delegado.post(reverse('tuboApp:actualizar_progreso_tubo', args=[pendiente.pk]), {'nuevo_estado': 'REALIZADO'})
        indicador.refresh_from_db()
        self.verificar('Al marcar un compromiso como realizado desde el Tubo el indicador se recalcula solo', indicador.avance == Decimal('3'))

        CatalagoItem.objects.filter(pk=item.pk).update(cuenta_compromisos=False)
        meta.refresh_from_db()
        self.verificar('Si el ítem no lo configura, solo suman las evidencias aprobadas', avance() == Decimal('1'))

        cliente_admin = Client()
        cliente_admin.force_login(u_admin)
        url = reverse('administracionApp:gestionar_catalogo')
        cliente_admin.post(url, {'accion': 'crear', 'tipo': 'item', 'nombre': 'Atenciones derivadas', 'cuenta_compromisos': 'on'})
        nuevo = CatalagoItem.objects.filter(nombre='Atenciones derivadas').first()
        self.verificar('El Administrador crea un ítem que suma compromisos', nuevo is not None and nuevo.cuenta_compromisos)
        cliente_admin.post(url, {'accion': 'editar', 'tipo': 'item', 'id_obj': nuevo.pk, 'nombre': 'Atenciones derivadas'})
        nuevo.refresh_from_db()
        self.verificar('Al editar sin marcar la opción, el ítem deja de sumar compromisos', not nuevo.cuenta_compromisos)
        self.finalizar()
