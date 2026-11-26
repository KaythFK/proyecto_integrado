import shutil
import sys
import tempfile

from django.test import TestCase, override_settings


def escribir(texto):
    codificacion = sys.stdout.encoding or 'utf-8'
    sys.stdout.write(texto.encode(codificacion, 'replace').decode(codificacion))


class CasoProtocolo(TestCase):
    """Caso del protocolo de pruebas: imprime cada verificación y falla si alguna no se cumple."""

    codigo = ''
    nombre = ''

    @classmethod
    def setUpClass(cls):
        cls._carpeta_media = tempfile.mkdtemp()
        cls._media_temporal = override_settings(MEDIA_ROOT=cls._carpeta_media)
        cls._media_temporal.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_temporal.disable()
        shutil.rmtree(cls._carpeta_media, ignore_errors=True)

    def setUp(self):
        self.resultados = []
        escribir(f'\n{self.codigo} {self.nombre}\n')

    def verificar(self, descripcion, condicion):
        self.resultados.append((descripcion, bool(condicion)))
        escribir(f'  {"OK   " if condicion else "FALLA"}  {descripcion}\n')

    def finalizar(self):
        correctas = sum(1 for _, cumple in self.resultados if cumple)
        escribir(f'  Resultado {self.codigo}: {correctas}/{len(self.resultados)} verificaciones correctas\n')
        fallidas = [descripcion for descripcion, cumple in self.resultados if not cumple]
        self.assertEqual(fallidas, [], f'Verificaciones fallidas en {self.codigo}')
