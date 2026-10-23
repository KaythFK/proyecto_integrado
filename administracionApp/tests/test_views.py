from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group
from administracionApp.models import Profesional, Cargo, Delegacion, Cargo, CatalagoAreaApoyo, Periodo, Vecino
import datetime



class TestSeguridadVistas(TestCase):
    def setUp(self):
        # 1. Preparamos el cliente simulado (navegador)
        self.client = Client()
        
        # 2. Creamos el grupo oficial de Administrador
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        # 3. Creamos un usuario "Intruso" (Sin rol)
        self.user_intruso = User.objects.create_user(username='intruso', password='123')
        
        # 4. Creamos un usuario "Admin" (Con rol)
        self.user_admin = User.objects.create_user(username='admin', password='123')
        self.user_admin.groups.add(self.grupo_admin)

    # --- CASO 1: BLOQUEO A INTRUSO (CP-SEC-001) ---
    def test_acceso_denegado_sin_rol_administrador(self):
        # 1. Iniciamos sesión con el usuario que NO tiene el rol
        self.client.login(username='intruso', password='123')
        
        # 2. Intentamos entrar a la vista protegida del directorio
        url = reverse('administracionApp:directorio_profesional')
        response = self.client.get(url)
        
        # 3. Verificamos que el sistema rechazó la carga de la página (No debe ser 200 OK)
        # Lo normal con decoradores de rol es que redirija (302) o dé prohibido (403)
        self.assertNotEqual(response.status_code, 200)

    # --- CASO 2: ACCESO EXITOSO (CP-SEC-002) ---
    def test_acceso_concedido_con_rol_administrador(self):
        # 1. Iniciamos sesión con el usuario legítimo
        self.client.login(username='admin', password='123')
        
        # 2. Intentamos entrar a la misma vista protegida
        url = reverse('administracionApp:directorio_profesional')
        response = self.client.get(url)
        
        # 3. Verificamos que el sistema sí nos entregó la página exitosamente
        self.assertEqual(response.status_code, 200)


class TestVistaCrearProfesional(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        self.grupo_prof = Group.objects.create(name='Profesional')
        
        # Autorización previa
        self.admin_user = User.objects.create_user(username='admin', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin', password='123')

        # Foráneas necesarias
        self.cargo = Cargo.objects.create(nombre="Asistente")
        self.delegacion = Delegacion.objects.create(nombre="Delegación Sur", territorio="Sur")

    # --- CASO 1: TRANSACCIÓN EXITOSA (CP-CREAR-PROF-001) ---
    def test_crear_profesional_guarda_usuario_y_profesional(self):
        # 1. Conteo inicial en base de datos
        users_inicial = User.objects.count()
        prof_inicial = Profesional.objects.count()

        # 2. Petición POST con datos válidos
        url = reverse('administracionApp:crear_profesional')
        response = self.client.post(url, {
            'email': 'nuevo@laserena.cl',
            'rol': self.grupo_prof.pk,
            'rut': '12345678-5',  # <-- RUT matemáticamente válido
            'nombres': 'Ana',
            'apellido_paterno': 'Gómez',
            'id_cargo': self.cargo.pk,
            'id_delegacion': self.delegacion.pk
        })

        # 3. Aserción de redirección de éxito (HTTP 302)
        self.assertEqual(response.status_code, 302)
        
        # 4. Aserción de incremento relacional en BD (+1 en ambas tablas)
        self.assertEqual(User.objects.count(), users_inicial + 1)
        self.assertEqual(Profesional.objects.count(), prof_inicial + 1)

    # --- CASO 2: BLOQUEO POR DATOS INVÁLIDOS (CP-CREAR-PROF-003) ---
    def test_crear_profesional_invalido_aborta_transaccion(self):
        # 1. Conteo inicial en base de datos
        users_inicial = User.objects.count()
        prof_inicial = Profesional.objects.count()

        # 2. Petición POST omitiendo campos obligatorios (ej. sin RUT)
        url = reverse('administracionApp:crear_profesional')
        response = self.client.post(url, {
            'email': 'incompleto@laserena.cl',
            'rol': self.grupo_prof.pk,
            'rut': '', # Falla intencional
            'nombres': 'Luis',
            'apellido_paterno': 'Pérez',
            'id_cargo': self.cargo.pk,
            'id_delegacion': self.delegacion.pk
        })

        # 3. Aserción de recarga de formulario con errores (HTTP 200 en lugar de 302)
        self.assertEqual(response.status_code, 200)

        # 4. Aserción de protección de BD (las tablas no aumentaron su tamaño)
        self.assertEqual(User.objects.count(), users_inicial)
        self.assertEqual(Profesional.objects.count(), prof_inicial)


class TestVistaEditarProfesional(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        self.grupo_prof = Group.objects.create(name='Profesional')
        
        # 1. Autorización: Loguear al administrador
        self.admin_user = User.objects.create_user(username='admin', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin', password='123')

        # 2. Foráneas necesarias
        self.cargo = Cargo.objects.create(nombre="Asistente")
        self.delegacion = Delegacion.objects.create(nombre="Delegación Centro", territorio="Centro")

        # 3. Precondición: Crear un usuario y profesional existente para editar
        self.usuario_objetivo = User.objects.create_user(username='original@laserena.cl', email='original@laserena.cl')
        self.usuario_objetivo.groups.add(self.grupo_prof)
        
        self.prof_objetivo = Profesional.objects.create(
            rut="11111111-1", # RUT Matemáticamente válido
            nombres="Pedro",
            apellido_paterno="Díaz",
            correo="original@laserena.cl",
            id_cargo=self.cargo,
            id_delegacion=self.delegacion,
            usuario=self.usuario_objetivo,
            estado=True
        )

    # --- CASO 1: EDICIÓN TRANSACCIONAL EXITOSA (CP-EDIT-PROF-001) ---
    def test_editar_profesional_actualiza_datos_exitosamente(self):
        url = reverse('administracionApp:editar_profesional', args=[self.prof_objetivo.id_profesional])
        
        # Enviamos POST cambiando el nombre a "Pedro Editado" y el correo
        response = self.client.post(url, {
            'email': 'editado@laserena.cl',
            'rol': self.grupo_prof.pk,
            'rut': '11111111-1', 
            'nombres': 'Pedro Editado',
            'apellido_paterno': 'Díaz',
            'id_cargo': self.cargo.pk,
            'id_delegacion': self.delegacion.pk
        })

        # 1. Verificamos redirección de éxito (HTTP 302)
        self.assertEqual(response.status_code, 302)
        
        # 2. Refrescamos los objetos desde la base de datos
        self.prof_objetivo.refresh_from_db()
        self.usuario_objetivo.refresh_from_db()
        
        # 3. Verificamos que los datos se actualizaron en ambas tablas
        self.assertEqual(self.prof_objetivo.nombres, "Pedro Editado")
        self.assertEqual(self.usuario_objetivo.email, "editado@laserena.cl")

        # --- CASO 2: ACCESO A ID INEXISTENTE (CP-EDIT-PROF-004) ---
    def test_editar_profesional_id_inexistente_retorna_404(self):
        # 1. Precondición: Generamos una URL apuntando a un ID que sabemos que no existe (ej. 9999)
        url = reverse('administracionApp:editar_profesional', args=[9999])
        
        # 2. Ejecutamos una petición GET hacia esa URL
        response = self.client.get(url)
        
        # 3. Verificamos que la vista se proteja y devuelva el código HTTP 404 (Not Found)
        # en lugar de caerse con un error 500 (Internal Server Error)
        self.assertEqual(response.status_code, 404)



class TestVistaCambiarEstadoProfesional(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        # 1. Autenticación de Administrador
        self.admin_user = User.objects.create_user(username='admin', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin', password='123')

        # 2. Foráneas
        self.cargo = Cargo.objects.create(nombre="Asistente")
        self.delegacion = Delegacion.objects.create(nombre="Norte", territorio="Norte")
        
        # 3. Registro objetivo (Inicialmente Activo)
        self.usuario_test = User.objects.create_user(username='test@laserena.cl', email='test@laserena.cl')
        self.prof_test = Profesional.objects.create(
            rut="12345678-5", 
            nombres="Carlos", 
            apellido_paterno="Soto",
            correo="test@laserena.cl",
            id_cargo=self.cargo, 
            id_delegacion=self.delegacion,
            usuario=self.usuario_test,
            estado=True
        )

    # --- CASO 1: DESACTIVACIÓN TRANSACCIONAL (CP-ESTADO-PROF-001) ---
    def test_desactivar_profesional_bloquea_acceso_usuario(self):
        url = reverse('administracionApp:cambiar_estado_profesional', args=[self.prof_test.id_profesional])
        
        # Ejecutamos POST para invertir el estado
        response = self.client.post(url)
        
        # 1. Comprobamos redirección exitosa
        self.assertEqual(response.status_code, 302)
        
        # 2. Refrescamos desde BD
        self.prof_test.refresh_from_db()
        self.usuario_test.refresh_from_db()
        
        # 3. Comprobamos que AMBOS registros fueron desactivados
        self.assertFalse(self.prof_test.estado)
        self.assertFalse(self.usuario_test.is_active)

    # --- CASO 2: PROTECCIÓN DE MÉTODO HTTP (CP-ESTADO-PROF-002) ---
    def test_cambiar_estado_ignora_metodo_get(self):
        url = reverse('administracionApp:cambiar_estado_profesional', args=[self.prof_test.id_profesional])
        
        # Ejecutamos GET (ej. un usuario escribiendo la URL en el navegador)
        response = self.client.get(url)
        
        # 1. Comprobamos que el controlador simplemente redirigió sin errores (302)
        self.assertEqual(response.status_code, 302)
        
        # 2. Refrescamos la BD
        self.prof_test.refresh_from_db()
        
        # 3. Comprobamos que el estado original (True) NO fue alterado
        self.assertTrue(self.prof_test.estado)




class TestVistaCrearDelegacion(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        # Autorización: Loguear al administrador para pasar el @role_required
        self.admin_user = User.objects.create_user(username='admin', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin', password='123')

    # --- CASO 1: CREACIÓN EXITOSA (CP-CREAR-DEL-001) ---
    def test_crear_delegacion_exitosa_asigna_estado_true(self):
        # 1. Contamos cuántas delegaciones hay inicialmente (0)
        cantidad_inicial = Delegacion.objects.count()
        
        # 2. Petición POST con datos válidos
        url = reverse('administracionApp:crear_delegacion')
        response = self.client.post(url, {
            'nombre': 'Delegación Las Compañías',
            'territorio': 'Norte',
            'calle': 'Av. Argentina',
            'numero': '1234'
            # Ajusta estos campos según lo que exija tu DelegacionForm
        })
        
        # 3. Verificamos que redirige a la lista (HTTP 302)
        self.assertEqual(response.status_code, 302)
        
        # 4. Verificamos que la BD aumentó en 1
        self.assertEqual(Delegacion.objects.count(), cantidad_inicial + 1)
        
        # 5. Verificamos que el controlador inyectó "estado = True" correctamente
        nueva_delegacion = Delegacion.objects.last()
        self.assertTrue(nueva_delegacion.estado)

    # --- CASO 2: PROTECCIÓN DE BD POR FORMULARIO INVÁLIDO (CP-CREAR-DEL-002) ---
    def test_crear_delegacion_invalida_no_guarda_en_bd(self):
        cantidad_inicial = Delegacion.objects.count()
        
        # 1. Petición POST enviando un diccionario vacío (Falla todas las validaciones)
        url = reverse('administracionApp:crear_delegacion')
        response = self.client.post(url, {})
        
        # 2. Verificamos que la vista atrapa el error y recarga la página (HTTP 200)
        self.assertEqual(response.status_code, 200)
        
        # 3. Comprobamos que la base de datos sigue intacta (no se creó basura)
        self.assertEqual(Delegacion.objects.count(), cantidad_inicial)


class TestVistaEditarDelegacion(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        # 1. Autorización de Administrador
        self.admin_user = User.objects.create_user(username='admin', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin', password='123')

        # 2. Precondición: Crear una delegación en la BD (con numero_calle entero)
        self.delegacion_test = Delegacion.objects.create(
            nombre="Delegación La Antena",
            territorio="Este",
            calle="Colo Colo",
            numero_calle=123,
            estado=True
        )

    # --- CASO 1: EDICIÓN EXITOSA (CP-EDIT-DEL-001) ---
    def test_editar_delegacion_actualiza_datos_exitosamente(self):
        url = reverse('administracionApp:editar_delegacion', args=[self.delegacion_test.id_delegacion])
        
        # Enviamos un POST modificando el nombre y el numero_calle
        response = self.client.post(url, {
            'nombre': 'Delegación La Antena Editada',
            'territorio': 'Este',
            'calle': 'Colo Colo',
            'numero_calle': 1234
        })
        
        # 1. Verificamos redirección a la lista general (HTTP 302)
        self.assertEqual(response.status_code, 302)
        
        # 2. Extraemos el objeto refrescado directo desde la base de datos
        self.delegacion_test.refresh_from_db()
        
        # 3. Verificamos que los atributos mutaron correctamente
        self.assertEqual(self.delegacion_test.nombre, 'Delegación La Antena Editada')
        self.assertEqual(self.delegacion_test.numero_calle, 1234)

    # --- CASO 2: PROTECCIÓN DE RUTA HTTP 404 (CP-EDIT-DEL-003) ---
    def test_editar_delegacion_id_inexistente_retorna_404(self):
        # 1. Construimos una URL apuntando a un ID falso
        url = reverse('administracionApp:editar_delegacion', args=[9999])
        
        # 2. Ejecutamos la petición GET
        response = self.client.get(url)
        
        # 3. Verificamos que la vista se proteja retornando un 404 limpio
        self.assertEqual(response.status_code, 404)


class TestVistaCambiarEstadoDelegacion(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        # 1. Autorización de Administrador
        self.admin_user = User.objects.create_user(username='admin', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin', password='123')

        # 2. Precondición: Crear una delegación en estado Activo (True)
        self.delegacion_test = Delegacion.objects.create(
            nombre="Delegación Centro",
            territorio="Centro",
            calle="Los Carrera",
            numero_calle=123,
            estado=True
        )

    # --- CASO 1: DESACTIVACIÓN LÓGICA (CP-ESTADO-DEL-001) ---
    def test_cambiar_estado_delegacion_exitoso(self):
        url = reverse('administracionApp:cambiar_estado_delegacion', args=[self.delegacion_test.id_delegacion])
        
        # Ejecutamos POST para invertir el estado
        response = self.client.post(url)
        
        # 1. Comprobamos redirección exitosa (HTTP 302)
        self.assertEqual(response.status_code, 302)
        
        # 2. Refrescamos desde BD
        self.delegacion_test.refresh_from_db()
        
        # 3. Comprobamos que el estado mutó a False en la BD
        self.assertFalse(self.delegacion_test.estado)

    # --- CASO 2: PROTECCIÓN DE MÉTODO HTTP (CP-ESTADO-DEL-002) ---
    def test_cambiar_estado_delegacion_ignora_get(self):
        url = reverse('administracionApp:cambiar_estado_delegacion', args=[self.delegacion_test.id_delegacion])
        
        # Ejecutamos GET (ej. un usuario escribiendo la URL en el navegador)
        response = self.client.get(url)
        
        # 1. Comprobamos que el controlador simplemente redirigió sin errores (HTTP 302)
        self.assertEqual(response.status_code, 302)
        
        # 2. Refrescamos la BD
        self.delegacion_test.refresh_from_db()
        
        # 3. Comprobamos que el estado original (True) NO fue alterado
        self.assertTrue(self.delegacion_test.estado)



class TestVistaCrearCargo(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        # 1. Autorización de Administrador
        self.admin_user = User.objects.create_user(username='admin', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin', password='123')

    # --- CASO 1: CREACIÓN EXITOSA (CP-CREAR-CARGO-001) ---
    def test_crear_cargo_exitoso_guarda_en_bd(self):
        cantidad_inicial = Cargo.objects.count()
        url = reverse('administracionApp:crear_cargo')
        
        # Enviamos un POST con el campo obligatorio correctamente llenado
        response = self.client.post(url, {
            'nombre': 'Jefe de Finanzas'
        })
        
        # 1. Verificamos redirección de éxito (HTTP 302)
        self.assertEqual(response.status_code, 302)
        
        # 2. Verificamos incremento en base de datos
        self.assertEqual(Cargo.objects.count(), cantidad_inicial + 1)
        
        # 3. Verificamos el dato exacto guardado
        nuevo_cargo = Cargo.objects.last()
        self.assertEqual(nuevo_cargo.nombre, 'Jefe de Finanzas')

    # --- CASO 2: AUDITORÍA DE CAMPO OBLIGATORIO (CP-CREAR-CARGO-002) ---
    def test_crear_cargo_sin_nombre_es_bloqueado(self):
        cantidad_inicial = Cargo.objects.count()
        url = reverse('administracionApp:crear_cargo')
        
        # Enviamos un POST simulando que el usuario dejó el nombre en blanco
        response = self.client.post(url, {
            'nombre': ''
        })
        
        # 1. Verificamos que la vista recargue el formulario para mostrar errores (HTTP 200)
        # Si devuelve 302, significa que se saltó la validación y guardó el error.
        self.assertEqual(response.status_code, 200)
        
        # 2. ASERCIÓN CRÍTICA: Comprobamos que la base de datos NO aumentó.
        # Si la prueba falla aquí, significa que la BD aceptó un cargo fantasma.
        self.assertEqual(Cargo.objects.count(), cantidad_inicial)


class TestVistaEditarCargo(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        # 1. Autorización de Administrador
        self.admin_user = User.objects.create_user(username='admin', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin', password='123')

        # 2. Precondición: Crear un cargo en la base de datos
        self.cargo_test = Cargo.objects.create(
            nombre="Asistente Social"
        )

    # --- CASO 1: EDICIÓN EXITOSA (CP-EDIT-CARGO-001) ---
    def test_editar_cargo_actualiza_datos_exitosamente(self):
        url = reverse('administracionApp:editar_cargo', args=[self.cargo_test.id_cargo])
        
        # Enviamos un POST modificando el nombre
        response = self.client.post(url, {
            'nombre': 'Jefe de Asistencia Social'
        })
        
        # 1. Verificamos redirección a la lista general (HTTP 302)
        self.assertEqual(response.status_code, 302)
        
        # 2. Extraemos el objeto refrescado directo desde la base de datos
        self.cargo_test.refresh_from_db()
        
        # 3. Verificamos que el nombre mutó correctamente
        self.assertEqual(self.cargo_test.nombre, 'Jefe de Asistencia Social')

    # --- CASO 2: PROTECCIÓN DE RUTA HTTP 404 (CP-EDIT-CARGO-003) ---
    def test_editar_cargo_id_inexistente_retorna_404(self):
        # 1. Construimos una URL apuntando a un ID falso
        url = reverse('administracionApp:editar_cargo', args=[9999])
        
        # 2. Ejecutamos la petición GET
        response = self.client.get(url)
        
        # 3. Verificamos que la vista se proteja retornando un 404 limpio
        self.assertEqual(response.status_code, 404)



class TestVistaCambiarEstadoCargo(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        # 1. Autorización de Administrador
        self.admin_user = User.objects.create_user(username='admin', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin', password='123')

        # 2. Precondición: Crear un cargo inicializado en estado Activo (True)
        self.cargo_test = Cargo.objects.create(
            nombre="Asistente Social",
            estado=True
        )

    # --- CASO 1: DESACTIVACIÓN LÓGICA (CP-ESTADO-CARGO-001) ---
    def test_cambiar_estado_cargo_exitoso(self):
        url = reverse('administracionApp:cambiar_estado_cargo', args=[self.cargo_test.id_cargo])
        
        # Ejecutamos POST para activar la lógica de inversión de estado
        response = self.client.post(url)
        
        # 1. Comprobamos redirección exitosa hacia la lista de cargos (HTTP 302)
        self.assertEqual(response.status_code, 302)
        
        # 2. Refrescamos el objeto directamente desde la base de datos
        self.cargo_test.refresh_from_db()
        
        # 3. Comprobamos que el atributo booleano mutó a False
        self.assertFalse(self.cargo_test.estado)

    # --- CASO 2: PROTECCIÓN DE MÉTODO HTTP (CP-ESTADO-CARGO-002) ---
    def test_cambiar_estado_cargo_ignora_metodo_get(self):
        url = reverse('administracionApp:cambiar_estado_cargo', args=[self.cargo_test.id_cargo])
        
        # Ejecutamos GET simulando un intento de acceso vía URL del navegador
        response = self.client.get(url)
        
        # 1. Comprobamos que el controlador simplemente redirigió sin procesar datos
        self.assertEqual(response.status_code, 302)
        
        # 2. Refrescamos el objeto desde la BD
        self.cargo_test.refresh_from_db()
        
        # 3. Verificamos que el estado original se mantuvo intacto (True)
        self.assertTrue(self.cargo_test.estado)


class TestVistaGestionarCatalogo(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        self.admin_user = User.objects.create_user(username='admin', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin', password='123')
        
        self.url = reverse('administracionApp:gestionar_catalogo')
        
        # Precondición: Crear un Área de Apoyo existente
        CatalagoAreaApoyo.objects.create(nombre="Asistencia Social", estado=True)

    # --- CASO 2: INYECCIÓN DE FRONTERA DE LONGITUD (CP-CAT-002) ---
    def test_gestionar_catalogo_excede_limite_caracteres_es_bloqueado(self):
        cantidad_inicial = CatalagoAreaApoyo.objects.count()
        texto_masivo = "A" * 300 
        
        response = self.client.post(self.url, {
            'accion': 'crear',
            'tipo': 'area',
            'nombre': texto_masivo
        })
        
        self.assertEqual(response.status_code, 302)
        # ASERCIÓN CRÍTICA: El motor de base de datos rechazó el texto masivo.
        self.assertEqual(CatalagoAreaApoyo.objects.count(), cantidad_inicial)

    # --- CASO 3: PRUEBA DE DUPLICIDAD (CP-CAT-003) ---
    def test_gestionar_catalogo_duplicado_es_bloqueado(self):
        cantidad_inicial = CatalagoAreaApoyo.objects.count()
        
        # Intentamos inyectar un POST creando un área con el MISMO nombre pero en minúsculas
        response = self.client.post(self.url, {
            'accion': 'crear',
            'tipo': 'area',
            'nombre': 'asistencia social'
        })
        
        self.assertEqual(response.status_code, 302)
        # ASERCIÓN CRÍTICA: La base de datos denegó la colisión.
        self.assertEqual(CatalagoAreaApoyo.objects.count(), cantidad_inicial)


class TestVistaCrearPeriodo(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        # Autorización
        self.admin_user = User.objects.create_user(username='admin', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin', password='123')
        
        self.url = reverse('administracionApp:crear_periodo')

# --- CASO 1: CREACIÓN EXITOSA / HAPPY PATH (CP-PER-001) ---
    def test_crear_periodo_exitoso_guarda_en_bd(self):
        cantidad_inicial = Periodo.objects.count()
        
        response = self.client.post(self.url, {
            'nombre': 'Periodo Académico 2026',
            'fecha_inicio': '2026-01-01',
            'fecha_termino': '2026-12-31',
            'dias_computables': 180,
            'umbral_regular': 4.0,
            'umbral_exelencia': 6.0,
            'version_parametros': 1
        })
        
        # Verifica redirección exitosa (HTTP 302)
        self.assertEqual(response.status_code, 302)
        
        # Verifica incremento matemático en base de datos
        self.assertEqual(Periodo.objects.count(), cantidad_inicial + 1)

    # --- CASO 3: INYECCIÓN DE FECHAS ANÓMALAS / EDGE CASE (CP-PER-003) ---
    def test_crear_periodo_fechas_invertidas_es_bloqueado(self):
        cantidad_inicial = Periodo.objects.count()
        
        # Inyectamos una fecha de inicio posterior a la fecha de término
        response = self.client.post(self.url, {
            'nombre': 'Periodo Viajero del Tiempo',
            'fecha_inicio': '2026-12-31',
            'fecha_termino': '2026-01-01',
            'dias_computables': 180,
            'umbral_regular': 4.0,
            'umbral_exelencia': 6.0,
            'version_parametros': 1
        })
        
        # ASERCIÓN CRÍTICA: La BD NO debe haber guardado este periodo ilógico
        self.assertEqual(Periodo.objects.count(), cantidad_inicial)

class TestVistaEditarPeriodo(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        self.admin_user = User.objects.create_user(username='admin_edicion', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin_edicion', password='123')
        
        self.periodo_base = Periodo.objects.create(
            nombre='Periodo Original',
            fecha_inicio='2026-01-01',
            fecha_termino='2026-06-30',
            dias_computables=180,
            umbral_regular=4.0,
            umbral_exelencia=6.0,
            version_parametros=1,
            estado=True
        )
        self.url_editar = reverse('administracionApp:editar_periodo', args=[self.periodo_base.id_periodo])

    # --- CASO 1: EDICIÓN EXITOSA / HAPPY PATH (CP-PER-004) ---
    def test_editar_periodo_actualiza_datos_en_bd(self):
        response = self.client.post(self.url_editar, {
            'nombre': 'Periodo Modificado',
            'fecha_inicio': '2026-01-01',
            'fecha_termino': '2026-06-30',
            'dias_computables': 180,
            'umbral_regular': 4.5,
            'umbral_exelencia': 6.5,
            'version_parametros': 2
        })
        
        self.assertEqual(response.status_code, 302)
        self.periodo_base.refresh_from_db()
        self.assertEqual(self.periodo_base.nombre, 'Periodo Modificado')

    # --- CASO 2: INYECCIÓN DE NOMBRE DUPLICADO EN EDICIÓN (CP-PER-006) ---
    def test_editar_periodo_nombre_duplicado_es_bloqueado(self):
        Periodo.objects.create(
            nombre='Periodo Segundo Semestre',
            fecha_inicio='2026-07-01',
            fecha_termino='2026-12-31',
            dias_computables=180,
            umbral_regular=4.0,
            umbral_exelencia=6.0,
            version_parametros=1,
            estado=True
        )
        
        response = self.client.post(self.url_editar, {
            'nombre': 'Periodo Segundo Semestre',
            'fecha_inicio': '2026-01-01',
            'fecha_termino': '2026-06-30',
            'dias_computables': 180,
            'umbral_regular': 4.0,
            'umbral_exelencia': 6.0,
            'version_parametros': 1
        })
        
        self.assertEqual(response.status_code, 200)
        self.periodo_base.refresh_from_db()
        self.assertEqual(self.periodo_base.nombre, 'Periodo Original')


class TestVistaCambiarEstadoPeriodo(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        self.admin_user = User.objects.create_user(username='admin_estado', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin_estado', password='123')
        
        self.periodo_base = Periodo.objects.create(
            nombre='Periodo Prueba Estado',
            fecha_inicio='2026-01-01',
            fecha_termino='2026-06-30',
            dias_computables=180,
            umbral_regular=4.0,
            umbral_exelencia=6.0,
            version_parametros=1,
            estado=True
        )
        self.url_estado = reverse('administracionApp:cambiar_estado_periodo', args=[self.periodo_base.id_periodo])

    # --- CASO 3: DESACTIVAR REGISTRO ACTIVO (CP-PER-005) ---
    def test_cambiar_estado_desactiva_periodo(self):
        self.assertTrue(self.periodo_base.estado)
        
        response = self.client.post(self.url_estado)
        self.assertEqual(response.status_code, 302)
        
        self.periodo_base.refresh_from_db()
        self.assertFalse(self.periodo_base.estado)

    # --- CASO 4: ACTIVAR REGISTRO INACTIVO (CP-PER-010) ---
    def test_cambiar_estado_activa_periodo(self):
        self.periodo_base.estado = False
        self.periodo_base.save()
        
        response = self.client.post(self.url_estado)
        self.assertEqual(response.status_code, 302)
        
        self.periodo_base.refresh_from_db()
        self.assertTrue(self.periodo_base.estado)



class TestVistaCrearVecino(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        self.admin_user = User.objects.create_user(username='admin_vecino', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin_vecino', password='123')
        
        self.vecino_trampa = Vecino.objects.create(
            rut="11111111-1",
            nombres="Vecino",
            apellido_paterno="Prueba",
            correo="vecino.prueba@correo.com",
            estado=True
        )
        self.url_crear = reverse('administracionApp:crear_vecino')

    # --- CASO 1: CREACIÓN EXITOSA / HAPPY PATH (CP-VEC-CRE-001) ---
    def test_crear_vecino_exitoso_guarda_en_bd(self):
        cantidad_inicial = Vecino.objects.count()
        
        response = self.client.post(self.url_crear, {
            'rut': '22222222-2',
            'nombres': 'María José',
            'apellido_paterno': 'Silva',
            'correo': 'maria.silva@correo.com'
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Vecino.objects.count(), cantidad_inicial + 1)
        
        nuevo_vecino = Vecino.objects.last()
        self.assertEqual(nuevo_vecino.rut, '22222222-2')

    # --- CASO 2: INYECCIÓN DE RUT DUPLICADO (CP-VEC-CRE-002) ---
    def test_crear_vecino_rut_duplicado_es_bloqueado(self):
        cantidad_inicial = Vecino.objects.count()
        
        response = self.client.post(self.url_crear, {
            'rut': '11111111-1',
            'nombres': 'Pedro',
            'apellido_paterno': 'Gómez',
            'correo': 'pedro.gomez@correo.com'
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vecino.objects.count(), cantidad_inicial)

# =================================================================
# CLASE: AUDITORÍA DE LA FUNCIÓN EDITAR VECINO
# =================================================================
class TestVistaEditarVecino(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        self.admin_user = User.objects.create_user(username='admin_edi_vec', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin_edi_vec', password='123')
        
        # Vecino Base (El que vamos a editar)
        self.vecino_base = Vecino.objects.create(
            rut="11111111-1",
            nombres="Juan Alberto",
            apellido_paterno="Pérez",
            correo="juan.perez@correo.com",
            estado=True
        )
        
        # Vecino Trampa (Para probar la colisión de correos)
        self.vecino_trampa = Vecino.objects.create(
            rut="33333333-3",
            nombres="Pedro",
            apellido_paterno="Gómez",
            correo="pedro.trampa@correo.com",
            estado=True
        )
        
        self.url_editar = reverse('administracionApp:editar_vecino', args=[self.vecino_base.id_vecino])

    # --- CASO 1: EDICIÓN EXITOSA / HAPPY PATH (CP-VEC-EDI-001) ---
    def test_editar_vecino_actualiza_datos_en_bd(self):
        # Alteramos el nombre y el correo del vecino base
        response = self.client.post(self.url_editar, {
            'rut': '11111111-1',
            'nombres': 'Juan Modificado',
            'apellido_paterno': 'Pérez',
            'correo': 'juan.modificado@correo.com'
        })
        
        # Verificamos redirección (HTTP 302)
        self.assertEqual(response.status_code, 302)
        
        # Refrescamos el objeto desde la BD y asertamos la actualización
        self.vecino_base.refresh_from_db()
        self.assertEqual(self.vecino_base.nombres, 'Juan Modificado')
        self.assertEqual(self.vecino_base.correo, 'juan.modificado@correo.com')

    def test_editar_vecino_metodo_get_carga_datos_actuales(self):
        # Ejecutamos una petición GET (entrar a la página sin enviar datos)
        response = self.client.get(self.url_editar)
        
        # La vista debe responder con éxito (HTTP 200) y renderizar el HTML
        self.assertEqual(response.status_code, 200)
        
        # ASERCIÓN DE VISTA: Verificamos que la vista inyectó el formulario en el contexto
        self.assertIn('form', response.context)
        
        # Verificamos que la vista pre-llenó el formulario con los datos de Juan
        formulario_renderizado = response.context['form']
        self.assertEqual(formulario_renderizado.initial['nombres'], 'Juan Alberto')
        self.assertEqual(formulario_renderizado.initial['correo'], 'juan.perez@correo.com')


# =================================================================
# CLASE: AUDITORÍA DE LA FUNCIÓN CAMBIAR ESTADO VECINO
# =================================================================
class TestVistaCambiarEstadoVecino(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_admin = Group.objects.create(name='Administrador')
        
        self.admin_user = User.objects.create_user(username='admin_est_vec', password='123')
        self.admin_user.groups.add(self.grupo_admin)
        self.client.login(username='admin_est_vec', password='123')
        
        # Vecino Base (Inicialmente Activo)
        self.vecino_base = Vecino.objects.create(
            rut="11111111-1",
            nombres="Juan Alberto",
            apellido_paterno="Pérez",
            correo="juan.perez@correo.com",
            estado=True
        )
        self.url_estado = reverse('administracionApp:cambiar_estado_vecino', args=[self.vecino_base.id_vecino])
        
        # URL Trampa: Apuntamos a un ID de vecino que no existe
        self.url_estado_inexistente = reverse('administracionApp:cambiar_estado_vecino', args=[9999])

    # --- CASO 1: DESACTIVAR REGISTRO ACTIVO (CP-VEC-EST-001) ---
    def test_cambiar_estado_desactiva_vecino(self):
        self.assertTrue(self.vecino_base.estado)
        
        response = self.client.post(self.url_estado)
        self.assertEqual(response.status_code, 302)
        
        self.vecino_base.refresh_from_db()
        self.assertFalse(self.vecino_base.estado)

    # --- CASO 2: INTENTO DE CAMBIO A ID INEXISTENTE (CP-VEC-EST-004) ---
    def test_cambiar_estado_id_inexistente_retorna_404(self):
        # Ejecutamos una petición POST intentando inhabilitar un registro fantasma
        response = self.client.post(self.url_estado_inexistente)
        
        # La función get_object_or_404 de la vista debe interceptar el error y devolver 404
        self.assertEqual(response.status_code, 404)