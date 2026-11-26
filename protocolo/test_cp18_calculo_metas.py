from decimal import Decimal

from django.contrib.auth.models import Group, User

from actividadApp.models import Actividad, Evidencia
from administracionApp.models import Cargo, Delegacion, Profesional
from comunidadApp.models import OrganizacionComunitaria
from monitoreoApp.models import Indicador, Meta
from monitoreoApp.services import sincronizar_indicador
from protocolo.base import CasoProtocolo
from protocolo.datos import crear


class CasoCP18(CasoProtocolo):
    codigo = 'CP-18'
    nombre = 'Cálculo de metas y tope de 120 %'

    def test_protocolo(self):
        cargo, delegacion = crear(Cargo), crear(Delegacion)

        def persona(nombre, rol, rut):
            usuario = User.objects.create_user(nombre, password='x')
            usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
            return Profesional.objects.create(rut=rut, nombres=nombre, apellido_paterno='P', correo=f'{nombre}@p.cl',
                                              id_cargo=cargo, id_delegacion=delegacion, usuario=usuario)

        profesional = persona('profesional', 'Profesional', '1-9')
        delegado = persona('delegado', 'Delegado', '2-7')
        organizacion = crear(OrganizacionComunitaria)
        meta = crear(Meta)
        Meta.objects.filter(pk=meta.pk).update(valor_objetivo=4)
        meta.refresh_from_db()

        def actividad(estado_revision='APROBADO', **extra):
            registro = crear(Actividad, id_profesional=profesional, id_meta=meta, id_organizacion=organizacion, **extra)
            Evidencia.objects.bulk_create([Evidencia(archivo_foto='evidencias/prueba.png', estado_revision=estado_revision, id_actividad=registro)])

        indicador = Indicador.objects.create(avance=0, cumplimiento=0, ponderacion=0, ajuste=0, meta_id_meta=meta, id_funcionario=profesional)

        def cumplimiento():
            sincronizar_indicador(indicador)
            indicador.refresh_from_db()
            return indicador.cumplimiento

        actividad()
        actividad()
        self.verificar('Dos actividades aprobadas de una meta de 4: 50 %', cumplimiento() == Decimal('50.00'))
        actividad(estado_revision='PENDIENTE')
        self.verificar('Evidencia pendiente no suma', cumplimiento() == Decimal('50.00'))
        actividad(estado_revision='RECHAZADO')
        self.verificar('Evidencia rechazada no suma', cumplimiento() == Decimal('50.00'))
        actividad(es_coordinacion_preparatoria=True)
        self.verificar('Coordinación preparatoria aprobada no suma', cumplimiento() == Decimal('50.00'))
        actividad(solicitante_profesional=delegado)
        self.verificar('Solicitud cuyo solicitante es el delegado no suma', cumplimiento() == Decimal('50.00'))
        for _ in range(4):
            actividad()
        self.verificar('Seis aprobadas de una meta de 4 (150 %) quedan topadas en 120 %', cumplimiento() == Decimal('120.00'))
        self.verificar('Semáforo en verde con 120 %', indicador.semaforo == 'VERDE')
        self.finalizar()
