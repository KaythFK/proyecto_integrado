from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse

from administracionApp.models import Auditoria, Cargo, Delegacion, Profesional
from protocolo.base import CasoProtocolo
from protocolo.datos import crear
from usuariosApp.correo import contenido_credenciales
from usuariosApp.models import ClaveTemporal


class CasoCP29(CasoProtocolo):
    codigo = 'CP-29'
    nombre = 'Envío y reenvío de credenciales por correo'

    def test_protocolo(self):
        cargo, delegacion = crear(Cargo), crear(Delegacion)
        grupo_prof = Group.objects.get_or_create(name='Profesional')[0]
        admin = User.objects.create_user('admin', password='Admin123!')
        admin.groups.add(Group.objects.get_or_create(name='Administrador')[0])
        Profesional.objects.create(rut='11111111-1', nombres='Admin', apellido_paterno='P', correo='admin@x.cl',
                                   id_cargo=cargo, id_delegacion=delegacion, usuario=admin)
        cliente = Client()
        cliente.force_login(admin)
        url_crear = reverse('administracionApp:crear_profesional')

        def datos(correo, rut, enviar=True):
            base = {'email': correo, 'rol': grupo_prof.pk, 'rut': rut, 'nombres': 'Nueva', 'apellido_paterno': 'Persona',
                    'apellido_materno': 'X', 'telefono': '+56912345678', 'id_cargo': cargo.pk, 'id_delegacion': delegacion.pk}
            if enviar:
                base['enviar_credenciales'] = 'on'
            return base

        def mensajes(respuesta):
            return ' '.join(str(m) for m in respuesta.context['messages'])

        self.verificar('El formulario de creación ofrece enviar las credenciales, marcado por defecto',
                       'name="enviar_credenciales" id="enviarCredenciales" checked' in cliente.get(url_crear).content.decode())

        with patch('administracionApp.views.enviar_credenciales', return_value=True) as envio:
            r = cliente.post(url_crear, datos('ana@laserena.cl', '12.345.678-5'), follow=True)
        nuevo = User.objects.get(username='ana@laserena.cl')
        destinatario, nombre, clave_enviada, enlace = envio.call_args.args
        self.verificar('Al crear el profesional se envía un correo a su dirección', envio.call_count == 1 and destinatario == 'ana@laserena.cl')
        self.verificar('La clave enviada es la que permite ingresar', nuevo.check_password(clave_enviada))
        self.verificar('El correo incluye el enlace de ingreso al sistema', enlace.endswith(reverse('usuariosApp:login')))
        self.verificar('El usuario queda obligado a cambiar la clave en su primer ingreso', ClaveTemporal.objects.filter(usuario=nuevo).exists())
        self.verificar('Si el correo se envió, la clave no se muestra en pantalla', 'Se enviaron' in mensajes(r) and clave_enviada not in mensajes(r))

        with patch('administracionApp.views.enviar_credenciales', return_value=False):
            r = cliente.post(url_crear, datos('beto@laserena.cl', '15.111.222-6'), follow=True)
        self.verificar('Si el envío falla, el usuario se crea igual', User.objects.filter(username='beto@laserena.cl').exists())
        self.verificar('Si el envío falla, se avisa y se muestra la clave para entregarla', 'No se pudo enviar' in mensajes(r) and 'Clave temporal: [' in mensajes(r))

        with patch('administracionApp.views.enviar_credenciales') as envio:
            r = cliente.post(url_crear, datos('carla@laserena.cl', '9.876.543-3', enviar=False), follow=True)
        self.verificar('Sin marcar la opción no se envía correo y la clave se muestra al administrador',
                       envio.call_count == 0 and 'Clave temporal: [' in mensajes(r))

        html, texto = contenido_credenciales('Ana', 'ana@laserena.cl', 'Abc123xyz9', 'https://sgr.cl/usuarios/login/')
        self.verificar('El correo muestra usuario, clave temporal, enlace y el aviso de cambio obligatorio',
                       all(v in html for v in ('ana@laserena.cl', 'Abc123xyz9', 'https://sgr.cl/usuarios/login/', 'cambiar esta clave')) and 'Abc123xyz9' in texto)

        profesional = Profesional.objects.get(usuario=nuevo)
        url_reenvio = reverse('administracionApp:reenviar_credenciales', args=[profesional.pk])
        self.verificar('El directorio ofrece Reenviar credenciales', 'Reenviar credenciales' in cliente.get(reverse('administracionApp:directorio_profesional')).content.decode())
        ClaveTemporal.objects.filter(usuario=nuevo).delete()
        with patch('administracionApp.views.enviar_credenciales', return_value=True) as envio:
            cliente.post(url_reenvio)
        nuevo.refresh_from_db()
        nueva_clave = envio.call_args.args[2]
        self.verificar('Reenviar genera una clave nueva y la envía', envio.call_count == 1 and nuevo.check_password(nueva_clave))
        self.verificar('La clave anterior deja de funcionar', not nuevo.check_password(clave_enviada))
        self.verificar('Reenviar vuelve a exigir el cambio de clave', ClaveTemporal.objects.filter(usuario=nuevo).exists())
        auditoria = Auditoria.objects.filter(evento='REENVIO_CREDENCIALES', identificador=profesional.pk)
        self.verificar('El reenvío queda en la auditoría sin guardar la contraseña',
                       auditoria.exists() and 'pbkdf2' not in str(list(auditoria.values_list('valor_nuevo', flat=True))))

        with patch('administracionApp.views.enviar_credenciales') as envio:
            cliente.get(url_reenvio)
        self.verificar('Abrir el reenvío por GET no cambia la clave', envio.call_count == 0 and User.objects.get(pk=nuevo.pk).check_password(nueva_clave))

        Profesional.objects.filter(pk=profesional.pk).update(estado=False)
        with patch('administracionApp.views.enviar_credenciales') as envio:
            r = cliente.post(url_reenvio, follow=True)
        self.verificar('No reenvía credenciales a un profesional inactivo', envio.call_count == 0 and 'Solo se pueden reenviar' in mensajes(r))

        Profesional.objects.filter(pk=profesional.pk).update(estado=True)
        otro = Client()
        otro.force_login(nuevo)
        with patch('administracionApp.views.enviar_credenciales') as envio:
            otro.post(url_reenvio)
        self.verificar('Un Profesional no puede reenviar credenciales', envio.call_count == 0 and User.objects.get(pk=nuevo.pk).check_password(nueva_clave))
        self.finalizar()
