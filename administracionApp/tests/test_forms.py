from django.test import TestCase
from django.core.exceptions import ValidationError
from administracionApp.forms import ProfesionalForm

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