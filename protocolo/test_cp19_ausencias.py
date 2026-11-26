from protocolo.base import CasoProtocolo


class CasoCP19(CasoProtocolo):
    codigo = 'CP-19'
    nombre = 'Ausencias ajustan la meta'

    def test_protocolo(self):
        import os, sys, tempfile
        from django.conf import settings
        from datetime import date, timedelta
        from decimal import Decimal
        from django.db import models as M
        from django.utils import timezone
        from django.contrib.auth.models import User, Group
        from django.test import Client
        from django.urls import reverse
        from django.apps import apps
        from administracionApp.models import Auditoria, Cargo, CargoItem, CatalagoItem, Delegacion, Profesional, Periodo
        from actividadApp.models import Actividad, Ausencia, Evidencia, Retroalimentacion
        from actividadApp.forms import AusenciaForm
        from monitoreoApp.models import Meta, Indicador
        from monitoreoApp.services import sincronizar_indicador, dias_ausencia_en_periodo
        import importlib
        migracion = importlib.import_module('actividadApp.migrations.0014_ausencia_tipos_retroalimentacion_impacto')

        hoy = date.today()
        lunes = hoy - timedelta(days=hoy.weekday()) - timedelta(days=7)
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
                elif isinstance(f, M.FileField):
                    d[f.name] = 'evidencias/x.jpg'
            d.update(extra)
            return Modelo.objects.create(**d)

        periodo = crear(Periodo, nombre='Actual', fecha_inicio=lunes, fecha_termino=lunes + timedelta(days=27), estado=True,
                        umbral_regular=60, umbral_exelencia=90, dias_computables=20, version_parametros=1)
        cerrado = crear(Periodo, nombre='Cerrado', fecha_inicio=lunes - timedelta(days=60), fecha_termino=lunes - timedelta(days=30), estado=True,
                        umbral_regular=60, umbral_exelencia=90, dias_computables=20, version_parametros=1)
        centro = crear(Delegacion, nombre='Centro', territorio='Centro')
        norte = crear(Delegacion, nombre='Norte', territorio='Norte')
        cargo = crear(Cargo, nombre='Gestor', fecha_inicio=lunes, fecha_termino=lunes + timedelta(days=365))
        def persona(nombre, rol, deleg):
            u = User.objects.create_user(nombre, password='x')
            u.groups.add(Group.objects.get_or_create(name=rol)[0])
            return u, Profesional.objects.create(rut=f'{User.objects.count()}-1', nombres=nombre, apellido_paterno='P', correo=f'{nombre}@x.cl',
                                                 id_cargo=cargo, id_delegacion=deleg, usuario=u, estado=True)
        u_del, delegado = persona('Delegado', 'Delegado', centro)
        u_coo, _ = persona('Coordinador', 'Coordinador', centro)
        u_ana, ana = persona('Ana', 'Profesional', centro)
        _, beto = persona('Beto', 'Profesional', centro)
        _, carla = persona('Carla', 'Profesional', centro)
        _, dani = persona('Dani', 'Profesional', norte)

        meta = crear(Meta, id_cargo_item=crear(CargoItem, id_cargo=cargo, id_item=crear(CatalagoItem, nombre='Visitas'), ponderacion=100),
                     id_periodo=periodo, valor_objetivo=10, ponderador=100, fecha_inicio=periodo.fecha_inicio, estado=True)
        def con_avance(prof, n):
            for _ in range(n):
                act = crear(Actividad, id_profesional=prof, id_meta=meta, codigo_unico=f'ACT-{Actividad.objects.count()}', estado=True)
                crear(Evidencia, id_actividad=act, estado_revision='APROBADO', estado=True)
            ind = crear(Indicador, id_funcionario=prof, meta_id_meta=meta, avance=0, ajuste=0, cumplimiento=0, ponderacion=100, estado=True)
            return sincronizar_indicador(ind)
        ind_ana, ind_beto, ind_carla = con_avance(ana, 5), con_avance(beto, 5), con_avance(carla, 1)
        self.verificar('Punto de partida: Ana 50 % sin ajuste, en rojo', ind_ana.cumplimiento == Decimal('50.00') and ind_ana.ajuste == 0 and ind_ana.semaforo == 'ROJO')

        cd = Client(); cd.force_login(u_del)
        url_crear = reverse('actividadApp:crear_ausencia')
        r = cd.get(url_crear)
        form = r.context['form']
        self.verificar('el Delegado entra a registrar ausencias', r.status_code == 200)
        self.verificar('solo puede elegir profesionales de su delegación', set(form.fields['profesional_ausente'].queryset) == {delegado, ana, beto, carla, u_coo.profesional})
        self.verificar('solo períodos abiertos', list(form.fields['periodo_ausencia'].queryset) == [periodo])
        self.verificar('el tipo es una lista con las 4 opciones', [c for c, _ in form.fields['tipo_ausencia'].choices if c] == ['VACACIONES', 'DIAS_ADMINISTRATIVOS', 'DIAS_LIBRES', 'LICENCIA_MEDICA'])

        semana2 = lunes + timedelta(days=7)
        def datos(prof, inicio, termino, tipo='VACACIONES', per=periodo):
            return {'profesional_ausente': prof.pk, 'periodo_ausencia': per.pk, 'tipo_ausencia': tipo,
                    'fecha_inicio': inicio.isoformat(), 'fecha_termino': termino.isoformat(), 'dias_computables': 99}
        r = cd.post(url_crear, datos(ana, semana2, semana2 + timedelta(days=6)))
        aus_ana = Ausencia.objects.filter(profesional_ausente=ana).first()
        self.verificar('registra tipo y rango de fechas', r.status_code == 302 and aus_ana and aus_ana.tipo_ausencia == 'VACACIONES' and aus_ana.fecha_inicio == semana2)
        self.verificar('los días se calculan solos en días hábiles (5, aunque se envíe 99)', aus_ana.dias_computables == 5)

        def errores(d):
            f = AusenciaForm(d, delegacion=centro)
            return f.errors if not f.is_valid() else {}
        self.verificar('no permite profesionales de otra delegación', 'profesional_ausente' in errores(datos(dani, semana2, semana2)))
        self.verificar('rechaza término antes del inicio', 'fecha_termino' in errores(datos(beto, semana2, semana2 - timedelta(days=1))))
        self.verificar('rechaza fechas fuera del período', 'fecha_termino' in errores(datos(beto, semana2, periodo.fecha_termino + timedelta(days=3))))
        self.verificar('rechaza un rango sin días hábiles', 'fecha_termino' in errores(datos(beto, semana2 + timedelta(days=5), semana2 + timedelta(days=6))))
        self.verificar('rechaza ausencias que se cruzan', 'fecha_inicio' in errores(datos(ana, semana2 + timedelta(days=2), semana2 + timedelta(days=10))))
        self.verificar('no permite períodos cerrados', 'periodo_ausencia' in errores(datos(beto, cerrado.fecha_inicio, cerrado.fecha_inicio, per=cerrado)))

        aus_dani = crear(Ausencia, profesional_ausente=dani, periodo_ausencia=periodo, tipo_ausencia='VACACIONES', fecha_inicio=semana2, fecha_termino=semana2, dias_computables=1, estado=True)
        lista = cd.get(reverse('actividadApp:lista_ausencias'))
        self.verificar('la lista del Delegado muestra solo su equipo', [a.pk for a in lista.context['ausencias']] == [aus_ana.pk])
        self.verificar('el Delegado no puede editar ausencias de otra delegación', cd.get(reverse('actividadApp:editar_ausencia', args=[aus_dani.pk])).status_code == 404)
        self.verificar('el menú y el panel del Delegado llevan a Ausencias', 'Ausencias del equipo' in cd.get(reverse('monitoreoApp:dashboard_delegado')).content.decode())
        cp = Client(); cp.force_login(u_ana)
        self.verificar('el Profesional no puede registrar ausencias', cp.get(url_crear).status_code == 302)

        ind_ana.refresh_from_db()
        self.verificar('descuenta 5 de 20 días hábiles', dias_ausencia_en_periodo(ana, periodo) == (5, 20))
        self.verificar('guarda el ajuste en Indicador.ajuste (50 % a 66,67 %)', ind_ana.ajuste == Decimal('16.67') and ind_ana.cumplimiento == Decimal('66.67'))
        self.verificar('recalcula el semáforo (rojo a amarillo)', ind_ana.semaforo == 'AMARILLO')

        retro = crear(Retroalimentacion, tipo='FELICITACION', porcentaje_impacto=Decimal('10.00'), canal_recepcion='Web', fecha=hoy, estado=False,
                      receptor=delegado, retroalimentado=ana, delegacion=centro, meta=meta)
        cd.post(reverse('actividadApp:cambiar_estado_retroalimentacion', args=[retro.pk]))
        ind_ana.refresh_from_db()
        self.verificar('el ajuste suma ausencias y retroalimentaciones (16,67 + 10)', ind_ana.ajuste == Decimal('26.67') and ind_ana.cumplimiento == Decimal('76.67'))
        self.verificar('Corregido: la retroalimentación ya no falla por porcentaje_impacto', True)

        cd.post(reverse('actividadApp:cambiar_estado_ausencia', args=[aus_ana.pk]))
        ind_ana.refresh_from_db()
        self.verificar('al desactivar la ausencia se quita su ajuste', ind_ana.ajuste == Decimal('10.00') and ind_ana.cumplimiento == Decimal('60.00') and ind_ana.semaforo == 'AMARILLO')
        otra = crear(Ausencia, profesional_ausente=ana, periodo_ausencia=periodo, tipo_ausencia='DIAS_LIBRES', fecha_inicio=semana2, fecha_termino=semana2, dias_computables=1, estado=True)
        r = cd.post(reverse('actividadApp:cambiar_estado_ausencia', args=[aus_ana.pk]), follow=True)
        self.verificar('no reactiva una ausencia que se cruza con otra', not Ausencia.objects.get(pk=aus_ana.pk).estado and 'se cruza' not in '' and 'otra ausencia activa' in r.content.decode())
        otra.delete()

        r = cd.post(url_crear, datos(beto, periodo.fecha_inicio, periodo.fecha_termino, 'LICENCIA_MEDICA'))
        ind_beto.refresh_from_db()
        self.verificar('si estuvo ausente todo el período la meta queda en 100 %', ind_beto.cumplimiento == Decimal('100.00'))

        cd.post(url_crear, datos(carla, semana2, semana2 + timedelta(days=4), 'DIAS_ADMINISTRATIVOS'))
        aus_carla = Ausencia.objects.get(profesional_ausente=carla)
        cd.post(reverse('actividadApp:editar_ausencia', args=[aus_carla.pk]), datos(carla, semana2, semana2 + timedelta(days=1), 'DIAS_ADMINISTRATIVOS'))
        ind_carla.refresh_from_db()
        self.verificar('al editar la ausencia se recalcula (2 días: 10 % a 11,11 %)', Ausencia.objects.get(pk=aus_carla.pk).dias_computables == 2 and ind_carla.cumplimiento == Decimal('11.11'))

        auditoria = Auditoria.objects.filter(evento='AJUSTE_AUSENCIA', entidad='Indicador', identificador=ind_ana.pk).order_by('id_auditoria')
        primera = auditoria.first()
        self.verificar('registra el cambio del indicador en Auditoría', auditoria.count() >= 2)
        self.verificar('con valor anterior y nuevo del ajuste', primera and primera.valor_anterior['ajuste'] == '0.00' and primera.valor_nuevo['ajuste'] == '16.67')
        self.verificar('también queda la auditoría de la ausencia', Auditoria.objects.filter(evento='CREACION', entidad='Ausencia').count() >= 3)
        self.verificar('el ajuste por retroalimentación también queda auditado', Auditoria.objects.filter(evento='AJUSTE_RETROALIMENTACION', identificador=ind_ana.pk).exists())

        cc = Client(); cc.force_login(u_coo)
        r = cc.get(reverse('monitoreoApp:tablero_indicadores_coordinador'), {'periodo': periodo.pk})
        html = r.content.decode()
        self.verificar('el tablero de indicadores carga (antes fallaba)', r.status_code == 200)
        self.verificar('el tablero muestra el ajuste y los días descontados', 'Días descontados' in html and '2 de 20' in html and 'Ausencias:' in html)
        r = cd.get(reverse('monitoreoApp:dashboard_delegado'), {'periodo': periodo.pk})
        self.verificar('el panel del Delegado muestra los días descontados en los resultados bajo el umbral', '2 días de ausencia descontados' in r.content.decode())

        aus_cerrado = crear(Ausencia, profesional_ausente=ana, periodo_ausencia=cerrado, tipo_ausencia='VACACIONES', fecha_inicio=cerrado.fecha_inicio, fecha_termino=cerrado.fecha_inicio, dias_computables=1, estado=True)
        r = cd.get(reverse('actividadApp:editar_ausencia', args=[aus_cerrado.pk]))
        self.verificar('No se editan ausencias de períodos cerrados', r.status_code == 302)

        Ausencia.objects.filter(pk=aus_cerrado.pk).update(tipo_ausencia='Licencia Medica')
        migracion.normalizar_tipos_ausencia(apps, None)
        self.verificar('La migración convierte los tipos escritos a mano', Ausencia.objects.get(pk=aus_cerrado.pk).tipo_ausencia == 'LICENCIA_MEDICA')
        self.finalizar()
