from django.test import TestCase
from django.core.exceptions import ValidationError
from administracionApp.forms import ProfesionalForm, PeriodoForm, DelegacionForm, CargoForm, VecinoForm, UsuarioSeguridadForm
import datetime
from django import forms
from administracionApp.models import Delegacion, Cargo, Vecino, User



class TestValidacionRut(TestCase):

    # --- CASO 1: CAMINO FELIZ (Cálculo y Formateo) ---
    def test_clean_rut_exito_y_formateo(self):
        # 1. Instanciamos el formulario totalmente vacío
        form = ProfesionalForm()
        # 2. Le inyectamos a la fuerza solo el RUT en su diccionario interno
        form.cleaned_data = {'rut': '12345678-5'}
        
        # 3. Ejecutamos DIRECTAMENTE la unidad aislada (sin is_valid)
        resultado = form.clean_rut()
        
        # 4. Verificamos que la función hizo la matemática y devolvió el string con puntos
        self.assertEqual(resultado, '12.345.678-5')

    # --- CASO 2: CAMINO DE ERROR (Falla Matemática) ---
    def test_clean_rut_rechaza_digito_verificador_falso(self):
        form = ProfesionalForm()
        form.cleaned_data = {'rut': '12345678-9'}
        
        # 3 y 4. Usamos assertRaisesMessage para asegurarnos de que la función explote 
        # y lance exactamente el error de negocio programado
        with self.assertRaisesMessage(ValidationError, "El RUT no es válido (dígito verificador incorrecto)."):
            form.clean_rut()



class TestValidacionPeriodo(TestCase):

    # --- CASO 1: RECHAZO POR FECHAS INCOHERENTES (CP-PER-002) ---
    def test_clean_rechaza_fecha_termino_anterior(self):
        # 1. Instanciamos el formulario vacío
        form = PeriodoForm()
        form._errors = {} # Inicializamos el diccionario de errores
        
        # 2. Inyectamos a la fuerza una fecha de término anterior a la de inicio
        form.cleaned_data = {
            'fecha_inicio': datetime.date(2026, 12, 31),
            'fecha_termino': datetime.date(2026, 1, 1) # ¡Error intencional!
        }
        
        # 3. Ejecutamos directamente la unidad aislada
        form.clean()
        
        # 4. Verificamos que detectó el error y lo asignó al campo correcto
        self.assertIn('fecha_termino', form.errors)
        self.assertEqual(form.errors['fecha_termino'][0], "La fecha de término debe ser posterior a la fecha de inicio.")

    # --- CASO 2: RECHAZO POR UMBRALES INCOHERENTES (CP-PER-003) ---
    def test_clean_rechaza_umbral_regular_mayor(self):
        form = PeriodoForm()
        form._errors = {}
        
        # 2. Inyectamos un umbral regular que supera al de excelencia
        form.cleaned_data = {
            'umbral_regular': 6.5,
            'umbral_exelencia': 4.0 # ¡Error intencional!
        }
        
        # 3. Ejecutamos la función
        form.clean()
        
        # 4. Verificamos que la regla de negocio atajó la inconsistencia
        self.assertIn('umbral_exelencia', form.errors)
        self.assertEqual(form.errors['umbral_exelencia'][0], "El umbral de excelencia debe ser mayor al umbral regular.")


class TestValidacionDelegacion(TestCase):

    # --- CASO 1: RECHAZO POR NÚMERO DE CALLE INVÁLIDO (CP-DEL-002) ---
    def test_clean_rechaza_numero_calle_cero_o_negativo(self):
        # 1. Instanciamos formulario vacío
        form = DelegacionForm()
        
        # 2. Inyectamos un número inválido (cero)
        form.cleaned_data = {'numero_calle': 0}
        
        # 3. Ejecutamos la función específica y verificamos que levante el error exacto
        with self.assertRaisesMessage(forms.ValidationError, "El número de la dirección debe ser mayor a cero."):
            form.clean_numero_calle()

    # --- CASO 2: RECHAZO POR NOMBRE DUPLICADO (CP-DEL-003) ---
    def test_clean_rechaza_nombre_duplicado(self):
        # 1. Precondición: Creamos una delegación real en la BD de pruebas
        Delegacion.objects.create(nombre="Delegación Centro", territorio="Sector Centro")
        
        # 2. Instanciamos formulario e inyectamos el mismo nombre exacto
        form = DelegacionForm()
        form.cleaned_data = {'nombre': "Delegación Centro"}
        
        # 3. Ejecutamos la función y verificamos que detecte la duplicidad
        with self.assertRaisesMessage(forms.ValidationError, "Ya existe una delegación registrada con este nombre."):
            form.clean_nombre()


class TestValidacionCargo(TestCase):

    # --- CASO 1: RECHAZO POR VIGENCIA INVÁLIDA (CP-CAR-002) ---
    def test_clean_rechaza_vigencia_cero_o_negativa(self):
        # 1. Instanciamos formulario vacío
        form = CargoForm()
        
        # 2. Inyectamos un número inválido (0 meses)
        form.cleaned_data = {'vigencia': 0}
        
        # 3. Ejecutamos la unidad aislada y capturamos la excepción
        with self.assertRaisesMessage(forms.ValidationError, "La vigencia (en meses) debe ser mayor a cero."):
            form.clean_vigencia()

    # --- CASO 2: RECHAZO POR NOMBRE DUPLICADO (CP-CAR-003) ---
    def test_clean_rechaza_nombre_duplicado(self):
        # 1. Precondición: Creamos el cargo real en la BD
        Cargo.objects.create(nombre="Supervisor de Obras")
        
        # 2. Instanciamos formulario e inyectamos el mismo nombre
        form = CargoForm()
        form.cleaned_data = {'nombre': "Supervisor de Obras"}
        
        # 3. Ejecutamos la validación contra la BD
        with self.assertRaisesMessage(forms.ValidationError, "Ya existe un cargo registrado con este nombre."):
            form.clean_nombre()


class TestValidacionVecino(TestCase):

    # --- CASO 1: RECHAZO POR RUT DUPLICADO (CP-VEC-002) ---
    def test_clean_rechaza_rut_duplicado(self):
        # 1. Precondición: Creamos un vecino real en la BD
        Vecino.objects.create(
            rut="12345678-9", 
            nombres="Juan Alberto", 
            apellido_paterno="Pérez", 
            correo="juan@correo.com"
        )
        
        # 2. Instanciamos formulario e inyectamos el RUT repetido
        form = VecinoForm()
        form.cleaned_data = {'rut': "12345678-9"}
        
        # 3. Ejecutamos la función y verificamos que levante el error
        with self.assertRaisesMessage(forms.ValidationError, "Ya existe un vecino registrado con este RUT."):
            form.clean_rut()

    # --- CASO 2: RECHAZO POR CORREO DUPLICADO (CP-VEC-003) ---
    def test_clean_rechaza_correo_duplicado(self):
        # 1. Precondición: Creamos un vecino con un correo específico en la BD
        Vecino.objects.create(
            rut="98765432-1", 
            nombres="María", 
            apellido_paterno="Silva", 
            correo="ejemplo@correo.com"
        )
        
        # 2. Instanciamos formulario e inyectamos el correo repetido
        form = VecinoForm()
        form.cleaned_data = {'correo': "ejemplo@correo.com"}
        
        # 3. Ejecutamos la validación contra la BD
        with self.assertRaisesMessage(forms.ValidationError, "Este correo ya está en uso por otro vecino."):
            form.clean_correo()



class TestValidacionSeguridad(TestCase):

    # --- CASO 1: RECHAZO POR CORREO DUPLICADO (CP-SEG-002) ---
    def test_clean_email_rechaza_duplicado(self):
        # 1. Precondición: Creamos un usuario real en la BD
        User.objects.create_user(username="admin@laserena.cl", email="admin@laserena.cl")
        
        # 2. Instanciamos formulario como si fuera un usuario nuevo inyectando el correo repetido
        form = UsuarioSeguridadForm()
        form.cleaned_data = {'email': "admin@laserena.cl"}
        
        # 3. Ejecutamos la función y verificamos el bloqueo
        with self.assertRaisesMessage(forms.ValidationError, "Ya existe una cuenta de usuario registrada con este correo."):
            form.clean_email()

    # --- CASO 2: EXCLUSIÓN DE SÍ MISMO AL EDITAR (CP-SEG-003) ---
    def test_clean_email_permite_mismo_correo_al_editar(self):
        # 1. Precondición: Creamos el usuario en la BD
        usuario = User.objects.create_user(username="jperez@laserena.cl", email="jperez@laserena.cl")
        
        # 2. Instanciamos el formulario PASÁNDOLE LA INSTANCIA (Simulando una edición)
        form = UsuarioSeguridadForm(instance=usuario)
        form.cleaned_data = {'email': "jperez@laserena.cl"}
        
        # 3. Ejecutamos la función (Esta vez NO debe fallar, debe devolver el correo)
        resultado = form.clean_email()
        self.assertEqual(resultado, "jperez@laserena.cl")