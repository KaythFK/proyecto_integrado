from protocolo.base import CasoProtocolo


class CasoCP15(CasoProtocolo):
    codigo = 'CP-15'
    nombre = 'Límite diario de siete actividades'

    def test_protocolo(self):
        import os, sys, re
        from datetime import date, timedelta
        from decimal import Decimal
        from django.db import models as M
        from django.utils import timezone
        from django.contrib.auth.models import User, Group
        from django.test import Client
        from django.urls import reverse
        from administracionApp.models import Cargo, Delegacion, Profesional, Periodo, CatalagoItem, CargoItem
        from actividadApp.models import Actividad, Evidencia
        from monitoreoApp.models import Meta, Indicador
        from config.utils import sincronizar_calculos_indicador

        hoy = date.today()

        def crear(Modelo, **extra):
            d = {}
            for f in Modelo._meta.concrete_fields:
                if f.primary_key or f.has_default() or f.name in extra or f.null or f.blank:
                    continue
                if isinstance(f, M.ForeignKey):
                    d[f.name] = crear(f.related_model)
                elif getattr(f, 'choices', None):
                    d[f.name] = f.choices[0][0]
                elif isinstance(f, (M.CharField, M.TextField)):
                    d[f.name] = 'Texto %d' % Modelo.objects.count()
                elif isinstance(f, (M.IntegerField, M.DecimalField)):
                    d[f.name] = 1
                elif isinstance(f, M.DateTimeField):
                    d[f.name] = timezone.now()
                elif isinstance(f, M.DateField):
                    d[f.name] = hoy
            d.update(extra)
            return Modelo.objects.create(**d)

        deleg = crear(Delegacion, nombre='Delegación Centro', territorio='Centro')
        otra = crear(Delegacion, nombre='Delegación Norte', territorio='Norte')
        cargo = crear(Cargo, nombre='Gestor Territorial')
        def persona(nombre, rol, i, delegacion=deleg):
            u = User.objects.create_user(nombre, password='x')
            u.groups.add(Group.objects.get_or_create(name=rol)[0])
            return u, Profesional.objects.create(rut=f'1{i}-1', nombres=nombre, apellido_paterno='P', correo=f'{nombre}@x.cl',
                                                 id_cargo=cargo, id_delegacion=delegacion, usuario=u, estado=True)
        u_del, p_del = persona('delegado', 'Delegado', 1)
        _, p_lento = persona('Lento', 'Profesional', 2)
        _, p_bien = persona('Bueno', 'Profesional', 3)
        _, p_ajeno = persona('Ajeno', 'Profesional', 4, otra)
        periodo = Periodo.objects.create(nombre='P', fecha_inicio=hoy - timedelta(days=30), fecha_termino=hoy + timedelta(days=60),
                                         umbral_exelencia=90, umbral_regular=60, dias_computables=60, version_parametros=1, estado=True)
        ci = CargoItem.objects.create(id_cargo=cargo, id_item=crear(CatalagoItem, nombre='Visitas'), ponderacion=100)
        meta = Meta.objects.create(valor_objetivo=10, unidad='visitas', ponderador=100, id_cargo_item=ci, id_periodo=periodo,
                                   fecha_inicio=periodo.fecha_inicio)

        def actividades(prof, n, aprobadas=True):
            lista = []
            for _ in range(n):
                a = crear(Actividad, id_profesional=prof, id_meta=meta)
                Evidencia.objects.bulk_create([Evidencia(id_actividad=a, archivo_foto='evidencias/x.jpg',
                                                         estado_revision='APROBADO' if aprobadas else 'PENDIENTE', estado=True)])
                lista.append(a)
            return lista

        def indicador(prof):
            i = Indicador.objects.create(meta_id_meta=meta, id_funcionario=prof, avance=0, cumplimiento=0, ponderacion=100, ajuste=0, estado=True)
            sincronizar_calculos_indicador(i)
            return i

        from django.core.exceptions import ValidationError
        from config.utils import validar_tope_diario_actividades
        from actividadApp.filters import ActividadFilter
        for _ in range(6):
            crear(Actividad, id_profesional=p_bien, id_meta=meta)
        ayer = crear(Actividad, id_profesional=p_bien, id_meta=meta)
        Actividad.objects.filter(pk=ayer.pk).update(fecha_registro=timezone.now() - timedelta(days=1))
        try:
            validar_tope_diario_actividades(p_bien); pasa6 = True
        except ValidationError:
            pasa6 = False
        self.verificar('Con 6 actividades hoy (y 1 de ayer) todavía puede registrar', pasa6)
        crear(Actividad, id_profesional=p_bien, id_meta=meta)
        try:
            validar_tope_diario_actividades(p_bien); bloquea = False
        except ValidationError as e:
            bloquea = 'tope máximo de 7' in str(e)
        self.verificar('Con 7 actividades hoy se bloquea la octava', bloquea)
        qs = Actividad.objects.filter(id_profesional=p_bien)
        self.verificar('Filtro Desde/Hasta de hoy trae 7', ActividadFilter({'desde': hoy, 'hasta': hoy}, queryset=qs).qs.count() == 7)
        self.verificar('Filtro de ayer trae 1', ActividadFilter({'desde': hoy - timedelta(days=1), 'hasta': hoy - timedelta(days=1)}, queryset=qs).qs.count() == 1)
        self.finalizar()
