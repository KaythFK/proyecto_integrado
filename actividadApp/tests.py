from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, Client
from django.urls import reverse, resolve
from django.contrib.auth import get_user_model
from .forms import ActividadForm
from actividadApp.views import listar_actividades, editar_actividad, desactivar_actividad


User = get_user_model()

class ActividadFormValidacionesTests(SimpleTestCase):
    def test_campos_obligatorios_rechazan_formulario_vacio(self):
        form = ActividadForm(data={})
        self.assertFalse(form.is_valid())
        obligatorios = ['solicitud_problema', 'accion', 'estado_progreso', 'id_profesional', 'id_meta']
        for campo in obligatorios:
            self.assertIn(campo, form.errors)
            self.assertEqual(form.errors.as_data()[campo][0].code, 'required')
        for campo in ['solicitante_profesional', 'solicitante_vecino', 'en_tubo']:
            self.assertNotIn(campo, form.errors)

    def test_estado_progreso_invalido_y_campos_protegidos(self):
        campo_estado = ActividadForm().fields['estado_progreso']
        for estado in ['PENDIENTE', 'EN_PROCESO', 'FINALIZADA']:
            self.assertEqual(campo_estado.clean(estado), estado)
        with self.assertRaises(ValidationError) as contexto:
            campo_estado.clean('INEXISTENTE')
        self.assertEqual(contexto.exception.error_list[0].code, 'invalid_choice')
        form = ActividadForm(data={'estado_progreso': 'INEXISTENTE'})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors.as_data()['estado_progreso'][0].code, 'invalid_choice')
        self.assertNotIn('codigo_unico', form.fields)
        self.assertNotIn('estado', form.fields)
        
    def test_form_validacion_errores_vacios(self):
        datos_vacios = {
            'solicitud_problema': '', 
            'accion': ''
        }
        formulario = ActividadForm(data=datos_vacios)
        self.assertFalse(formulario.is_valid())
        self.assertIn('solicitud_problema', formulario.errors)

    def test_form_logica_exclusion(self):
        formulario = ActividadForm()
        self.assertNotIn('codigo_unico', formulario.fields)
        self.assertNotIn('estado', formulario.fields)

class ActividadViewsTestCase(TestCase):
    def setUp(self):
        self.cliente = Client()
        self.user = User.objects.create_user(username='prof@correo.cl', password='Ventana$123')

    def test_view_seguridad_acceso_anonimo(self):
        url = reverse('actividadApp:registrar_actividad')
        respuesta = self.cliente.get(url)
        self.assertEqual(respuesta.status_code, 302)

    def test_view_manejo_errores_post(self):
        self.cliente.force_login(self.user)
        url = reverse('actividadApp:registrar_actividad')
        respuesta = self.cliente.post(url, {})
        self.assertEqual(respuesta.status_code, 302)

class ActividadListarTestCase(TestCase):
    
    def setUp(self):
        self.cliente = Client()

    def test_listar_acceso_anonimo(self):
        url = reverse('actividadApp:listar_actividades')
        respuesta = self.cliente.get(url)
        self.assertEqual(respuesta.status_code, 302)

    def test_listar_resolucion_estructural(self):
        url = reverse('actividadApp:listar_actividades')
        resolucion = resolve(url)
        self.assertEqual(resolucion.func, listar_actividades)
        
class ActividadEditarTestCase(TestCase):
    
    def setUp(self):
        self.cliente = Client()

    def test_editar_acceso_anonimo(self):
        url = reverse('actividadApp:editar_actividad', args=[1])
        respuesta = self.cliente.get(url)
        self.assertEqual(respuesta.status_code, 302)

    def test_editar_resolucion_estructural(self):
        url = reverse('actividadApp:editar_actividad', args=[1])
        resolucion = resolve(url)
        self.assertEqual(resolucion.func, editar_actividad)
        
class ActividadDesactivarTestCase(TestCase):
    
    def setUp(self):
        self.cliente = Client()

    def test_desactivar_acceso_anonimo(self):
        url = reverse('actividadApp:desactivar_actividad', args=['ACT-TEST'])
        respuesta = self.cliente.get(url)
        self.assertEqual(respuesta.status_code, 302)

    def test_desactivar_resolucion_estructural(self):
        url = reverse('actividadApp:desactivar_actividad', args=['ACT-TEST'])
        resolucion = resolve(url)
        self.assertEqual(resolucion.func, desactivar_actividad)