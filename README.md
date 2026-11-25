# Sistema de Gestión y Registro Territorial (SGR)

## Descripción

El Sistema de Gestión y Registro Territorial (SGR) es una plataforma web desarrollada para la Ilustre Municipalidad de La Serena. Permite registrar, monitorear y medir las actividades y compromisos de los equipos de cada delegación territorial, asegurando la trazabilidad de cada requerimiento ciudadano y evaluando el cumplimiento mediante metas, indicadores y un semáforo de desempeño.

La aplicación se encuentra desplegada en AWS EC2: https://34-238-129-191.sslip.io

## Tecnologías

El sistema está desarrollado en Python 3.14 con Django 5.2.1 y utiliza MySQL 8.4 como base de datos en el entorno local (WAMP) y MariaDB 10.5 en el servidor, ambos con el motor InnoDB. La interfaz está construida con HTML5, CSS3 y Bootstrap 5, y los gráficos con Chart.js. Además, usa django-filter para los filtros de listados, Pillow para el manejo de imágenes, openpyxl para los reportes en Excel y python-dotenv para las variables de entorno. Los correos se envían con PHPMailer mediante SMTP de Gmail. Las versiones exactas de las librerías se encuentran en `requirements.txt`.

## Estructura

El proyecto se organiza en aplicaciones independientes por dominio:

- `usuariosApp`: inicio de sesión, perfil, cambio obligatorio de contraseña temporal y recuperación de contraseña.
- `administracionApp`: mantenedores de profesionales, delegaciones, cargos, vecinos, períodos y catálogos, además de la auditoría del sistema.
- `actividadApp`: actividades, gestiones, evidencias, validaciones, retroalimentaciones y ausencias.
- `tuboApp`: Tubo de compromisos, con sus estados, vencimientos, reasignaciones y observaciones.
- `monitoreoApp`: metas, indicadores, semáforo, alertas, resultados bajo el umbral y tendencias por cargo.
- `comunidadApp`: organizaciones comunitarias, afiliaciones, cargas familiares y celebraciones.
- `config`: configuración general, menú por rol, utilidades compartidas y entrega protegida de archivos.

## Roles

El sistema utiliza control de acceso basado en roles, y cada usuario solo puede consultar y modificar la información que le corresponde. El Administrador gestiona la configuración global, los usuarios, los mantenedores, la auditoría y las reglas de alerta. El Coordinador tiene una visión global de todas las delegaciones y administra períodos, cargos, metas, indicadores y tendencias. El Delegado supervisa su delegación, valida las evidencias de su equipo y revisa los resultados bajo el umbral. El Profesional registra sus actividades y evidencias, gestiona sus compromisos y consulta su avance frente a lo esperado.

## Seguridad

Las contraseñas se almacenan con hash y deben tener al menos 8 caracteres, una mayúscula y un carácter especial. Al crear un usuario se genera una contraseña temporal, que debe cambiarse obligatoriamente en el primer ingreso. La recuperación de contraseña se realiza mediante un enlace enviado por correo, de un solo uso y con una vigencia de 5 minutos.

Cada vista valida el rol del usuario, y las actividades y compromisos validan además la delegación o el dueño del registro. Las fotos de evidencia y los respaldos de felicitaciones o reclamos solo se entregan a quien tiene permiso sobre ellos, y no es posible abrir ningún archivo sin sesión iniciada.

Toda operación crítica queda registrada en la auditoría con el usuario, la fecha, la acción, la entidad y los valores anterior y nuevo. Estos registros no pueden modificarse ni eliminarse, y cualquier intento de alterarlos queda registrado.

## Instalación local

Se requiere Python 3.12 o superior, MySQL 8 (por ejemplo, el incluido en WAMP) y Git. Primero se clona el repositorio, se crea un entorno virtual y se instalan las dependencias. Luego se crea en MySQL una base de datos vacía llamada `municipalidad_db`, con juego de caracteres `utf8mb4` y, en la raíz del proyecto, un archivo `.env` con las variables descritas más abajo. Finalmente se crean las tablas, el administrador inicial y se inicia el servidor:

```bash
git clone https://github.com/KaythFK/proyecto_integrado.git
cd proyecto_integrado
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

El sistema queda disponible en http://127.0.0.1:8000/. En macOS o Linux, el entorno virtual se activa con `source venv/bin/activate`. No es necesario ejecutar `makemigrations`, ya que las migraciones vienen incluidas en el repositorio. Después de cada `git pull` se recomienda ejecutar nuevamente `pip install -r requirements.txt` y `python manage.py migrate`, por si hay dependencias o tablas nuevas.

Para cargar las organizaciones comunitarias desde la planilla incluida en el repositorio se usa el siguiente comando. Con `--dry-run` solo simula la importación y muestra lo que haría, sin guardar cambios:

```bash
python manage.py importar_organizaciones_excel "base datos JJVV sin verificar.xlsx" --dry-run
python manage.py importar_organizaciones_excel "base datos JJVV sin verificar.xlsx"
```

Las pruebas automatizadas se ejecutan con `python manage.py test`. Django crea una base de datos temporal para las pruebas y la elimina al terminar, por lo que no se modifican los datos reales.

## Variables de entorno

El archivo `.env` no se incluye en el repositorio. Debe contener la configuración de la base de datos (`DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` y `DB_PORT`), los datos del servidor de correo (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` y `SMTP_FROM_NAME`) y la ruta del script de envío de correos (`PHPMAILER_SCRIPT`). Para usar MySQL, `DB_ENGINE` debe ser `django.db.backends.mysql`.

## Base de datos

Todas las tablas usan el motor InnoDB, que hace cumplir las claves foráneas en la propia base de datos: no permite guardar un registro que apunte a otro inexistente. El archivo `config/settings.py` fuerza InnoDB en cada conexión, porque algunas instalaciones de MySQL, como WAMP, usan MyISAM por defecto, que ignora las claves foráneas.

Una base creada antes con MyISAM se convierte con el comando `pasar_a_innodb`. Sin opciones solo revisa la base y muestra el motor de las tablas, la cantidad de claves foráneas y las filas huérfanas, es decir, registros que apuntan a otros que ya no existen. Con `--confirmar` respalda los datos en un archivo JSON, mueve las tablas actuales a la base `municipalidad_db_respaldo_myisam`, crea las tablas de nuevo en InnoDB y recarga los datos. Si encuentra filas huérfanas no realiza la conversión y deben corregirse antes:

```bash
python manage.py pasar_a_innodb
python manage.py pasar_a_innodb --confirmar
```

El usuario de la base de datos debe tener permiso para crear la base de respaldo. Una vez verificada la conversión, esa base puede eliminarse.

## Alertas

Las alertas de compromisos por vencer, evidencias pendientes y avance bajo el umbral se generan automáticamente mientras los usuarios navegan, con un máximo de una revisión cada 5 minutos. También pueden generarse manualmente o mediante una tarea programada con `python manage.py generar_alertas`.

## Despliegue en AWS EC2

El sistema se ejecuta en Amazon Linux 2023, con Nginx como servidor web, Gunicorn como servidor de aplicación y MariaDB 10.5 como base de datos. El certificado HTTPS se obtiene con Certbot para el dominio `34-238-129-191.sslip.io`, y Nginx redirige a ese dominio las visitas que llegan por la IP. El proyecto se encuentra en `/var/www/proyecto_inte2`. Para el envío de correos se instala PHP y la librería PHPMailer en `/home/ec2-user/phpmailer`. Los archivos subidos deben ser entregados por Django, por lo que Nginx no debe publicar directamente la carpeta `media`.

MariaDB debe configurarse con `lower_case_table_names=1` en la sección `[mysqld]` de su archivo de configuración, antes de importar la base. Los respaldos generados en Windows guardan los nombres de tabla en minúsculas, y sin este ajuste las tablas con mayúsculas, como las de organizaciones comunitarias, no se encuentran y esas páginas responden con error 500.

Para actualizar el servidor:

```bash
cd /var/www/proyecto_inte2
git pull --no-edit origin main
source proyecto_inte2/bin/activate
pip install -r requirements.txt
python manage.py migrate
sudo systemctl restart gunicorn
```

## Respaldo y recuperación

La base de datos se respalda con `mysqldump -u usuario -p --single-transaction municipalidad_db > respaldo.sql` y se restaura con `mysql -u usuario -p municipalidad_db < respaldo.sql`. Los archivos subidos se respaldan copiando la carpeta `media`. En Windows con WAMP, ambos procesos también pueden realizarse desde phpMyAdmin, con las opciones Exportar e Importar. Al importar un respaldo, la base de destino debe estar vacía. Después de importarlo conviene ejecutar `python manage.py pasar_a_innodb` para confirmar que todas las tablas quedaron en InnoDB con sus claves foráneas.

## Integrantes

Kathalyna Higuera y Beatriz López.

