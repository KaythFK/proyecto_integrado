from protocolo.base import CasoProtocolo


class CasoCP05(CasoProtocolo):
    codigo = 'CP-05'
    nombre = 'Gestión de roles y permisos'

    def test_protocolo(self):
        import os, sys
        from datetime import date
        from django.contrib.auth.models import User, Group
        from django.test import Client
        from django.urls import reverse
        from administracionApp.models import Auditoria, Cargo, Delegacion, Profesional
        from administracionApp.forms import UsuarioSeguridadForm
        from usuariosApp.models import RolSistema, asignar_rol, rol_principal
        from usuariosApp.views import destino_segun_rol
        from config.utils import etiqueta_funcionario

        centro = Delegacion.objects.create(nombre='Centro', territorio='Centro')
        cargo = Cargo.objects.create(nombre='Gestor', fecha_inicio=date(2026, 1, 1), fecha_termino=date(2026, 12, 31))
        def persona(nombre, rol):
            u = User.objects.create_user(nombre, password='x', first_name=nombre)
            asignar_rol(u, Group.objects.get_or_create(name=rol)[0])
            Profesional.objects.create(rut=f'{u.pk}-1', nombres=nombre, apellido_paterno='P', correo=f'{nombre}@x.cl',
                                       id_cargo=cargo, id_delegacion=centro, usuario=u, estado=True)
            return u
        admin = persona('Admin', 'Administrador')
        ana = persona('Ana', 'Profesional')

        ca = Client(); ca.force_login(admin)
        url_lista = reverse('usuariosApp:lista_roles')
        r = ca.get(url_lista)
        nombres = [rol.nombre for rol in r.context['roles']]
        self.verificar('Leer: el listado muestra los 4 perfiles base', r.status_code == 200 and nombres == ['Administrador', 'Coordinador', 'Delegado', 'Profesional'])
        self.verificar('Leer: cada rol muestra sus accesos', 'Registrar actividad' in r.content.decode() and 'Revisar evidencias' in r.content.decode())
        self.verificar('El menú del Administrador tiene Roles', 'usuariosApp/roles' in r.content.decode() or reverse('usuariosApp:lista_roles') in r.content.decode())

        url_crear = reverse('usuariosApp:crear_rol')
        def crear(nombre, perfil='Profesional', descripcion='Apoya el trabajo en terreno de la delegación'):
            return ca.post(url_crear, {'nombre': nombre, 'perfil_base': perfil, 'descripcion': descripcion})
        r = crear('Técnico de terreno')
        tecnico = RolSistema.objects.filter(grupo__name='Técnico de terreno').first()
        self.verificar('Crear: se crea el rol con su perfil base', r.status_code == 302 and tecnico and tecnico.perfil_base == 'Profesional' and not tecnico.es_base and tecnico.estado)
        self.verificar('Crear: queda en la Auditoría', Auditoria.objects.filter(entidad='RolSistema', evento='CREACION', identificador=tecnico.pk).exists())

        def errores(r, campo):
            return r.status_code == 200 and campo in r.context['form'].errors
        self.verificar('Validación: nombre muy corto', errores(crear('Te'), 'nombre'))
        self.verificar('Validación: no permite el nombre de un perfil base', errores(crear('delegado'), 'nombre'))
        self.verificar('Validación: no permite nombres repetidos (sin importar mayúsculas)', errores(crear('TÉCNICO DE TERRENO'), 'nombre'))
        self.verificar('Validación: el perfil base es obligatorio', errores(crear('Supervisor', perfil=''), 'perfil_base'))
        self.verificar('Validación: la descripción es obligatoria', errores(crear('Supervisor', descripcion='corta'), 'descripcion'))

        form = UsuarioSeguridadForm()
        opciones = [str(e) for _, e in form.fields['rol'].choices][1:]
        self.verificar('El formulario de usuario ofrece el rol nuevo con su perfil', 'Técnico de terreno (perfil Profesional)' in opciones)
        beto = persona('Beto', 'Técnico de terreno')
        self.verificar('Asignar: el usuario queda con su rol y su perfil base', set(beto.groups.values_list('name', flat=True)) == {'Técnico de terreno', 'Profesional'})
        self.verificar('Asignar: el rol que se muestra es el nuevo', rol_principal(beto).name == 'Técnico de terreno')
        self.verificar('Las listas de funcionarios muestran el rol nuevo', etiqueta_funcionario(beto.profesional) == 'Beto P (Técnico de terreno · Centro)')
        cb = Client(); cb.force_login(beto)
        self.verificar('Acceso: entra a lo de su perfil base (panel del Profesional)', cb.get(reverse('actividadApp:dashboard_profesional')).status_code == 200)
        self.verificar('Acceso: no entra a lo de otros perfiles', cb.get(reverse('monitoreoApp:dashboard_delegado')).status_code == 302)
        self.verificar('Al iniciar sesión va al panel de su perfil base', destino_segun_rol(beto) == 'actividadApp:dashboard_profesional')

        url_editar = reverse('usuariosApp:editar_rol', args=[tecnico.pk])
        r = ca.get(url_editar)
        self.verificar('Editar: muestra accesos y usuarios del rol', r.status_code == 200 and 'Beto' in r.content.decode() and 'Usuarios con este rol (1)' in r.content.decode())
        r = ca.post(url_editar, {'nombre': 'Técnico territorial', 'perfil_base': 'Delegado', 'descripcion': 'Acompaña al equipo de la delegación'})
        tecnico.refresh_from_db(); beto.refresh_from_db()
        self.verificar('Editar: cambia nombre y perfil base', r.status_code == 302 and tecnico.nombre == 'Técnico territorial' and tecnico.perfil_base == 'Delegado')
        self.verificar('Editar: sus usuarios cambian de accesos al instante', set(beto.groups.values_list('name', flat=True)) == {'Técnico territorial', 'Delegado'})
        self.verificar('Editar: queda en la Auditoría con valor anterior', Auditoria.objects.filter(entidad='RolSistema', evento='EDICION', identificador=tecnico.pk).first().valor_anterior['nombre'] == 'Técnico de terreno')

        url_estado = reverse('usuariosApp:cambiar_estado_rol', args=[tecnico.pk])
        r = ca.post(url_estado, follow=True)
        tecnico.refresh_from_db()
        self.verificar('Eliminar: no desactiva un rol con usuarios activos', tecnico.estado and 'Reasígnalos' in r.content.decode())
        base = RolSistema.objects.get(grupo__name='Profesional')
        r = ca.post(reverse('usuariosApp:cambiar_estado_rol', args=[base.pk]), follow=True)
        self.verificar('Eliminar: no desactiva un perfil base', RolSistema.objects.get(pk=base.pk).estado and 'no se pueden desactivar' in r.content.decode())
        asignar_rol(beto, Group.objects.get(name='Profesional'))
        ca.post(url_estado)
        tecnico.refresh_from_db()
        self.verificar('Eliminar: sin usuarios activos se desactiva (borrado lógico)', not tecnico.estado and Group.objects.filter(name='Técnico territorial').exists())
        self.verificar('Un rol inactivo no aparece al crear usuarios', 'Técnico territorial (perfil Delegado)' not in [str(e) for _, e in UsuarioSeguridadForm().fields['rol'].choices])
        ca.post(url_estado)
        self.verificar('Se puede volver a activar', RolSistema.objects.get(pk=tecnico.pk).estado)

        r = ca.post(reverse('usuariosApp:editar_rol', args=[base.pk]), {'nombre': 'Otro', 'perfil_base': 'Administrador', 'descripcion': 'Nueva descripción del perfil'})
        base.refresh_from_db()
        self.verificar('Perfil base: solo se edita la descripción', base.nombre == 'Profesional' and base.perfil_base == 'Profesional' and base.descripcion == 'Nueva descripción del perfil')

        cp = Client(); cp.force_login(ana)
        self.verificar('Solo el Administrador gestiona roles', cp.get(url_lista).status_code == 302)
        self.finalizar()
