from protocolo.base import CasoProtocolo


class CasoCP10(CasoProtocolo):
    codigo = 'CP-10'
    nombre = 'Evidencias: tipo, tamaño y contenido'

    def test_protocolo(self):
        import os, io, sys

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
        from django.core.files.uploadedfile import SimpleUploadedFile
        from actividadApp.models import Evidencia
        from PIL import Image

        def imagen(nombre='foto.png', fmt='PNG'):
            b = io.BytesIO(); Image.new('RGB', (40, 40), 'red').save(b, fmt)
            return SimpleUploadedFile(nombre, b.getvalue(), content_type='image/' + fmt.lower())

        act = compA.id_actividad
        url = reverse('actividadApp:registrar_evidencia', args=[act.pk])

        def subir(archivo):
            antes = Evidencia.objects.count()
            cA.post(url, {'archivo_foto': archivo})
            return Evidencia.objects.count() > antes

        self.verificar('PNG válida se guarda', subir(imagen()))
        self.verificar('JPG válida se guarda', subir(imagen('foto.jpg', 'JPEG')))
        self.verificar('WEBP válida se guarda', subir(imagen('foto.webp', 'WEBP')))
        self.verificar('PDF válido se guarda', subir(SimpleUploadedFile('respaldo.pdf', b'%PDF-1.4 contenido', content_type='application/pdf')))
        self.verificar('PDF falso se rechaza', not subir(SimpleUploadedFile('falso.pdf', b'no es pdf', content_type='application/pdf')))
        self.verificar('Texto renombrado a .jpg se rechaza', not subir(SimpleUploadedFile('falsa.jpg', b'esto no es una imagen', content_type='image/jpeg')))
        self.verificar('Imagen dañada (PNG cortado) se rechaza', not subir(SimpleUploadedFile('rota.png', imagen().read()[:30], content_type='image/png')))
        self.verificar('Más de 10 MB se rechaza', not subir(SimpleUploadedFile('grande.png', b'0' * (10 * 1024 * 1024 + 10), content_type='image/png')))
        self.verificar('Extensión no permitida (.exe) se rechaza', not subir(SimpleUploadedFile('virus.exe', b'MZ', content_type='application/octet-stream')))

        cAdm.force_login(User.objects.get(username='admin'))
        url_admin = reverse('actividadApp:crear_evidencia')
        h = cAdm.get(url_admin).content.decode()
        self.verificar('Formulario del Administrador muestra el campo actividad', 'name="id_actividad"' in h and act.codigo_unico in h)
        otra = compB.id_actividad
        antes = Evidencia.objects.count()
        r = cAdm.post(url_admin, {'archivo_foto': imagen('admin.png'), 'id_actividad': otra.pk}, follow=True)
        nueva = Evidencia.objects.order_by('-pk').first()
        self.verificar('Administrador crea evidencia con actividad', Evidencia.objects.count() == antes + 1 and nueva.id_actividad_id == otra.pk)
        antes = Evidencia.objects.count()
        cAdm.post(url_admin, {'archivo_foto': imagen('sin.png')})
        self.verificar('Sin actividad no se guarda', Evidencia.objects.count() == antes)
        Evidencia.objects.filter(pk=nueva.pk).update(estado_revision='APROBADO')
        antes = Evidencia.objects.count()
        r = cAdm.post(url_admin, {'archivo_foto': imagen('extra.png'), 'id_actividad': otra.pk})
        self.verificar('No deja agregar evidencias a una actividad ya aprobada', Evidencia.objects.count() == antes and 'ya cuenta con una evidencia' in r.content.decode())
        cAdm.post(url_admin, {'archivo_foto': SimpleUploadedFile('falsa.jpg', b'texto', content_type='image/jpeg'), 'id_actividad': act.pk})
        self.verificar('Administrador tampoco puede subir texto renombrado a .jpg', not Evidencia.objects.filter(metadatos__origen='Panel de Administración Global', id_actividad=act).exists())
        ev = Evidencia.objects.filter(id_actividad=act).first()
        r = cAdm.get(reverse('actividadApp:editar_evidencia', args=[ev.pk]))
        self.verificar('Editar evidencia sigue funcionando', r.status_code == 200 and 'name="id_actividad"' not in r.content.decode())
        self.finalizar()
