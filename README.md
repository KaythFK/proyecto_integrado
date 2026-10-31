Sistema de Gestión y Registro Territorial (SGR)

📌 Descripción del Proyecto

El Sistema de Gestión y Registro Territorial (SGR) es una plataforma web desarrollada para la Ilustre Municipalidad (o entidad territorial correspondiente), diseñada para optimizar, registrar y monitorear las intervenciones, actividades y compromisos en los diferentes territorios.

El sistema permite una gestión descentralizada pero controlada, asegurando la trazabilidad de cada requerimiento ciudadano y evaluando el cumplimiento de los equipos a través de indicadores de desempeño en tiempo real.

🚀 Arquitectura y Tecnologías

Este proyecto está construido bajo el framework web Django, utilizando un patrón de diseño orientado al Dominio de Datos (Apps independientes por entidad principal) y una estricta separación de interfaces por Rol de Usuario.

Backend: Python 3.x, Django 5.2.1

Base de Datos: Relacional (MySQL)

Frontend: HTML5, CSS3, Bootstrap 5 (Diseño Responsivo)

Visualización de Datos: Chart.js (Gráficos y Semáforos de cumplimiento)

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


Aplicar las migraciones a la base de datos:

python manage.py makemigrations
python manage.py migrate


Crear un superusuario (Administrador inicial):

python manage.py createsuperuser


Ejecutar el servidor de desarrollo:

python manage.py runserver


El sistema estará disponible en http://127.0.0.1:8000/, nuestro proyecto es desplegado en una instancia de AWS para su acceso.
