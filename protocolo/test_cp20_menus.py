from protocolo.base import CasoProtocolo


class CasoCP20(CasoProtocolo):
    codigo = 'CP-20'
    nombre = 'Menús de acciones estandarizados'

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

        paginas = [
            ('Administrador', cAdm, R('administracionApp:admin-actividades'), ['Editar', 'Gestiones', 'Observaciones']),
            ('Administrador', cAdm, R('comunidadApp:lista_afiliaciones'), ['Organización', 'Editar']),
            ('Administrador', cAdm, R('comunidadApp:lista_organizaciones'), ['Nómina', 'Editar']),
            ('Administrador', cAdm, R('administracionApp:lista_periodos'), ['Versionar', 'Extender']),
            ('Administrador', cAdm, R('administracionApp:lista_vecinos'), ['Ficha', 'Editar']),
            ('Administrador', cAdm, R('monitoreoApp:listar_metas'), ['Ver detalle', 'Editar']),
            ('Coordinador', cCoo, R('monitoreoApp:tablero_metas_coordinador'), ['Ver detalle', 'Editar', 'Historial']),
            ('Profesional', cA, R('actividadApp:lista_gestiones', args=[act.pk]), ['Editar', 'Ver actividad']),
            ('Profesional', cA, R('actividadApp:mis_gestiones'), ['Editar', 'Ver actividad']),
            ('Administrador', cAdm, R('comunidadApp:detalle_organizacion', args=[org.pk]), ['Ficha vecino', 'Editar']),
        ]
        for rol, cliente, url, opciones in paginas:
            r = cliente.get(url)
            h = r.content.decode()
            cuerpo = re.search(r'<tbody>(.*?)</tbody>', h, re.S)
            cuerpo = cuerpo.group(1) if cuerpo else ''
            items = [re.sub(r'<[^>]+>|\s+', ' ', x).strip() for x in re.findall(r'<li>(.*?)</li>', cuerpo, re.S)]
            nombre = url.strip('/').replace('/', ' › ')
            self.verificar(f'{rol} {nombre}: responde 200', r.status_code == 200)
            self.verificar(f'{rol} {nombre}: menú Acciones', 'dropdown-toggle' in cuerpo)
            self.verificar(f'{rol} {nombre}: opciones {opciones}', all(any(o in i for i in items) for o in opciones))
            self.verificar(f'{rol} {nombre}: interruptor con confirmación', 'role="switch"' in cuerpo)
            celdas = [c for c in re.findall(r'<td class="text-center[^"]*">(.*?)</td>', cuerpo, re.S) if 'role="switch"' in c]
            self.verificar(f'{rol} {nombre}: celda de acciones sin botones sueltos', celdas and not any(re.search(r'class="btn btn-sm (?!text-white px-3 shadow-sm fondo-guinda dropdown-toggle)', c) for c in celdas))

        r = cA.get(R('administracionApp:lista_vecinos')); h = r.content.decode()
        if r.status_code == 200:
            cuerpo = re.search(r'<tbody>(.*?)</tbody>', h, re.S).group(1)
            self.verificar('Vecinos sin ser Administrador: solo botón Ficha, sin menú', 'dropdown-toggle' not in cuerpo and 'Ficha' in cuerpo)

        h = cA.get(R('actividadApp:mis_gestiones')).content.decode()
        self.verificar('El Profesional no ve opciones de Administrador en sus listados', 'Versionar' not in h and 'Extender' not in h)
        r = cA.get(R('administracionApp:lista_periodos'))
        self.verificar('El Profesional no puede abrir un listado del Administrador', r.status_code in (302, 403))
        cA.force_login(User.objects.get(username='profA'))
        r = cCoo.get(R('administracionApp:admin-actividades'))
        self.verificar('El Coordinador no puede abrir el listado de actividades del Administrador', r.status_code in (302, 403))
        self.finalizar()
