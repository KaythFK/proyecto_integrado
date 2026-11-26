from protocolo.base import CasoProtocolo


class CasoCP14(CasoProtocolo):
    codigo = 'CP-14'
    nombre = 'Búsqueda dinámica en el Tubo'

    def test_protocolo(self):
        import os, sys
        from datetime import date, timedelta
        from django.db import models as M
        from django.utils import timezone
        from django.contrib.auth.models import User, Group
        from django.test import Client
        from django.urls import reverse
        from administracionApp.models import Cargo, Delegacion, Profesional, Vecino
        from actividadApp.models import Actividad
        from tuboApp.models import Compromiso

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

        centro = crear(Delegacion, nombre='Centro', territorio='Centro')
        norte = crear(Delegacion, nombre='Norte', territorio='Norte')
        cargo = crear(Cargo, nombre='Gestor')
        def persona(nombre, rol, i, deleg, rut=None, ap='P'):
            u = User.objects.create_user(nombre, password='x')
            u.groups.add(Group.objects.get_or_create(name=rol)[0])
            return u, Profesional.objects.create(rut=rut or f'1{i}-1', nombres=nombre, apellido_paterno=ap, correo=f'{nombre}@x.cl',
                                                 id_cargo=cargo, id_delegacion=deleg, usuario=u, estado=True)
        u_del, _ = persona('delegado', 'Delegado', 1, centro)
        u_adm, _ = persona('admin', 'Administrador', 2, centro)
        _, ana = persona('Ana', 'Profesional', 3, centro)
        _, beto = persona('Beto', 'Profesional', 4, norte)
        _, colega = persona('Rocío', 'Profesional', 5, centro, rut='9.876.543-K', ap='Muñoz')

        juan = crear(Vecino, rut='12.345.678-5', nombres='Juan Andrés', apellido_paterno='Pérez', apellido_materno='Soto', telefono='1', correo='j@x.cl')
        maria = crear(Vecino, rut='15.111.222-3', nombres='María', apellido_paterno='González', apellido_materno='Rojas', telefono='1', correo='m@x.cl')

        def compromiso(prof, codigo, **solicitante):
            act = crear(Actividad, id_profesional=prof, codigo_unico=codigo, solicitud_problema='Bache en la calle', **solicitante)
            return crear(Compromiso, id_funcionario=prof, id_actividad=act, fecha_comprometida=hoy + timedelta(days=5), territorio='Centro', estado=True)
        c_juan = compromiso(ana, 'ACT-2026-AAA111', solicitante_vecino=juan)
        c_maria = compromiso(ana, 'ACT-2026-BBB222', solicitante_vecino=maria)
        c_colega = compromiso(ana, 'ACT-2026-CCC333', solicitante_profesional=colega)
        c_norte = compromiso(beto, 'ACT-2026-DDD444', solicitante_vecino=juan)

        def ids(cliente, url, q):
            return sorted(c.pk for c in cliente.get(url, {'q': q}).context['compromisos'])

        cd = Client(); cd.force_login(u_del)
        url_d = reverse('monitoreoApp:tubo_delegacion')
        self.verificar('Por código', ids(cd, url_d, 'bbb222') == [c_maria.pk])
        for rut in ['12.345.678-5', '12345678-5', '123456785', '12345678', '345.678']:
            self.verificar(f'Por RUT del vecino escrito como "{rut}"', ids(cd, url_d, rut) == [c_juan.pk])
        self.verificar('Por RUT de un profesional solicitante con K minúscula', ids(cd, url_d, '9876543-k') == [c_colega.pk])
        self.verificar('Por nombre', ids(cd, url_d, 'maría') == [c_maria.pk])
        self.verificar('Por apellido', ids(cd, url_d, 'gonzález') == [c_maria.pk])
        self.verificar('Por nombre y apellido juntos', ids(cd, url_d, 'Juan Pérez') == [c_juan.pk])
        self.verificar('Por nombre de un profesional solicitante', ids(cd, url_d, 'Rocío Muñoz') == [c_colega.pk])
        self.verificar('Sigue buscando por problema y territorio', ids(cd, url_d, 'bache') == sorted([c_juan.pk, c_maria.pk, c_colega.pk]))
        self.verificar('Sin coincidencias devuelve vacío', ids(cd, url_d, 'zzzz') == [])
        self.verificar('El delegado no ve compromisos de otra delegación', c_norte.pk not in ids(cd, url_d, 'Juan'))
        self.verificar('La búsqueda se combina con los demás filtros', [c.pk for c in cd.get(url_d, {'q': 'Juan', 'estado': 'REALIZADO'}).context['compromisos']] == [])

        ca = Client(); ca.force_login(u_adm)
        url_a = reverse('tuboApp:tubo')
        self.verificar('Tubo del administrador busca por RUT en todas las delegaciones', ids(ca, url_a, '12345678') == sorted([c_juan.pk, c_norte.pk]))
        self.verificar('Tubo del administrador busca por nombre', ids(ca, url_a, 'maría gonz') == [c_maria.pk])
        self.verificar('RUT inexistente no devuelve resultados', ids(cd, url_d, '99.999.999-9') == [])
        self.verificar('El delegado no encuentra por código un compromiso de otra delegación', ids(cd, url_d, 'ddd444') == [])
        inyeccion = cd.get(url_d, {'q': "' OR 1=1 --"})
        self.verificar('Texto con caracteres especiales no falla ni devuelve todo', inyeccion.status_code == 200 and list(inyeccion.context['compromisos']) == [])
        self.verificar('Búsqueda vacía muestra todos los compromisos de la delegación y ninguno ajeno',
                       ids(cd, url_d, '') == sorted([c_juan.pk, c_maria.pk, c_colega.pk]))
        for cliente, url in ((cd, url_d), (ca, url_a)):
            html = cliente.get(url).content.decode()
            self.verificar(f'{url}: el buscador filtra al escribir', 'data-busqueda-dinamica' in html and 'campo.form.submit()' in html
               and 'Código, RUT o nombre del solicitante' in html)
        self.finalizar()
