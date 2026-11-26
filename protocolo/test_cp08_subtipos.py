from protocolo.base import CasoProtocolo


class CasoCP08(CasoProtocolo):
    codigo = 'CP-08'
    nombre = 'Subtipos de atención'

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
        from actividadApp.models import CatalogoTipoGestion, CatalogoSubtipoGestion, GestionActividad
        visita = CatalogoTipoGestion.objects.create(nombre='Visita a terreno')
        reunion = CatalogoTipoGestion.objects.create(nombre='Reunión')
        url = reverse('administracionApp:gestionar_catalogo')
        cAdm.post(url, {'accion': 'crear', 'tipo': 'subtipo', 'nombre': 'Inspección', 'tipo_gestion': visita.pk})
        self.verificar('Admin crea subtipo', CatalogoSubtipoGestion.objects.filter(nombre='Inspección', tipo_gestion=visita).exists())
        r = cAdm.post(url, {'accion': 'crear', 'tipo': 'subtipo', 'nombre': 'inspección', 'tipo_gestion': visita.pk}, follow=True)
        self.verificar('Rechaza duplicado en el mismo tipo', CatalogoSubtipoGestion.objects.count() == 1 and 'Ya existe el subtipo' in r.content.decode())
        cAdm.post(url, {'accion': 'crear', 'tipo': 'subtipo', 'nombre': 'Inspección', 'tipo_gestion': reunion.pk})
        self.verificar('Permite mismo nombre en otro tipo', CatalogoSubtipoGestion.objects.count() == 2)
        r = cAdm.post(url, {'accion': 'crear', 'tipo': 'subtipo', 'nombre': 'Sin tipo'}, follow=True)
        self.verificar('Exige tipo de gestión', not CatalogoSubtipoGestion.objects.filter(nombre='Sin tipo').exists())
        s1 = CatalogoSubtipoGestion.objects.get(nombre='Inspección', tipo_gestion=visita)
        s2 = CatalogoSubtipoGestion.objects.get(nombre='Inspección', tipo_gestion=reunion)
        cAdm.post(url, {'accion': 'editar', 'tipo': 'subtipo', 'id_obj': s1.pk, 'nombre': 'Inspección técnica', 'tipo_gestion': visita.pk})
        s1.refresh_from_db(); self.verificar('Admin edita subtipo', s1.nombre == 'Inspección técnica')
        cAdm.post(url, {'accion': 'estado', 'tipo': 'subtipo', 'id_obj': s2.pk})
        s2.refresh_from_db(); self.verificar('Admin desactiva subtipo', not s2.estado)
        r = cAdm.get(reverse('administracionApp:panel_catalogos') + '?tab=subtipo'); h = r.content.decode()
        self.verificar('Panel muestra pestaña de subtipos', r.status_code == 200 and 'Subtipos de Gestión' in h and 'Inspección técnica' in h)
        r = cCoo.get(reverse('administracionApp:panel_catalogos')); self.verificar('Coordinador ve el panel', r.status_code == 200)
        r = cA.post(url, {'accion': 'crear', 'tipo': 'subtipo', 'nombre': 'Intruso', 'tipo_gestion': visita.pk})
        self.verificar('Profesional no puede crear subtipos', not CatalogoSubtipoGestion.objects.filter(nombre='Intruso').exists())
        cA.force_login(profA.usuario)
        act = compA.id_actividad
        url_g = reverse('actividadApp:crear_gestion', args=[act.pk])
        h = cA.get(url_g, follow=True).content.decode()
        self.verificar('Formulario muestra subtipos activos', 'Inspección técnica' in h and f'data-tipo="{visita.pk}"' in h)
        self.verificar('Formulario oculta subtipos inactivos', f'value="{s2.pk}" data-tipo' not in h)
        cA.post(url_g, {'tipo_gestion': reunion.pk, 'subtipo_gestion': s1.pk, 'descripcion': 'x'})
        self.verificar('Rechaza subtipo de otro tipo', not GestionActividad.objects.filter(descripcion='x').exists())
        cA.post(url_g, {'tipo_gestion': visita.pk, 'subtipo_gestion': s1.pk, 'descripcion': 'y'})
        g = GestionActividad.objects.filter(descripcion='y').first()
        self.verificar('Guarda gestión con subtipo', g is not None and g.subtipo_gestion_id == s1.pk)
        cA.post(url_g, {'tipo_gestion': reunion.pk, 'descripcion': 'z'})
        self.verificar('Subtipo es opcional', GestionActividad.objects.filter(descripcion='z', subtipo_gestion__isnull=True).exists())
        h = cA.get(reverse('actividadApp:lista_gestiones', args=[act.pk])).content.decode()
        self.verificar('Lista de gestiones muestra el subtipo', 'Inspección técnica' in h)
        h = cA.get(reverse('actividadApp:editar_gestion', args=[g.pk])).content.decode()
        self.verificar('Editar conserva el subtipo seleccionado', f'value="{s1.pk}" data-tipo="{visita.pk}" selected' in h)
        self.finalizar()
