import re
import unicodedata
from collections import Counter
from datetime import date, datetime
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
import pandas as pd

from comunidadApp.models import OrganizacionComunitaria
from administracionApp.models import Delegacion


DELEGACIONES_OFICIALES = [
    'COMPANIAS',
    'CENTRO',
    'PAMPA',
    'RURAL',
    'ANTENA',
    'AV DEL MAR',
]


def normalizar_texto(texto):
    if not texto:
        return ''
    s = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
    s = ' '.join(s.upper().strip().split())
    s = s.replace('CIAS', 'COMPANIAS').replace('COPANIAS', 'COMPANIAS')
    return s


def limpiar_texto_o_sin_datos(valor, max_len=None):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        texto = OrganizacionComunitaria.SIN_DATO_TEXTO
    else:
        texto = str(valor).strip()
        if not texto or texto.upper() in ('SIN DATOS', 'S/INF.', 'S/INF', 'SIN INF.', 'NAN', 'NONE'):
            texto = OrganizacionComunitaria.SIN_DATO_TEXTO
    if max_len:
        texto = texto[:max_len]
    return texto


def limpiar_socios(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0
    s = str(valor).strip()
    if not s or s.upper() in ('SIN DATOS', 'S/INF.', 'S/INF', 'SIN INF.'):
        return 0
    match = re.search(r'\d+', s)
    return int(match.group(0)) if match else 0


def limpiar_fecha(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    s = str(valor).strip()
    if not s or s.upper() in ('SIN DATOS', 'S/INF.', 'S/INF', 'SIN INF.', 'NAT', 'NONE'):
        return None
    parsed = pd.to_datetime(s, errors='coerce')
    if pd.isna(parsed):
        return None
    return parsed.date()


def clasificar_organizacion(nombre_org):
    n = (nombre_org or '').upper().strip()
    Tipo = OrganizacionComunitaria.TipoOrganizacion
    Subtipo = OrganizacionComunitaria.SubtipoOrganizacion

    if 'JUNTA DE VECINOS' in n or 'JJ.VV' in n or 'JJVV' in n:
        return Tipo.TERRITORIAL, Subtipo.JUNTA_VECINOS
    if 'UNION COMUNAL' in n or 'UNIÓN COMUNAL' in n:
        return Tipo.FUNCIONAL, Subtipo.UNION_COMUNAL
    if 'ADULTO MAYOR' in n or 'ADULTOS MAYORES' in n or 'ABUELITO' in n:
        return Tipo.FUNCIONAL, Subtipo.ADULTO_MAYOR
    if 'COMITE DE ALLEGADOS' in n or 'COMITÉ DE ALLEGADOS' in n:
        return Tipo.FUNCIONAL, Subtipo.COMITE_ALLEGADOS
    if 'COMITE DE SEGURIDAD' in n or 'COMITÉ DE SEGURIDAD' in n or 'SEGURIDAD CIUDADANA' in n:
        return Tipo.FUNCIONAL, Subtipo.COMITE_SEGURIDAD
    if 'COMITE' in n or 'COMITÉ' in n:
        return Tipo.FUNCIONAL, Subtipo.COMITE_VIVIENDA
    if 'CENTRO DE MADRES' in n:
        return Tipo.FUNCIONAL, Subtipo.CENTRO_MADRES
    if 'CULTURAL' in n:
        return Tipo.FUNCIONAL, Subtipo.CULTURAL
    if 'JUVENIL' in n or 'JOVENES' in n or 'JÓVENES' in n:
        return Tipo.FUNCIONAL, Subtipo.JUVENIL
    if 'DEPORTIV' in n or 'FUTBOL' in n or 'FÚTBOL' in n or 'CUECA' in n or 'CLUB' in n:
        return Tipo.FUNCIONAL, Subtipo.CLUB_DEPORTIVO

    return Tipo.FUNCIONAL, Subtipo.OTRO


def resolver_delegacion(territorio_limpio, delegaciones_cache):
    if not territorio_limpio or territorio_limpio == OrganizacionComunitaria.SIN_DATO_TEXTO:
        return None
    terr_norm = normalizar_texto(territorio_limpio)

    clave_oficial = next((d for d in DELEGACIONES_OFICIALES if d in terr_norm), None)
    if not clave_oficial:
        return None

    for del_obj in delegaciones_cache:
        if clave_oficial in normalizar_texto(del_obj.nombre):
            return del_obj
    return None


class Command(BaseCommand):
    help = 'Importa organizaciones comunitarias desde el archivo Excel base datos JJVV sin verificar.xlsx'

    def add_arguments(self, parser):
        parser.add_argument('ruta_excel', type=str, help='Ruta al archivo .xlsx')
        parser.add_argument(
            '--hoja',
            type=str,
            default='juntas de vecinos',
            help='Nombre de la hoja del Excel (por defecto: juntas de vecinos)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula la importación sin guardar cambios en la base de datos'
        )

    def handle(self, *args, **options):
        ruta_excel = options['ruta_excel']
        hoja = options['hoja']
        dry_run = options['dry_run']

        try:
            df = pd.read_excel(ruta_excel, sheet_name=hoja)
        except Exception as e:
            raise CommandError(f'No se pudo leer el archivo Excel: {e}')

        df.columns = [str(c).strip() for c in df.columns]

        col_nombre = 'ORGANIZACIONES'
        col_domicilio = 'DOMICILIO LEGAL'
        col_territorio = 'TERRIT. DELEG.'
        col_socios = 'SOCIOS ACTIVOS'
        col_fecha_const = 'FECHA CONSTIT.'
        col_reg_pj = 'Nº REG. P.J.'
        col_fecha_insc = 'FECHA INSCRIPC EN REG.'
        col_reg_dir = 'REG. DIR. Nº'

        if col_nombre not in df.columns:
            raise CommandError(f'No se encontró la columna {col_nombre} en la hoja {hoja}.')

        delegaciones_cache = list(Delegacion.objects.all())
        nombres_existentes = set(
            n.strip().lower()
            for n in OrganizacionComunitaria.objects.values_list('nombre', flat=True)
            if n
        )

        creadas = 0
        omitidas_duplicadas = 0
        con_incompletos = 0
        conteo_delegaciones = Counter()
        objetos_a_crear = []

        for _, fila in df.iterrows():
            nombre = limpiar_texto_o_sin_datos(fila.get(col_nombre), max_len=150)
            if nombre == OrganizacionComunitaria.SIN_DATO_TEXTO:
                continue

            clave_nombre = nombre.lower()
            if clave_nombre in nombres_existentes:
                omitidas_duplicadas += 1
                continue

            tipo, subtipo = clasificar_organizacion(nombre)
            direccion = limpiar_texto_o_sin_datos(fila.get(col_domicilio), max_len=200)
            territorio = limpiar_texto_o_sin_datos(fila.get(col_territorio), max_len=45)
            socios_activos = limpiar_socios(fila.get(col_socios))
            fecha_formacion = limpiar_fecha(fila.get(col_fecha_const))
            fecha_inscripcion = limpiar_fecha(fila.get(col_fecha_insc))
            n_reg_pj = limpiar_texto_o_sin_datos(fila.get(col_reg_pj), max_len=50)
            n_reg_dir = limpiar_texto_o_sin_datos(fila.get(col_reg_dir), max_len=50)
            delegacion = resolver_delegacion(territorio, delegaciones_cache)

            etiqueta_del = delegacion.nombre if delegacion else 'SIN DELEGACIÓN ASIGNADA'
            conteo_delegaciones[etiqueta_del] += 1

            org = OrganizacionComunitaria(
                nombre=nombre,
                tipo=tipo,
                subtipo=subtipo,
                direccion=direccion,
                territorio=territorio,
                socios_activos=socios_activos,
                fecha_formacion=fecha_formacion,
                fecha_inscripcion_reg_date=fecha_inscripcion,
                n_reg_pj=n_reg_pj,
                n_reg_dir=n_reg_dir,
                id_delegacion=delegacion,
                organizacion_matriz=None,
                estado=True,
            )

            if org.tiene_datos_incompletos:
                con_incompletos += 1

            nombres_existentes.add(clave_nombre)
            objetos_a_crear.append(org)
            creadas += 1

        if not dry_run and objetos_a_crear:
            with transaction.atomic():
                OrganizacionComunitaria.objects.bulk_create(objetos_a_crear, batch_size=500)

        modo = 'SIMULACIÓN (--dry-run)' if dry_run else 'IMPORTACIÓN REAL'
        self.stdout.write(self.style.SUCCESS(f'=== {modo} FINALIZADA ==='))
        self.stdout.write(f'Organizaciones preparadas/creadas: {creadas}')
        self.stdout.write(f'Omitidas por duplicado en BD/Excel: {omitidas_duplicadas}')
        self.stdout.write(f'Registros con aviso "SIN DATOS" / pendientes: {con_incompletos}')
        self.stdout.write('--- Distribución por Delegación ---')
        for nombre_del, cantidad in conteo_delegaciones.items():
            self.stdout.write(f'  * {nombre_del}: {cantidad}')