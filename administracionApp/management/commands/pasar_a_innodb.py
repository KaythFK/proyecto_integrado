import json
from datetime import datetime
from io import StringIO
from pathlib import Path

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

TABLAS_SIN_COMPARAR = {'django_migrations', 'django_session', 'django_admin_log', 'django_content_type', 'auth_permission'}


class Command(BaseCommand):
    help = ('Revisa la base de datos y, con --confirmar, la recrea en InnoDB con claves foráneas reales. '
            'Las tablas actuales se mueven a <base>_respaldo_myisam y los datos se respaldan en JSON.')

    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true', help='Ejecuta la conversión. Sin esta opción solo revisa.')
        parser.add_argument('--carpeta', default=str(Path.home() / 'respaldos_bd'), help='Carpeta donde se guarda el respaldo en JSON.')

    def handle(self, *args, **opciones):
        if connection.vendor != 'mysql':
            raise CommandError('Este comando solo aplica a bases MySQL o MariaDB.')
        base = connection.settings_dict['NAME']
        respaldo = f'{base}_respaldo_myisam'

        estado = self.estado()
        self.stdout.write(f'Base: {base}')
        self.stdout.write(f'Motores: {estado["motores"]} | claves foráneas: {estado["fk"]}')
        huerfanos = self.huerfanos()
        for linea in huerfanos:
            self.stdout.write(self.style.WARNING(linea))
        self.stdout.write(f'Filas huérfanas: {sum(n for n, _ in huerfanos.values()) if huerfanos else 0}')

        if not opciones['confirmar']:
            self.stdout.write('Solo revisión. Para convertir, ejecuta de nuevo con --confirmar.')
            return
        if huerfanos:
            raise CommandError('Hay filas huérfanas. Corrígelas antes de convertir; no se modificó nada.')
        if set(estado['motores']) == {'InnoDB'} and estado['fk']:
            self.stdout.write(self.style.SUCCESS('La base ya está en InnoDB con claves foráneas. No hay nada que hacer.'))
            return

        carpeta = Path(opciones['carpeta'])
        carpeta.mkdir(parents=True, exist_ok=True)
        archivo = carpeta / f'{base}_datos_{datetime.now():%Y%m%d_%H%M}.json'
        self.respaldar_datos(archivo)
        self.stdout.write(f'1) Datos respaldados en {archivo}')

        conteo_antes = estado['conteo']
        self.mover_tablas(base, respaldo)
        self.stdout.write(f'2) Tablas actuales movidas a {respaldo}')

        call_command('migrate', verbosity=0)
        ContentType.objects.clear_cache()
        self.stdout.write('3) Tablas creadas en InnoDB con sus claves foráneas')

        salida = StringIO()
        call_command('loaddata', str(archivo), stdout=salida)
        self.stdout.write(f'4) {salida.getvalue().strip()}')

        despues = self.estado()
        diferencias = {t: (conteo_antes.get(t), despues['conteo'].get(t))
                       for t in set(conteo_antes) | set(despues['conteo']) if conteo_antes.get(t) != despues['conteo'].get(t)}
        self.stdout.write(f'Motores: {despues["motores"]} | claves foráneas: {despues["fk"]}')
        self.stdout.write(f'Filas: {sum(conteo_antes.values())} -> {sum(despues["conteo"].values())}')
        self.stdout.write(f'Tablas con distinto número de filas: {diferencias or "ninguna"}')
        self.stdout.write(self.style.SUCCESS(f'Conversión terminada. Las tablas anteriores siguen en {respaldo}.'))

    def estado(self):
        with connection.cursor() as c:
            c.execute('SELECT ENGINE, COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() GROUP BY ENGINE')
            motores = dict(c.fetchall())
            c.execute("SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_TYPE = 'FOREIGN KEY'")
            fk = c.fetchone()[0]
            conteo = {}
            for tabla in connection.introspection.table_names(c):
                if tabla.lower() not in TABLAS_SIN_COMPARAR:
                    c.execute(f'SELECT COUNT(*) FROM {connection.ops.quote_name(tabla)}')
                    conteo[tabla.lower()] = c.fetchone()[0]
        return {'motores': motores, 'fk': fk, 'conteo': conteo}

    def huerfanos(self):
        q = connection.ops.quote_name
        encontrados = {}
        with connection.cursor() as c:
            existentes = {t.lower() for t in connection.introspection.table_names(c)}
            for modelo in apps.get_models(include_auto_created=True):
                tabla = modelo._meta.db_table
                if tabla.lower() not in existentes:
                    continue
                for campo in modelo._meta.concrete_fields:
                    if not (campo.many_to_one or campo.one_to_one):
                        continue
                    destino = campo.related_model._meta.db_table
                    col = campo.target_field.column
                    c.execute(f'SELECT t.{q(campo.column)}, COUNT(*) FROM {q(tabla)} t LEFT JOIN {q(destino)} d ON t.{q(campo.column)} = d.{q(col)} '
                              f'WHERE t.{q(campo.column)} IS NOT NULL AND d.{q(col)} IS NULL GROUP BY t.{q(campo.column)}')
                    filas = c.fetchall()
                    if filas:
                        valores = ', '.join(str(v) for v, _ in filas[:10])
                        encontrados[f'{tabla}.{campo.column} -> {destino}.{col}: valores inexistentes {valores}'] = (sum(n for _, n in filas), valores)
        return {texto: datos for texto, datos in encontrados.items()}

    def respaldar_datos(self, archivo):
        salida = StringIO()
        call_command('dumpdata', '--natural-foreign', '--exclude', 'contenttypes', '--exclude', 'auth.permission',
                     '--exclude', 'sessions', '--exclude', 'admin.logentry', stdout=salida)
        datos = json.loads(salida.getvalue())
        validos = {(m._meta.app_label.lower(), m._meta.model_name) for m in apps.get_models(include_auto_created=True)}
        for objeto in datos:
            for campo in ('permissions', 'user_permissions'):
                if campo in objeto['fields']:
                    objeto['fields'][campo] = [p for p in objeto['fields'][campo] if (p[1].lower(), p[2]) in validos]
        archivo.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')

    def mover_tablas(self, base, respaldo):
        q = connection.ops.quote_name
        with connection.cursor() as c:
            c.execute('SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s', [base])
            juego, cotejo = c.fetchone()
            c.execute('SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s', [respaldo])
            if c.fetchone()[0]:
                c.execute('SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s', [respaldo])
                if c.fetchone()[0]:
                    raise CommandError(f'La base {respaldo} ya tiene tablas. Revísala antes de continuar; no se modificó nada.')
            else:
                c.execute(f'CREATE DATABASE {q(respaldo)} CHARACTER SET {juego} COLLATE {cotejo}')
            tablas = connection.introspection.table_names(c)
            c.execute('RENAME TABLE ' + ', '.join(f'{q(base)}.{q(t)} TO {q(respaldo)}.{q(t)}' for t in tablas))
