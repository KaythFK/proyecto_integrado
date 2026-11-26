from protocolo.base import CasoProtocolo


class CasoCP07(CasoProtocolo):
    codigo = 'CP-07'
    nombre = 'Matriz de ítems por cargo'

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
        from datetime import date
        from administracionApp.models import CatalagoItem, CargoItem
        from monitoreoApp.models import Meta

        R = reverse
        cAdm.force_login(User.objects.get(username='admin'))
        i1 = CatalagoItem.objects.create(nombre='Reuniones', estado=True)
        i2 = CatalagoItem.objects.create(nombre='Visitas', estado=True)
        ci1 = CargoItem.objects.create(id_cargo=cargo, id_item=i1, ponderacion=60, estado=True)
        ci2 = CargoItem.objects.create(id_cargo=cargo, id_item=i2, ponderacion=40, estado=True)
        meta = crear(Meta, id_cargo_item=ci1)
        url = R('administracionApp:configurar_matriz_cargo', args=[cargo.pk])
        hoy = date.today().isoformat()

        r = cAdm.post(url, {'fecha_inicio': hoy, 'fecha_termino': '2027-12-31', f'ponderacion_{i1.pk}': '70', f'ponderacion_{i2.pk}': '30'})
        self.verificar('Cambiar ponderaciones con metas asociadas no da error', r.status_code == 302)
        ci1.refresh_from_db(); self.verificar('El ítem conserva su identificador y la meta sigue apuntándolo', ci1.ponderacion == 70 and Meta.objects.get(pk=meta.pk).id_cargo_item_id == ci1.pk)

        r = cAdm.post(url, {'fecha_inicio': hoy, 'fecha_termino': '2027-12-31', f'ponderacion_{i2.pk}': '100'})
        self.verificar('Quitar un ítem que tiene metas no da error', r.status_code == 302)
        ci1.refresh_from_db(); ci2.refresh_from_db()
        self.verificar('El ítem quitado queda desactivado, no borrado', CargoItem.objects.filter(pk=ci1.pk).exists() and not ci1.estado)
        self.verificar('La meta sigue apuntando a un ítem existente', Meta.objects.filter(pk=meta.pk, id_cargo_item_id=ci1.pk).exists())
        self.verificar('El otro ítem queda con 100', ci2.estado and ci2.ponderacion == 100)

        h = cAdm.get(R('administracionApp:lista_cargos')).content.decode()
        self.verificar('La lista de cargos muestra solo ítems activos', 'Visitas' in h and 'Reuniones' not in h)

        r = cAdm.post(url, {'fecha_inicio': hoy, 'fecha_termino': '2027-12-31', f'ponderacion_{i1.pk}': '50', f'ponderacion_{i2.pk}': '50'})
        ci1.refresh_from_db()
        self.verificar('Volver a agregar el ítem lo reactiva sin duplicarlo', ci1.estado and ci1.ponderacion == 50 and CargoItem.objects.filter(id_cargo=cargo, id_item=i1).count() == 1)
        self.finalizar()
