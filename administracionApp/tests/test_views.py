
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User, Group
from django.http import HttpResponse
from usuariosApp.decorators import role_required 

# 1. UNIDAD AISLADA: Vista falsa ("dummy") protegida solo por tu decorador
@role_required('Administrador')
def vista_falsa_admin(request):
    return HttpResponse("Acceso Concedido a Administrador")

class TestDecoradorRoles(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        
        # Precondiciones: Creamos los roles
        self.grupo_admin = Group.objects.create(name='Administrador')
        self.grupo_vecino = Group.objects.create(name='Vecino')
        
        # Precondiciones: Creamos usuarios con distintos roles
        self.usuario_admin = User.objects.create_user(username='admin@laserena.cl', password='123')
        self.usuario_admin.groups.add(self.grupo_admin)
        
        self.usuario_vecino = User.objects.create_user(username='vecino@laserena.cl', password='123')
        self.usuario_vecino.groups.add(self.grupo_vecino)

    # --- CASO CRÍTICO 1: RECHAZO POR ROL INCORRECTO ---
    def test_role_required_rechaza_usuario_sin_permisos(self):
        # Acción: Fabricamos la petición y le inyectamos el usuario "Vecino"
        peticion = self.factory.get('/ruta-inventada/')
        peticion.user = self.usuario_vecino 
        
        # Ejecución: Chocamos contra la vista protegida
        respuesta = vista_falsa_admin(peticion)
        
        # Aserción: El decorador debe bloquear la respuesta OK (200).
        # Generalmente, un role_required redirige al login o a un error (302).
        self.assertEqual(respuesta.status_code, 302)

