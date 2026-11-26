from protocolo.base import CasoProtocolo


class CasoCP21(CasoProtocolo):
    codigo = 'CP-21'
    nombre = 'Paginación y filtros'

    def test_protocolo(self):
        import os, sys, re

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
        from administracionApp.models import Vecino, Periodo
        from comunidadApp.models import AfiliacionVecino
        from actividadApp.models import CatalogoTipoGestion, GestionActividad

        R = reverse
        act = compA.id_actividad
        vecino = crear(Vecino, nombres='Ana', telefono='912345678')
        AfiliacionVecino.objects.create(vecino=vecino, organizacion=org, cargo_organizacion='Socia')
        GestionActividad.objects.create(actividad=act, tipo_gestion=CatalogoTipoGestion.objects.create(nombre='Visita'), descripcion='d', profesional=profA)

        import re
        from comunidadApp.models import OrganizacionComunitaria
        for i in range(30):
            crear(OrganizacionComunitaria, nombre=f'Org {i:02d}')
        total_orgs = OrganizacionComunitaria.objects.count()
        h = re.sub(r'<[^>]+>', '', cAdm.get(R('comunidadApp:lista_organizaciones')).content.decode())
        self.verificar('Página 1 muestra 25 y el total', f'Mostrando 1–25 de {total_orgs}' in h)
        h2 = re.sub(r'<[^>]+>', '', cAdm.get(R('comunidadApp:lista_organizaciones') + '?page=2').content.decode())
        self.verificar('Página 2 muestra el resto', f'Mostrando 26–{total_orgs} de {total_orgs}' in h2)
        h3 = re.sub(r'<[^>]+>', '', cAdm.get(R('comunidadApp:lista_organizaciones') + '?q=Org+0&page=1').content.decode())
        self.verificar('La búsqueda se mantiene al paginar', 'Mostrando 1–10 de 10' in h3)
        h4 = cAdm.get(R('comunidadApp:lista_organizaciones') + '?q=Org').content.decode()
        self.verificar('Enlace Siguiente conserva el filtro', '?q=Org&amp;page=2' in h4 or '?q=Org&page=2' in h4)
        sin_resultados = cAdm.get(R('comunidadApp:lista_organizaciones') + '?q=zzzz')
        self.verificar('Búsqueda sin coincidencias no muestra paginación ni falla',
                       sin_resultados.status_code == 200 and 'Mostrando' not in re.sub(r'<[^>]+>', '', sin_resultados.content.decode()))
        h5 = re.sub(r'<[^>]+>', '', cAdm.get(R('comunidadApp:lista_organizaciones') + '?page=99').content.decode())
        self.verificar('Página fuera de rango (99) muestra la última página sin error', f'Mostrando 26–{total_orgs} de {total_orgs}' in h5)
        h6 = re.sub(r'<[^>]+>', '', cAdm.get(R('comunidadApp:lista_organizaciones') + '?page=abc').content.decode())
        self.verificar('Número de página inválido (abc) muestra la primera página sin error', f'Mostrando 1–25 de {total_orgs}' in h6)
        h7 = re.sub(r'<[^>]+>', '', cAdm.get(R('comunidadApp:lista_organizaciones') + '?page=-1').content.decode())
        self.verificar('Número de página negativo muestra la última página sin error', f'Mostrando 26–{total_orgs} de {total_orgs}' in h7)
        for nombre in ['comunidadApp:lista_afiliaciones', 'administracionApp:lista_vecinos', 'administracionApp:admin-actividades', 'tuboApp:lista_cartas']:
            r = cAdm.get(R(nombre)); self.verificar(f'{nombre} responde 200 con paginación', r.status_code == 200)
        self.finalizar()
