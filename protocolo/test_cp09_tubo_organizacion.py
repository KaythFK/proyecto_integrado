from protocolo.base import CasoProtocolo


class CasoCP09(CasoProtocolo):
    codigo = 'CP-09'
    nombre = 'Actividad con ingreso opcional al Tubo'

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
        from actividadApp.forms import ActividadProfesionalForm, ActividadForm, ActividadDelegadoForm, MENSAJE_TUBO_SIN_ORGANIZACION
        act = compA.id_actividad
        base = {'solicitud_problema': 's', 'accion': 'a', 'id_meta': act.id_meta_id, 'fecha_comprometida': '2026-12-10', 'id_profesional': profA.pk}
        def errores(form):
            form.is_valid(); return form.errors.get('id_organizacion', [])
        uP = profA.usuario
        for nombre, crear_form in [('Profesional', lambda d: ActividadProfesionalForm(d, usuario_actual=uP)),
                                   ('Administrador', lambda d: ActividadForm(d)),
                                   ('Delegado', lambda d: ActividadDelegadoForm(d, delegacion=d1))]:
            self.verificar(f'{nombre}: Tubo sin organización da error', MENSAJE_TUBO_SIN_ORGANIZACION in errores(crear_form({**base, 'en_tubo': 'on'})))
            self.verificar(f'{nombre}: sin Tubo y sin organización no da ese error', MENSAJE_TUBO_SIN_ORGANIZACION not in errores(crear_form(dict(base))))
            org.id_delegacion = d1; org.estado = True; org.save()
            self.verificar(f'{nombre}: Tubo con organización no da ese error', MENSAJE_TUBO_SIN_ORGANIZACION not in errores(crear_form({**base, 'en_tubo': 'on', 'id_organizacion': org.pk})))
        from actividadApp.models import Actividad
        antes = Actividad.objects.count()
        r = cA.post(reverse('actividadApp:registrar_actividad'), {**base, 'en_tubo': 'on'})
        self.verificar('POST profesional sin organización: no da 500', r.status_code == 200)
        self.verificar('POST profesional sin organización: no guarda actividad', Actividad.objects.count() == antes)
        self.verificar('POST muestra el mensaje', MENSAJE_TUBO_SIN_ORGANIZACION in r.content.decode())
        self.finalizar()
