from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse

from actividadApp.models import Actividad, CatalogoTipoGestion, GestionActividad
from administracionApp.models import Cargo, Delegacion, Profesional
from protocolo.base import CasoProtocolo
from protocolo.datos import crear


class CasoCP27(CasoProtocolo):
    codigo = 'CP-27'
    nombre = 'Atención social con hasta tres gestiones'

    def test_protocolo(self):
        cargo, delegacion = crear(Cargo), crear(Delegacion)
        usuario = User.objects.create_user('profesional', password='x')
        usuario.groups.add(Group.objects.get_or_create(name='Profesional')[0])
        profesional = Profesional.objects.create(rut='1-9', nombres='Ana', apellido_paterno='Rojas', correo='ana@p.cl',
                                                 id_cargo=cargo, id_delegacion=delegacion, usuario=usuario)
        atencion = crear(Actividad, id_profesional=profesional, codigo_unico='ACT-2026-0001')
        otra_atencion = crear(Actividad, id_profesional=profesional, codigo_unico='ACT-2026-0002')
        tipos = [CatalogoTipoGestion.objects.create(nombre=n) for n in ('Informe social', 'Derivación', 'Subsidio', 'Visita')]
        cliente = Client()
        cliente.force_login(usuario)
        url = reverse('actividadApp:crear_gestion', args=[atencion.pk])
        lista = reverse('actividadApp:lista_gestiones', args=[atencion.pk])

        def registrar(tipo, fecha, descripcion, actividad=atencion):
            return cliente.post(reverse('actividadApp:crear_gestion', args=[actividad.pk]),
                                {'tipo_gestion': tipo.pk, 'fecha_ejecucion': fecha, 'descripcion': descripcion})

        def activas(actividad=atencion):
            return GestionActividad.objects.filter(actividad=actividad, estado=True).count()

        registrar(tipos[0], '2026-11-02', 'Primera gestión')
        registrar(tipos[1], '2026-11-10', 'Segunda gestión')
        registrar(tipos[2], '2026-11-18', 'Tercera gestión')
        self.verificar('Registra tres gestiones con tipos y fechas distintas para la misma atención', activas() == 3
                       and GestionActividad.objects.filter(actividad=atencion).values('tipo_gestion').distinct().count() == 3)
        self.verificar('La secuencia completa se consulta desde la misma atención',
                       all(t in cliente.get(lista).content.decode() for t in ('Primera gestión', 'Segunda gestión', 'Tercera gestión')))

        respuesta = cliente.post(url, {'tipo_gestion': tipos[3].pk, 'fecha_ejecucion': '2026-11-20', 'descripcion': 'Cuarta gestión'}, follow=True)
        self.verificar('Rechaza una cuarta gestión activa en la misma atención', activas() == 3
                       and not GestionActividad.objects.filter(descripcion='Cuarta gestión').exists())
        self.verificar('Informa el motivo del rechazo', 'máximo permitido' in respuesta.content.decode())
        self.verificar('Con tres gestiones el formulario de registro no se abre', cliente.get(url).status_code == 302)
        pagina = cliente.get(lista).content.decode()
        self.verificar('La lista muestra el aviso de máximo alcanzado y oculta Nueva Gestión',
                       'Máximo de 3 gestiones alcanzado' in pagina and '+ Nueva Gestión' not in pagina)

        registrar(tipos[0], '2026-11-03', 'Gestión de otra atención', actividad=otra_atencion)
        self.verificar('Las gestiones de otra atención no cuentan para el límite', activas(otra_atencion) == 1 and activas() == 3)

        primera = GestionActividad.objects.get(descripcion='Primera gestión')
        cliente.post(reverse('actividadApp:cambiar_estado_gestion', args=[primera.pk]), HTTP_REFERER=lista)
        self.verificar('Al desactivar una gestión baja a dos activas', activas() == 2)
        registrar(tipos[3], '2026-11-20', 'Cuarta gestión')
        self.verificar('Con dos activas permite registrar otra', activas() == 3
                       and GestionActividad.objects.filter(descripcion='Cuarta gestión').exists())
        cliente.post(reverse('actividadApp:cambiar_estado_gestion', args=[primera.pk]), HTTP_REFERER=lista)
        primera.refresh_from_db()
        self.verificar('No permite reactivar una gestión si ya hay tres activas', not primera.estado and activas() == 3)
        self.finalizar()
