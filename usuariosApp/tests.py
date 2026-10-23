from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

class LoginTestCase(TestCase):
    def setUp(self):
        self.cliente = Client()
        self.admin_user = User.objects.create_user(
            username='admin@correo.cl', 
            email='admin@correo.cl',
            password='Ventana$123',
            is_active=True
        )
        self.admin_user.is_superuser = True
        self.admin_user.is_staff = True
        self.admin_user.save()

    def test_login_exitoso_admin(self):
        url_login = reverse('usuariosApp:login')
        datos_entrada = {
            'username': 'admin@correo.cl', 
            'password': 'Ventana$123'
        }
        respuesta = self.cliente.post(url_login, datos_entrada)
        self.assertEqual(respuesta.status_code, 302)
        url_dashboard = reverse('administracionApp:dashboard_admin')
        self.assertRedirects(respuesta, url_dashboard)
        
        self.assertTrue('_auth_user_id' in self.cliente.session)
        self.assertEqual(int(self.cliente.session['_auth_user_id']), self.admin_user.pk)
        
    def test_login_credenciales_incorrectas(self):
        url_login = reverse('usuariosApp:login')
        datos_entrada = {
            'username': 'admin@correo.cl',
            'password': 'pollito123' 
        }
        
        respuesta = self.cliente.post(url_login, datos_entrada)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('_auth_user_id', self.cliente.session)


class LoginSeguridadTestCase(TestCase):
    def setUp(self):
        self.cliente = Client()

    def test_login_credenciales_vacias(self):
        url = reverse('usuariosApp:login') 
        respuesta = self.cliente.post(url, {
            'username': '',
            'password': ''
        })

        self.assertEqual(respuesta.status_code, 200)
        mensajes = list(respuesta.context.get('messages'))
        self.assertTrue(any('Por favor, ingresa tu usuario y tu contraseña.' in mensaje.message for mensaje in mensajes))

    def test_login_cuenta_inactiva(self):
        User.objects.create_user(
            username='suspendido@correo.cl', 
            password='ClaveSegura$123', 
            is_active=False
        )
        
        url = reverse('usuariosApp:login')
        respuesta = self.cliente.post(url, {
            'username': 'suspendido@correo.cl',
            'password': 'ClaveSegura$123'
        })
        
        self.assertEqual(respuesta.status_code, 200)
        mensajes = list(respuesta.context.get('messages'))
        self.assertTrue(any('Esta cuenta se encuentra desactivada por auditoría.' in mensaje.message for mensaje in mensajes))


class PerfilSeguridadTestCase(TestCase):
    def setUp(self):
        self.cliente = Client()
        self.usuario_prueba = User.objects.create_user(
            username='profesional@correo.cl', 
            password='ClaveSegura$123'
        )

    def test_restriccion_acceso_anonimo_perfil(self):
        url = reverse('usuariosApp:mi_perfil')
        respuesta = self.cliente.get(url)
        self.assertEqual(respuesta.status_code, 302)

    def test_cambio_clave_no_coincide(self):

        self.cliente.login(username='profesional@correo.cl', password='ClaveSegura$123')
        
        url = reverse('usuariosApp:mi_perfil')
        respuesta = self.cliente.post(url, {
            'nueva_clave': 'Nueva$123',
            'confirmar_clave': 'Distinta$999'
        })
        
        self.assertEqual(respuesta.status_code, 200)
        mensajes = list(respuesta.context.get('messages'))
        self.assertTrue(any('Las contraseñas no coinciden.' in mensaje.message for mensaje in mensajes))

class PerfilSeguridadTestCase(TestCase):
    
    def setUp(self):
        self.cliente = Client()

        self.usuario_prueba = User.objects.create_user(
            username='profesional@correo.cl', 
            password='ClaveSegura$123'
        )

    def test_restriccion_acceso_anonimo_perfil(self):

        url = reverse('usuariosApp:mi_perfil')
        respuesta = self.cliente.get(url)

        self.assertEqual(respuesta.status_code, 302)

    def test_cambio_clave_no_coincide(self):

        self.cliente.login(username='profesional@correo.cl', password='ClaveSegura$123')
        
        url = reverse('usuariosApp:mi_perfil')

        respuesta = self.cliente.post(url, {
            'nueva_clave': 'Nueva$123',
            'confirmar_clave': 'Distinta$999'
        })

        self.assertEqual(respuesta.status_code, 200)
        mensajes = list(respuesta.context.get('messages'))
        self.assertTrue(any('Las contraseñas no coinciden.' in mensaje.message for mensaje in mensajes))