from protocolo.base import CasoProtocolo


class CasoCP12(CasoProtocolo):
    codigo = 'CP-12'
    nombre = 'Bloqueo después de la aprobación'

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
        from actividadApp.models import Evidencia, CatalogoTipoGestion, GestionActividad
        from PIL import Image
        def foto():
            b = io.BytesIO(); Image.new('RGB', (20, 20), 'red').save(b, 'JPEG'); return SimpleUploadedFile('a.jpg', b.getvalue(), content_type='image/jpeg')
        act = compA.id_actividad
        otra = compB.id_actividad
        ev = Evidencia.objects.create(archivo_foto=foto(), id_actividad=act, estado_revision='APROBADO')
        tipo = CatalogoTipoGestion.objects.create(nombre='Visita')
        g = GestionActividad.objects.create(actividad=act, tipo_gestion=tipo, descripcion='d', profesional=profA)
        _, cDel2 = usuario('delegadoB', 'Delegado', d2, 9)
        def bloqueado(nombre, cliente, metodo, url, datos=None, antes=None):
            act.refresh_from_db(); previo = (act.solicitud_problema, act.estado, act.estado_progreso)
            r = getattr(cliente, metodo)(url, datos or {}, follow=True)
            act.refresh_from_db()
            msg = 'ya fue aprobada y no se puede modificar' in r.content.decode()
            self.verificar(f'{nombre}: bloqueado con aviso', msg and (act.solicitud_problema, act.estado, act.estado_progreso) == previo)
        R = reverse
        bloqueado('Profesional editar', cA, 'post', R('actividadApp:editar_actividad', args=[act.pk]), {'solicitud_problema': 'CAMBIO', 'accion': 'x'})
        bloqueado('Profesional editar (abrir)', cA, 'get', R('actividadApp:editar_actividad', args=[act.pk]))
        bloqueado('Profesional desactivar', cA, 'get', R('actividadApp:desactivar_actividad', args=[act.codigo_unico]))
        bloqueado('Profesional progreso', cA, 'post', R('actividadApp:actualizar_progreso_actividad', args=[act.pk]), {'nuevo_estado': 'FINALIZADA'})
        bloqueado('Delegado editar', cDel, 'post', R('actividadApp:editar_actividad_delegado', args=[act.pk]), {'solicitud_problema': 'CAMBIO'})
        bloqueado('Delegado desactivar', cDel, 'post', R('actividadApp:cambiar_estado_actividad_delegado', args=[act.pk]))
        bloqueado('Admin editar', cAdm, 'post', R('administracionApp:editar_actividad', args=[act.pk]), {'solicitud_problema': 'CAMBIO'})
        bloqueado('Admin desactivar', cAdm, 'post', R('administracionApp:desactivar_actividad', args=[act.pk]))
        bloqueado('Admin progreso', cAdm, 'post', R('administracionApp:actualizar_progreso_actividad', args=[act.pk]), {'nuevo_estado': 'FINALIZADA'})
        bloqueado('Coordinador desactivar', cCoo, 'post', R('actividadApp:cambiar_estado_actividad_coordinador', args=[act.pk]))
        n = GestionActividad.objects.count()
        bloqueado('Crear gestión', cA, 'post', R('actividadApp:crear_gestion', args=[act.pk]), {'tipo_gestion': tipo.pk, 'descripcion': 'nueva'})
        self.verificar('Crear gestión: no se creó', GestionActividad.objects.count() == n)
        bloqueado('Editar gestión', cA, 'post', R('actividadApp:editar_gestion', args=[g.pk]), {'tipo_gestion': tipo.pk, 'descripcion': 'otra'})
        g.refresh_from_db(); self.verificar('Editar gestión: sin cambios', g.descripcion == 'd')
        bloqueado('Desactivar gestión', cA, 'post', R('actividadApp:cambiar_estado_gestion', args=[g.pk]))
        g.refresh_from_db(); self.verificar('Desactivar gestión: sigue activa', g.estado)
        bloqueado('Editar evidencia aprobada', cAdm, 'post', R('actividadApp:editar_evidencia', args=[ev.pk]), {'estado_revision': 'PENDIENTE', 'id_actividad': act.pk})
        ev.refresh_from_db(); self.verificar('Evidencia sigue aprobada', ev.estado_revision == 'APROBADO')
        bloqueado('Desactivar evidencia', cAdm, 'post', R('actividadApp:cambiar_estado_evidencia', args=[ev.pk]))
        ev.refresh_from_db(); self.verificar('Evidencia sigue activa', ev.estado)
        compA.refresh_from_db(); previo = compA.estado_progreso
        bloqueado('Tubo progreso (Profesional)', cA, 'post', R('tuboApp:actualizar_progreso_tubo', args=[compA.pk]), {'nuevo_estado': 'EN_PROCESO'})
        bloqueado('Tubo progreso (Delegado)', cDel, 'post', R('tuboApp:actualizar_progreso_tubo', args=[compA.pk]), {'nuevo_estado': 'EN_PROCESO'})
        compA.refresh_from_db(); self.verificar('Compromiso sin cambios', compA.estado_progreso == previo)
        bloqueado('Tubo desactivar (Admin)', cAdm, 'post', R('tuboApp:cambiar_estado_tubo', args=[compA.pk]))
        compA.refresh_from_db(); self.verificar('Compromiso sigue activo', compA.estado)
        evB = Evidencia.objects.create(archivo_foto=foto(), id_actividad=otra)
        r = cA.post(R('actividadApp:editar_evidencia', args=[evB.pk]), {'estado_revision': 'APROBADO', 'id_actividad': otra.pk})
        self.verificar('Profesional no edita evidencia ajena (403)', r.status_code == 403)
        r = cB.get(R('actividadApp:editar_actividad', args=[otra.pk])); self.verificar('No aprobada: se puede abrir editar', r.status_code == 200)
        r = cB.post(R('actividadApp:actualizar_progreso_actividad', args=[otra.pk]), {'nuevo_estado': 'EN_PROCESO'}); otra.refresh_from_db()
        self.verificar('No aprobada: cambia progreso', otra.estado_progreso == 'EN_PROCESO')
        h = cA.get(R('actividadApp:listar_actividades')).content.decode()
        self.verificar('Lista Profesional: muestra "Aprobada"', 'bi-lock-fill' in h)
        self.verificar('Lista Profesional: oculta Registrar evidencia', R('actividadApp:registrar_evidencia', args=[act.pk]) not in h)
        h = cDel.get(R('actividadApp:actividades_delegacion')).content.decode()
        self.verificar('Lista Delegado: oculta Editar', R('actividadApp:editar_actividad_delegado', args=[act.pk]) not in h)
        h = cAdm.get(R('administracionApp:admin-actividades')).content.decode()
        self.verificar('Lista Admin: oculta Editar de la aprobada', R('administracionApp:editar_actividad', args=[act.pk]) not in h)
        self.verificar('Lista Admin: muestra Editar de la no aprobada', R('administracionApp:editar_actividad', args=[otra.pk]) in h)
        r = cCoo.get(R('tuboApp:listar_todas')); self.verificar('Lista Coordinador responde 200', r.status_code == 200)
        self.finalizar()
