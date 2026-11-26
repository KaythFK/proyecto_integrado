from protocolo.base import CasoProtocolo


class CasoCP22(CasoProtocolo):
    codigo = 'CP-22'
    nombre = 'Página de inicio y redirección por rol'

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
        from django.test import Client
        anon = Client()
        r = anon.get('/'); h = r.content.decode()
        self.verificar('Raíz sin sesión responde 200', r.status_code == 200)
        for texto in ['Uso exclusivo de funcionarios municipales', 'Sistema de Gestión de Resultados', 'La Serena informa', 'carruselMunicipal',
                      'Sobre el sistema', 'Cómo funciona', 'Entrega informes trazables', 'El acceso queda registrado']:
            self.verificar(f'Muestra "{texto}"', texto in h)
        self.verificar('Botón lleva al login', 'href="/usuarios/login/"' in h and 'Ingresar al sistema' in h)
        self.verificar('Sin sección de roles', 'Profesional' not in h and 'Coordinador' not in h)
        for cliente, rol, destino in [(cAdm, 'Administrador', R('administracionApp:dashboard_admin')), (cDel, 'Delegado', R('monitoreoApp:dashboard_delegado')),
                                      (cA, 'Profesional', R('actividadApp:dashboard_profesional')), (cCoo, 'Coordinador', R('tuboApp:dashboard_coordinador'))]:
            h = cliente.get('/').content.decode()
            self.verificar(f'{rol} con sesión: "Ir a mi panel" a su panel', 'Ir a mi panel' in h and f'href="{destino}"' in h)
            r = cliente.get(R('usuariosApp:login'))
            self.verificar(f'{rol} con sesión que abre el login va a su panel', r.status_code == 302 and r['Location'] == destino)
            r = cliente.get(destino)
            self.verificar(f'{rol} sigue con sesión en su panel', r.status_code == 200)
        h = cAdm.get(R('administracionApp:dashboard_admin')).content.decode()
        self.verificar('Panel del Administrador ya no tiene carrusel', 'carruselMunicipal' not in h)
        self.finalizar()
