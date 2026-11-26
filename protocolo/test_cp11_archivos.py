import os

from protocolo.base import CasoProtocolo


class CasoCP11(CasoProtocolo):
    codigo = 'CP-11'
    nombre = 'Acceso a archivos subidos'

    def test_protocolo(self):
        import os, sys
        from datetime import date
        from django.conf import settings
        from django.db import models as M
        from django.utils import timezone
        from django.contrib.auth.models import User, Group
        from django.test import Client
        from administracionApp.models import Cargo, Delegacion, Profesional
        from actividadApp.models import Actividad, Evidencia, Retroalimentacion

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

        def archivo(ruta, contenido):
            completa = os.path.join(settings.MEDIA_ROOT, ruta)
            os.makedirs(os.path.dirname(completa), exist_ok=True)
            open(completa, 'wb').write(contenido)

        archivo('evidencias/foto_a.jpg', b'FOTO-A')
        archivo('evidencias/foto_b.jpg', b'FOTO-B')
        archivo('evidencias/huerfana.jpg', b'SIN-REGISTRO')
        archivo('retroalimentaciones/reclamo_a.jpg', b'RECLAMO-A')
        archivo('fotos_perfil/perfil.png', b'PERFIL')
        archivo('otra_carpeta/secreto.txt', b'SECRETO')

        d1 = crear(Delegacion, nombre='Centro', territorio='Centro')
        d2 = crear(Delegacion, nombre='Norte', territorio='Norte')
        cargo = crear(Cargo, nombre='Gestor')
        def persona(nombre, rol, i, deleg):
            u = User.objects.create_user(nombre, password='x')
            u.groups.add(Group.objects.get_or_create(name=rol)[0])
            return u, Profesional.objects.create(rut=f'1{i}-1', nombres=nombre, apellido_paterno='P', correo=f'{nombre}@x.cl',
                                                 id_cargo=cargo, id_delegacion=deleg, usuario=u, estado=True)
        u_a, p_a = persona('prof_a', 'Profesional', 1, d1)
        u_b, p_b = persona('prof_b', 'Profesional', 2, d2)
        u_d1, p_d1 = persona('delegado_1', 'Delegado', 3, d1)
        u_c, _ = persona('coord', 'Coordinador', 4, d1)
        u_adm, _ = persona('admin', 'Administrador', 5, d1)

        for prof, ruta in ((p_a, 'evidencias/foto_a.jpg'), (p_b, 'evidencias/foto_b.jpg')):
            act = crear(Actividad, id_profesional=prof)
            Evidencia.objects.bulk_create([Evidencia(id_actividad=act, archivo_foto=ruta, estado=True)])
        crear(Retroalimentacion, tipo='RECLAMO', archivo_respaldo='retroalimentaciones/reclamo_a.jpg', receptor=p_d1,
              retroalimentado=p_a, delegacion=d1, fecha=hoy)

        A, B, R, P = '/media/evidencias/foto_a.jpg', '/media/evidencias/foto_b.jpg', '/media/retroalimentaciones/reclamo_a.jpg', '/media/fotos_perfil/perfil.png'

        anon = Client()
        self.verificar('Sin sesión no se puede abrir ninguna foto (redirige al login)',
           all(anon.get(u).status_code == 302 and '/usuarios/login/' in anon.get(u).url for u in (A, B, R, P)))

        def cliente(u):
            c = Client(); c.force_login(u); return c

        casos = [
            ('Profesional A', u_a, {A: 200, B: 403, R: 200, P: 200}),
            ('Profesional B', u_b, {A: 403, B: 200, R: 403, P: 200}),
            ('Delegado de Centro', u_d1, {A: 200, B: 403, R: 200, P: 200}),
            ('Coordinador', u_c, {A: 200, B: 200, R: 200, P: 200}),
            ('Administrador', u_adm, {A: 200, B: 200, R: 200, P: 200}),
        ]
        for nombre, u, esperado in casos:
            c = cliente(u)
            obtenido = {ruta: c.get(ruta).status_code for ruta in esperado}
            self.verificar(f'{nombre}: {[(r.split("/")[-1], obtenido[r]) for r in esperado]}', obtenido == esperado)

        c = cliente(u_a)
        r = c.get(A)
        self.verificar('Entrega el contenido real del archivo', b''.join(r.streaming_content) == b'FOTO-A')
        self.verificar('No queda guardado en caché del navegador', 'no-store' in r['Cache-Control'])
        self.verificar('Archivo sin registro asociado: 404', c.get('/media/evidencias/huerfana.jpg').status_code == 404)
        self.verificar('Otra carpeta de media: 404', cliente(u_adm).get('/media/otra_carpeta/secreto.txt').status_code == 404)
        self.verificar('No permite salir de la carpeta media', cliente(u_adm).get('/media/fotos_perfil/../../config/settings.py').status_code in (404, 403, 400))
        self.verificar('Archivo inexistente: 404', c.get('/media/fotos_perfil/no_existe.png').status_code == 404)
        self.finalizar()
