from protocolo.base import CasoProtocolo


class CasoCP13(CasoProtocolo):
    codigo = 'CP-13'
    nombre = 'Tubo de cartas por delegación'

    def test_protocolo(self):
        import os, sys

        from django.core.management import call_command
        from django.contrib.auth.models import User, Group
        from django.test import Client
        from django.urls import reverse
        from django.db import models as M
        from administracionApp.models import Cargo, Delegacion, Profesional
        from actividadApp.models import Actividad
        from tuboApp.models import Compromiso
        from monitoreoApp.models import Meta
        from comunidadApp.models import OrganizacionComunitaria
        def crear(Modelo, **extra):
            d = {}
            for f in Modelo._meta.concrete_fields:
                if f.primary_key or f.has_default() or f.name in extra or f.null: continue
                if isinstance(f, M.ForeignKey): d[f.name] = crear(f.related_model)
                elif getattr(f, 'choices', None): d[f.name] = f.choices[0][0]
                elif isinstance(f, (M.CharField, M.TextField)): d[f.name] = 'x%d' % Modelo.objects.count()
                elif isinstance(f, (M.IntegerField, M.DecimalField)): d[f.name] = 1
                elif isinstance(f, M.DateField): d[f.name] = '2026-01-01'
            d.update(extra); return Modelo.objects.create(**d)
        cargo = crear(Cargo); d1 = crear(Delegacion); d2 = crear(Delegacion)
        def usuario(nombre, rol, deleg, n):
            u = User.objects.create_user(nombre, password='x'); u.groups.add(Group.objects.get_or_create(name=rol)[0])
            p = Profesional.objects.create(rut=f'{n}-1', nombres=nombre, apellido_paterno='P', correo=f'{nombre}@p.cl', id_cargo=cargo, id_delegacion=deleg, usuario=u)
            c = Client(); c.force_login(u); return p, c
        profA, cA = usuario('profA', 'Profesional', d1, 1)
        profB, cB = usuario('profB', 'Profesional', d2, 2)
        _, cDel = usuario('delegado1', 'Delegado', d1, 3)
        _, cAdm = usuario('admin', 'Administrador', d2, 4)
        _, cCoo = usuario('coord', 'Coordinador', d2, 5)
        org = crear(OrganizacionComunitaria)
        def compromiso(prof):
            act = crear(Actividad, id_profesional=prof, id_meta=crear(Meta), id_organizacion=org)
            return Compromiso.objects.create(territorio='t', fecha_comprometida='2026-12-01', id_funcionario=prof, id_actividad=act, organizacion=org)
        compA, compB = compromiso(profA), compromiso(profB)

        from django.conf import settings
        from datetime import date, timedelta
        from tuboApp.models import CartaTubo
        from administracionApp.models import Auditoria

        def relogin():
            for c, u in [(cA, 'profA'), (cB, 'profB'), (cDel, 'delegado1'), (cAdm, 'admin'), (cCoo, 'coord'), (cA2, 'profA2')]:
                c.force_login(User.objects.get(username=u))

        profA2, cA2 = usuario('profA2', 'Profesional', d1, 7)
        R = reverse
        hoy = date.today().isoformat()
        base = {'fecha_recepcion': hoy, 'numero_oficina_partes': '10093', 'destinatario': 'ALCALDESA', 'remitente': 'Junta Vecinal Norte',
                'telefono_contacto': '912345678', 'tema': 'Solicita apoyo para operativo', 'estado_carta': 'EN_PROCESO'}

        cA.post(R('tuboApp:crear_carta'), {**base, 'encargado': profA.pk})
        c1 = CartaTubo.objects.first()
        self.verificar('Profesional registra carta', c1 is not None and c1.delegacion_id == d1.pk and c1.registrado_por_id == profA.pk)
        self.verificar('Código automático CAR-', c1 is not None and c1.codigo.startswith(f'CAR-{date.today().year}-'))
        self.verificar('Queda en auditoría', Auditoria.objects.filter(entidad='CartaTubo', evento='CREACION').exists())
        cA.post(R('tuboApp:crear_carta'), {**base, 'encargado': profB.pk})
        self.verificar('Rechaza encargado de otra delegación', CartaTubo.objects.count() == 1)
        r = cA.post(R('tuboApp:crear_carta'), {**base, 'encargado': profA.pk, 'fecha_recepcion': (date.today() + timedelta(days=2)).isoformat()})
        self.verificar('Rechaza fecha de recepción futura', CartaTubo.objects.count() == 1 and 'no puede ser futura' in r.content.decode())
        cA.post(R('tuboApp:crear_carta'), {**base, 'encargado': profA.pk, 'telefono_contacto': 'abc'})
        self.verificar('Rechaza teléfono inválido', CartaTubo.objects.count() == 1)
        cA.post(R('tuboApp:crear_carta'), {**base, 'encargado': profA.pk, 'fecha_actividad': (date.today() - timedelta(days=3)).isoformat()})
        self.verificar('Rechaza actividad antes de la recepción', CartaTubo.objects.count() == 1)
        h = cA.get(R('tuboApp:crear_carta')).content.decode()
        self.verificar('Profesional no ve la opción Aprobada', 'value="APROBADA"' not in h)
        cA.post(R('tuboApp:crear_carta'), {**base, 'encargado': profA.pk, 'estado_carta': 'APROBADA'})
        self.verificar('Profesional no puede aprobar', CartaTubo.objects.count() == 1)

        cB.post(R('tuboApp:crear_carta'), {**base, 'encargado': profB.pk, 'remitente': 'Club Deportivo Sur'})
        c2 = CartaTubo.objects.get(remitente='Club Deportivo Sur')
        h = cA.get(R('tuboApp:lista_cartas')).content.decode()
        self.verificar('Profesional ve cartas de su delegación', c1.codigo in h)
        self.verificar('Profesional no ve cartas de otra delegación', c2.codigo not in h)
        h = cA2.get(R('tuboApp:lista_cartas')).content.decode()
        self.verificar('Compañero de la delegación también la ve', c1.codigo in h)
        self.verificar('Compañero no tiene botón Editar', R('tuboApp:editar_carta', args=[c1.pk]) not in h)
        cA2.post(R('tuboApp:editar_carta', args=[c1.pk]), {**base, 'encargado': profA.pk, 'remitente': 'CAMBIO AJENO'})
        c1.refresh_from_db(); self.verificar('Compañero no puede editar carta ajena', c1.remitente == 'Junta Vecinal Norte')
        r = cA.get(R('tuboApp:editar_carta', args=[c2.pk])); self.verificar('Otra delegación: 404', r.status_code == 404)
        cA.post(R('tuboApp:editar_carta', args=[c1.pk]), {**base, 'encargado': profA.pk, 'observacion': 'Se llamó al remitente'})
        c1.refresh_from_db(); self.verificar('Encargado edita su carta', c1.observacion == 'Se llamó al remitente')
        cDel.post(R('tuboApp:editar_carta', args=[c1.pk]), {**base, 'encargado': profA2.pk, 'estado_carta': 'APROBADA', 'pronunciamiento': 'Delegado'})
        c1.refresh_from_db(); self.verificar('Delegado aprueba y reasigna', c1.estado_carta == 'APROBADA' and c1.encargado_id == profA2.pk)
        relogin()
        cA.post(R('tuboApp:editar_carta', args=[c1.pk]), {**base, 'encargado': profA.pk, 'remitente': 'TRAS APROBAR'})
        c1.refresh_from_db(); self.verificar('Aprobada: quien la registró ya no puede editar', c1.remitente == 'Junta Vecinal Norte')
        cA2.post(R('tuboApp:editar_carta', args=[c1.pk]), {**base, 'encargado': profA2.pk, 'remitente': 'TRAS APROBAR'})
        c1.refresh_from_db(); self.verificar('Aprobada: tampoco el nuevo encargado', c1.remitente == 'Junta Vecinal Norte')
        h = cA.get(R('tuboApp:lista_cartas')).content.decode()
        self.verificar('Lista muestra "Cerrada"', 'Cerrada' in h)
        cDel.post(R('tuboApp:editar_carta', args=[c1.pk]), {**base, 'encargado': profA2.pk, 'estado_carta': 'APROBADA', 'remitente': 'Corrección delegado'})
        c1.refresh_from_db(); self.verificar('Delegado puede corregir una aprobada', c1.remitente == 'Corrección delegado')
        cDel.post(R('tuboApp:cambiar_estado_carta', args=[c1.pk]))
        c1.refresh_from_db(); self.verificar('Delegado desactiva carta', not c1.estado)
        cA.post(R('tuboApp:cambiar_estado_carta', args=[c2.pk]))
        relogin()
        c2.refresh_from_db(); self.verificar('Profesional no puede desactivar', c2.estado)

        h = cCoo.get(R('tuboApp:lista_cartas')).content.decode()
        self.verificar('Coordinador ve todas las delegaciones', c1.codigo in h and c2.codigo in h)
        self.verificar('Coordinador no puede registrar', R('tuboApp:crear_carta') not in h)
        h = cAdm.get(R('tuboApp:lista_cartas') + f'?delegacion={d2.pk}').content.decode()
        self.verificar('Admin filtra por delegación', c2.codigo in h and c1.codigo not in h)
        h = cAdm.get(R('tuboApp:lista_cartas') + '?q=club').content.decode()
        self.verificar('Búsqueda por remitente', c2.codigo in h and c1.codigo not in h)
        h = cAdm.get(R('tuboApp:lista_cartas') + f'?q={c1.codigo[-6:]}').content.decode()
        self.verificar('Búsqueda por código', c1.codigo in h and c2.codigo not in h)
        h = cAdm.get(R('tuboApp:lista_cartas') + '?estado_carta=APROBADA').content.decode()
        self.verificar('Filtro por estado', c1.codigo in h and c2.codigo not in h)
        h = cAdm.get(R('tuboApp:lista_cartas') + f'?encargado={profB.pk}').content.decode()
        self.verificar('Filtro por encargado', c2.codigo in h and c1.codigo not in h)
        ayer = (date.today() - timedelta(days=1)).isoformat()
        h = cAdm.get(R('tuboApp:lista_cartas') + f'?hasta={ayer}').content.decode()
        self.verificar('Filtro por rango de fechas', c1.codigo not in h and c2.codigo not in h)
        cAdm.post(R('tuboApp:crear_carta'), {**base, 'delegacion': d2.pk, 'encargado': profB.pk, 'remitente': 'Desde admin'})
        self.verificar('Admin registra eligiendo delegación', CartaTubo.objects.filter(remitente='Desde admin', delegacion=d2).exists())
        for c, n in [(cA, 'Profesional'), (cDel, 'Delegado'), (cCoo, 'Coordinador')]:
            h = c.get(R('tuboApp:lista_cartas')).content.decode()
            self.verificar(f'Menú de {n} incluye Tubo de cartas', 'Tubo de cartas' in h)
        h = cAdm.get(R('administracionApp:dashboard_admin')).content.decode()
        self.verificar('Panel del Administrador incluye Tubo de cartas', 'Tubo de cartas' in h)
        self.finalizar()
