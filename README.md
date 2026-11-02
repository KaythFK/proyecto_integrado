Sistema de Gestión y Registro Territorial (SGR)

📌 Descripción del Proyecto

El Sistema de Gestión y Registro Territorial (SGR) es una plataforma web desarrollada para la Ilustre Municipalidad (o entidad territorial correspondiente), diseñada para optimizar, registrar y monitorear las intervenciones, actividades y compromisos en los diferentes territorios.
El sistema permite una gestión descentralizada pero controlada, asegurando la trazabilidad de cada requerimiento ciudadano y evaluando el cumplimiento de los equipos a través de indicadores de desempeño en tiempo real.

Aplicación desplegada en AWS EC2: http://34.238.129.191

🚀 Arquitectura y Tecnologías

Este proyecto está construido bajo el framework web Django, utilizando un patrón de diseño orientado al Dominio de Datos (Apps independientes por entidad principal) y una estricta separación de interfaces por Rol de Usuario.
Backend: Python 3.x, Django 5.2.1
Base de Datos: Relacional (MySQL)
Frontend: HTML5, CSS3, Bootstrap 5 (Diseño Responsivo)
Visualización de Datos: Chart.js (Gráficos y Semáforos de cumplimiento)
Correo: PHPMailer (SMTP de Gmail) para la recuperación de contraseña
Despliegue: AWS EC2 (Amazon Linux 2023), Apache y Gunicorn.

🏢 Estructura de Aplicaciones (Domain-Driven)

El sistema está dividido en módulos escalables:
usuariosApp: Gestión de autenticación, perfiles y permisos (RBAC).
administracionApp: Mantenedores de Profesionales, Delegaciones y entidades base.
actividadApp: Núcleo transaccional. Creación, edición, cambio de estado (borrado lógico) y evidencias de las actividades territoriales.
tuboApp: Pipeline de "Compromisos" (Agenda colectiva), control de fechas de vencimiento y observaciones.
monitoreoApp: Portal exclusivo para el monitoreo y auditoría por parte de los Delegados.

👥 Roles de Usuario y Funcionalidades

El sistema implementa un modelo de control de acceso basado en roles (Role-Based Access Control):
Administrador: Acceso a la configuración global, creación de usuarios, asignación de delegaciones y mantenedores.
Delegado: Supervisa una delegación específica. Tiene acceso a un Dashboard con resumen ejecutivo del territorio, audita las actividades de su equipo y monitorea el Tubo de Compromisos de su jurisdicción.
Profesional: Operador en terreno. Registra actividades (autogenerando códigos únicos ACT-YYYY-XXX), adjunta documentación técnica/evidencias, y actualiza el progreso de sus compromisos asignados.

🔑Recuperación de contraseña

1. En el login, el usuario presiona **¿Olvidaste tu contraseña?** e ingresa su correo.
2. Django genera un token seguro (`default_token_generator`) y arma el enlace `/usuarios/restablecer-clave/<uid>/<token>/`.
3. El correo se envía con **PHPMailer**: Django ejecuta el script `enviar_correo.php` del servidor y le entrega el destinatario y el enlace.
4. El enlace caduca en 5 minutos y sirve una sola vez.
5. El usuario define su nueva contraseña (mínimo 8 caracteres, una mayúscula y un carácter especial) y vuelve al login.

🛠️ Instalación y Despliegue Local
Sigue estos pasos para levantar el entorno de desarrollo en tu máquina local:
Clonar el repositorio:
git clone <https://github.com/KaythFK/proyecto_integrado.git>
cd <proyecto_integrado>

Crear y activar un entorno virtual (recomendado):
python -m venv venv
# En Windows:
venv\Scripts\activate
# En macOS/Linux:
source venv/bin/activate

Instalar las dependencias:
pip install -r requirements.txt

Crear el archivo .env en la raíz del proyecto

Aplicar las migraciones a la base de datos:

python manage.py makemigrations
python manage.py migrate

Crear un superusuario (Administrador inicial):
python manage.py createsuperuser

Ejecutar el servidor de desarrollo:
python manage.py runserver
El sistema estará disponible en http://127.0.0.1:8000/. Sin PHP instalado y con DEBUG = True, el enlace de recuperación se muestra en la consola en vez de enviarse por correo.

Variables de entorno

El archivo .env no se sube al repositorio (está en .gitignore).

DB_ENGINE=django.db.backends.mysql
DB_NAME=municipalidad_db
DB_USER=usuario
DB_PASSWORD=contraseña
DB_HOST=localhost
DB_PORT=3306

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=correo@gmail.com
SMTP_PASSWORD=contraseña_de_aplicación_de_google
SMTP_FROM_NAME=Delegaciones Municipales
PHPMAILER_SCRIPT=/home/ec2-user/phpmailer/enviar_correo.php
Despliegue en AWS EC2

🛠️Despliegue en AWS EC2
Proyecto: /var/www/proyecto_inte2
Servidor: Apache como servidor web y Gunicorn como servidor de aplicación (servicio gunicorn).
PHPMailer: se instala PHP (sudo dnf install -y php-cli) y se clona la librería en /home/ec2-user/phpmailer, junto al script enviar_correo.php.

Para actualizar el servidor:

cd /var/www/proyecto_inte2
git pull --no-edit origin main
source proyecto_inte2/bin/activate
python manage.py migrate
sudo systemctl restart gunicorn

Integrantes
Kathalyna Higuera
Beatriz López
