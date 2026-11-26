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
        parser.add_argument('--solo-motor', action='store_true',
                            help='Solo cambia a InnoDB el motor de las tablas existentes, sin recrearlas. Sirve para que migrate pueda '
                                 'crear tablas nuevas en una base que sigue en MyISAM; no agrega las claves foráneas de las tablas antiguas.')

    def handle(self, *args, **opciones):
        if connection.vendor != 'mysql':
            raise CommandError('Este comando solo aplica a bases MySQL o MariaDB.')
        base = connection.settings_dict['NAME']
        respaldo = f'{base}_respaldo_myisam'

        if opciones['solo_motor']:
            self.cambiar_motor()
            return

        estado = self.estado()
        esperadas = self.fk_esperadas()
        self.stdout.write(f'Base: {base}')
        self.stdout.write(f'Motores: {estado["motores"]} | claves foráneas: {estado["fk"]} de {esperadas} esperadas')
        pendientes = self.migraciones_pendientes()
        if pendientes:
            self.stdout.write(self.style.WARNING(f'Migraciones pendientes: {", ".join(pendientes)}'))
        huerfanos = self.huerfanos()
        for linea in huerfanos:
            self.stdout.write(self.style.WARNING(linea))
        self.stdout.write(f'Filas huérfanas: {sum(n for n, _ in huerfanos.values()) if huerfanos else 0}')

        if not opciones['confirmar']:
            self.stdout.write('Solo revisión. Para convertir, ejecuta de nuevo con --confirmar.')
            return
        if pendientes:
            raise CommandError('Hay migraciones pendientes. Ejecuta migrate (si falla por MyISAM, usa antes --solo-motor); no se modificó nada.')
        if huerfanos:
            raise CommandError('Hay filas huérfanas. Corrígelas antes de convertir; no se modificó nada.')
        if set(estado['motores']) == {'InnoDB'} and estado['fk'] >= esperadas:
            self.stdout.write(self.style.SUCCESS('La base ya está en InnoDB con todas sus claves foráneas. No hay nada que hacer.'))
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

    def cambiar_motor(self):
        q = connection.ops.quote_name
        with connection.cursor() as c:
            c.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
                      "AND TABLE_TYPE = 'BASE TABLE' AND ENGINE <> 'InnoDB'")
            tablas = [fila[0] for fila in c.fetchall()]
            for tabla in tablas:
                c.execute(f'ALTER TABLE {q(tabla)} ENGINE=InnoDB')
            self.stdout.write(self.style.SUCCESS(f'Tablas cambiadas a InnoDB: {len(tablas)}.'))
            self.limpiar_tablas_a_medias(c)
        self.stdout.write('Ahora ejecuta migrate.')

    def limpiar_tablas_a_medias(self, c):
        """Elimina las tablas y columnas vacías que dejó creadas una migración pendiente que falló, para que migrate pueda crearlas de nuevo."""
        from django.db.migrations.executor import MigrationExecutor
        from django.db.migrations.operations import AddField, CreateModel
        q = connection.ops.quote_name
        existentes = {t.lower(): t for t in connection.introspection.table_names(c)}
        ejecutor = MigrationExecutor(connection)
        for migracion, _ in ejecutor.migration_plan(ejecutor.loader.graph.leaf_nodes()):
            for operacion in migracion.operations:
                if isinstance(operacion, AddField):
                    try:
                        modelo = apps.get_model(migracion.app_label, operacion.model_name)
                        columna = modelo._meta.get_field(operacion.name).column
                    except (LookupError, Exception):
                        continue
                    tabla = existentes.get(modelo._meta.db_table.lower())
                    if not tabla:
                        continue
                    columnas = {col.name.lower(): col.name for col in connection.introspection.get_table_description(c, tabla)}
                    if columna.lower() not in columnas:
                        continue
                    c.execute(f'SELECT COUNT(*) FROM {q(tabla)} WHERE {q(columnas[columna.lower()])} IS NOT NULL')
                    if c.fetchone()[0]:
                        self.stdout.write(self.style.WARNING(f'La columna {tabla}.{columna} de la migración pendiente '
                                                             f'{migracion.app_label}.{migracion.name} tiene datos; no se eliminó.'))
                        continue
                    c.execute(f'ALTER TABLE {q(tabla)} DROP COLUMN {q(columnas[columna.lower()])}')
                    self.stdout.write(f'Columna vacía {tabla}.{columna} eliminada: había quedado a medias por la migración {migracion.app_label}.{migracion.name}.')
                    continue
                if not isinstance(operacion, CreateModel):
                    continue
                try:
                    tabla = apps.get_model(migracion.app_label, operacion.name)._meta.db_table
                except LookupError:
                    continue
                if tabla.lower() not in existentes:
                    continue
                c.execute(f'SELECT COUNT(*) FROM {q(existentes[tabla.lower()])}')
                if c.fetchone()[0]:
                    self.stdout.write(self.style.WARNING(f'La tabla {tabla} de la migración pendiente {migracion.app_label}.{migracion.name} '
                                                         f'tiene datos; no se eliminó. Revísala antes de ejecutar migrate.'))
                    continue
                c.execute(f'DROP TABLE {q(existentes[tabla.lower()])}')
                self.stdout.write(f'Tabla vacía {tabla} eliminada: había quedado a medias por la migración {migracion.app_label}.{migracion.name}.')

    def fk_esperadas(self):
        return sum(1 for modelo in apps.get_models(include_auto_created=True) for campo in modelo._meta.concrete_fields
                   if (campo.many_to_one or campo.one_to_one) and getattr(campo, 'db_constraint', True))

    def migraciones_pendientes(self):
        from django.db.migrations.executor import MigrationExecutor
        ejecutor = MigrationExecutor(connection)
        plan = ejecutor.migration_plan(ejecutor.loader.graph.leaf_nodes())
        return [f'{migracion.app_label}.{migracion.name}' for migracion, _ in plan]

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
                columnas = {col.name.lower() for col in connection.introspection.get_table_description(c, tabla)}
                for campo in modelo._meta.concrete_fields:
                    if not (campo.many_to_one or campo.one_to_one) or campo.column.lower() not in columnas:
                        continue
                    destino = campo.related_model._meta.db_table
                    if destino.lower() not in existentes:
                        continue
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
