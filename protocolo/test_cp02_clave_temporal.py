from protocolo.base import CasoProtocolo


class CasoCP02(CasoProtocolo):
    codigo = 'CP-02'
    nombre = 'Contraseña temporal y cambio obligatorio'

    def test_protocolo(self):
        import os, sys, re
        from datetime import date
        from django.db import models as M
        from django.utils import timezone
        from django.contrib.auth.models import User, Group
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        from django.test import Client
        from django.urls import reverse
        from administracionApp.models import Cargo, Delegacion, Profesional, Auditoria
        from usuariosApp.models import ClaveTemporal

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

        deleg = crear(Delegacion, nombre='Centro', territorio='Centro')
        cargo = crear(Cargo, nombre='Gestor')
        u_adm = User.objects.create_user('admin', password='Admin123!')
        u_adm.groups.add(Group.objects.get_or_create(name='Administrador')[0])
        Profesional.objects.create(rut='11111111-1', nombres='Admin', apellido_paterno='P', correo='admin@x.cl', id_cargo=cargo,
                                   id_delegacion=deleg, usuario=u_adm, estado=True)
        grupo_prof = Group.objects.get_or_create(name='Profesional')[0]

        ca = Client(); ca.force_login(u_adm)
        r = ca.post(reverse('administracionApp:crear_profesional'), {
            'email': 'nueva@laserena.cl', 'rol': grupo_prof.pk, 'rut': '12.345.678-5', 'nombres': 'Nueva', 'apellido_paterno': 'Persona',
            'apellido_materno': 'X', 'telefono': '+56912345678', 'id_cargo': cargo.pk, 'id_delegacion': deleg.pk}, follow=True)
        mensajes = [str(m) for m in r.context['messages']] if r.context else []
        clave = next((re.search(r'Clave temporal: \[(.+?)\]', m).group(1) for m in mensajes if 'Clave temporal' in m), None)
        nuevo = User.objects.filter(username='nueva@laserena.cl').first()
        self.verificar('Al crear el usuario queda marcado con clave temporal', nuevo and clave and ClaveTemporal.objects.filter(usuario=nuevo).exists())
        self.verificar('El mensaje al administrador avisa que deberá cambiarla', any('primer ingreso' in m for m in mensajes))

        cn = Client()
        r = cn.post(reverse('usuariosApp:login'), {'username': 'nueva@laserena.cl', 'password': clave})
        self.verificar('Al ingresar con la clave temporal lo lleva a cambiarla', r.status_code == 302 and r.url == reverse('usuariosApp:cambiar_clave_inicial'))
        for nombre in ['actividadApp:dashboard_profesional', 'actividadApp:listar_actividades', 'usuariosApp:mi_perfil']:
            r = cn.get(reverse(nombre))
            self.verificar(f'No puede saltarse el cambio entrando a {nombre}', r.status_code == 302 and r.url == reverse('usuariosApp:cambiar_clave_inicial'))
        r = cn.get(reverse('usuariosApp:cambiar_clave_inicial'))
        self.verificar('La pantalla de cambio se muestra con la lista de requisitos', r.status_code == 200 and 'reqMayuscula' in r.content.decode()
           and 'Cambia tu contraseña' in r.content.decode())

        r = cn.post(reverse('usuariosApp:cambiar_clave_inicial'), {'new_password1': 'debil', 'new_password2': 'debil'})
        self.verificar('Rechaza una contraseña que no cumple los requisitos', r.status_code == 200 and 'no cumple con los requisitos' in r.content.decode())
        r = cn.post(reverse('usuariosApp:cambiar_clave_inicial'), {'new_password1': clave + 'A!', 'new_password2': clave + 'B!'})
        self.verificar('Rechaza si la confirmación no coincide', r.status_code == 200 and ClaveTemporal.objects.filter(usuario=nuevo).exists())
        nuevo.set_password('Temporal1!'); nuevo.save()
        cn.force_login(nuevo)
        r = cn.post(reverse('usuariosApp:cambiar_clave_inicial'), {'new_password1': 'Temporal1!', 'new_password2': 'Temporal1!'})
        self.verificar('Rechaza repetir la contraseña temporal', r.status_code == 200 and 'distinta de la contraseña temporal' in r.content.decode())

        r = cn.post(reverse('usuariosApp:cambiar_clave_inicial'), {'new_password1': 'MiClave2026!', 'new_password2': 'MiClave2026!'})
        self.verificar('Con una contraseña válida lo lleva a su panel', r.status_code == 302 and r.url == reverse('actividadApp:dashboard_profesional'))
        self.verificar('Se quita la marca de clave temporal', not ClaveTemporal.objects.filter(usuario=nuevo).exists())
        self.verificar('La sesión sigue abierta después del cambio', cn.get(reverse('actividadApp:dashboard_profesional')).status_code == 200)
        self.verificar('El cambio queda en la auditoría', Auditoria.objects.filter(evento='CAMBIO_CLAVE_INICIAL', identificador=nuevo.pk).exists())
        self.verificar('La auditoría no guarda la contraseña', 'pbkdf2' not in str(Auditoria.objects.filter(evento='CAMBIO_CLAVE_INICIAL').values_list('valor_nuevo', flat=True)))

        c2 = Client()
        r = c2.post(reverse('usuariosApp:login'), {'username': 'nueva@laserena.cl', 'password': 'MiClave2026!'})
        self.verificar('En el siguiente ingreso entra directo a su panel', r.status_code == 302 and r.url == reverse('actividadApp:dashboard_profesional'))
        r = c2.get(reverse('usuariosApp:cambiar_clave_inicial'))
        self.verificar('Si ya la cambió, la pantalla de cambio lo devuelve a su panel', r.status_code == 302 and r.url == reverse('actividadApp:dashboard_profesional'))

        c3 = Client()
        r = c3.post(reverse('usuariosApp:login'), {'username': 'admin', 'password': 'Admin123!'})
        self.verificar('Un usuario existente sin clave temporal no se ve afectado', r.status_code == 302 and r.url == reverse('administracionApp:dashboard_admin'))

        ClaveTemporal.objects.create(usuario=nuevo)
        nuevo.refresh_from_db()
        token = default_token_generator.make_token(nuevo)
        uid = urlsafe_base64_encode(force_bytes(nuevo.pk))
        _r = Client().post(reverse('usuariosApp:restablecer_clave', args=[uid, token]), {'new_password1': 'Recupero9#', 'new_password2': 'Recupero9#'})
        self.verificar('Recuperar la contraseña por correo también quita la marca', not ClaveTemporal.objects.filter(usuario=nuevo).exists())

        ClaveTemporal.objects.create(usuario=nuevo)
        c4 = Client(); c4.force_login(nuevo)
        r = c4.get(reverse('usuariosApp:logout'))
        self.verificar('Puede cerrar sesión sin cambiarla', r.status_code == 302 and r.url == reverse('usuariosApp:login'))
        self.finalizar()
