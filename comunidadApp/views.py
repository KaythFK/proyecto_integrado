from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.db import transaction
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.forms.models import model_to_dict

from usuariosApp.decorators import role_required
from .models import OrganizacionComunitaria, AfiliacionVecino, CargaFamiliar, VinculoFamiliar
from .forms import OrganizacionComunitariaForm, AfiliacionVecinoForm, CargaFamiliarForm, VincularCargaForm
from administracionApp.models import Profesional, Auditoria, Vecino
from config.utils import delegacion_del_profesional
from django.utils.http import url_has_allowed_host_and_scheme
from django.db.models import Case, When, Value, IntegerField
from django.core.exceptions import ValidationError



# --- FUNCIÓN AUXILIAR DE AUDITORÍA ---
def registrar_auditoria(request, evento, entidad, objeto_instancia, datos_anteriores=None):
    """
    Función centralizada para registrar auditoría con descripciones legibles.
    """
    try:
        profesional_actual = Profesional.objects.filter(usuario=request.user).first() if request.user.is_authenticated else None
        if profesional_actual is None:
            print(f"Auditoría omitida: {request.user} no tiene un perfil de funcionario asociado.")
            return
        identificador = getattr(objeto_instancia, 'pk', 0)
        
        diccionario_nuevo = model_to_dict(objeto_instancia)
        datos_nuevos_limpios = {k: str(v) for k, v in diccionario_nuevo.items()}
        datos_nuevos_limpios['descripcion_legible'] = str(objeto_instancia)
        
        datos_anteriores_limpios = None
        if datos_anteriores:
            datos_anteriores_limpios = {k: str(v) for k, v in datos_anteriores.items()}
            datos_anteriores_limpios['descripcion_legible'] = str(objeto_instancia)

        Auditoria.objects.create(
            evento=evento,
            entidad=entidad,
            identificador=identificador,
            valor_anterior=datos_anteriores_limpios,
            valor_nuevo=datos_nuevos_limpios,
            funcionario_id_funcionario=profesional_actual
        )
    except Exception as e:
        print(f"Error interno registrando auditoría: {e}")
# ---------------------------------------


# --- CRUD ORGANIZACIONES COMUNITARIAS ---

@login_required
@role_required('Administrador', 'Profesional')
def lista_organizaciones(request):
    query = request.GET.get('q')
    delegacion_prof = delegacion_del_profesional(request.user)

    if delegacion_prof is False:
        organizaciones = OrganizacionComunitaria.objects.none()
    elif delegacion_prof is not None:
        organizaciones = OrganizacionComunitaria.objects.filter(id_delegacion=delegacion_prof)
    else:
        organizaciones = OrganizacionComunitaria.objects.all()

    organizaciones = organizaciones.order_by('nombre')

    if query:
        organizaciones = organizaciones.filter(
            Q(nombre__icontains=query) |
            Q(territorio__icontains=query) |
            Q(n_reg_pj__icontains=query) |
            Q(subtipo__icontains=query)
        ).distinct()

    return render(request, 'administrador/organizaciones/lista_organizaciones.html', {
        'organizaciones': organizaciones,
        'query': query,
        'delegacion_profesional': delegacion_prof if delegacion_prof else None,
    })


@login_required
@role_required('Administrador', 'Profesional')
def crear_organizacion(request):
    delegacion_prof = delegacion_del_profesional(request.user)
    if delegacion_prof is False:
        messages.error(request, 'Tu usuario Profesional no tiene una delegación asignada.')
        return redirect('comunidadApp:lista_organizaciones')

    if request.method == 'POST':
        form = OrganizacionComunitariaForm(request.POST, delegacion=delegacion_prof)
        if form.is_valid():
            try:
                with transaction.atomic():
                    organizacion = form.save(commit=False)
                    if delegacion_prof is not None:
                        organizacion.id_delegacion = delegacion_prof
                    organizacion.estado = True
                    organizacion.save()

                    registrar_auditoria(request, "CREACION", "OrganizacionComunitaria", organizacion)

                messages.success(request, f'La organización "{organizacion.nombre}" fue registrada con éxito.')
                return redirect('comunidadApp:lista_organizaciones')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = OrganizacionComunitariaForm(delegacion=delegacion_prof)

    return render(request, 'administrador/organizaciones/form_organizaciones.html', {
        'form': form,
        'titulo': 'Registrar Nueva Organización Comunitaria'
    })


@login_required
@role_required('Administrador', 'Profesional')
def editar_organizacion(request, id_organizacion):
    delegacion_prof = delegacion_del_profesional(request.user)
    qs_base = OrganizacionComunitaria.objects.all()
    if delegacion_prof is False:
        qs_base = OrganizacionComunitaria.objects.none()
    elif delegacion_prof is not None:
        qs_base = qs_base.filter(id_delegacion=delegacion_prof)

    organizacion = get_object_or_404(qs_base, id_organizacion=id_organizacion)

    if request.method == 'POST':
        datos_antiguos = model_to_dict(organizacion)
        form = OrganizacionComunitariaForm(request.POST, instance=organizacion, delegacion=delegacion_prof)
        if form.is_valid():
            try:
                with transaction.atomic():
                    org_guardada = form.save(commit=False)
                    if delegacion_prof is not None:
                        org_guardada.id_delegacion = delegacion_prof
                    org_guardada.save()

                    registrar_auditoria(request, "EDICION", "OrganizacionComunitaria", org_guardada, datos_antiguos)

                messages.success(request, f'La organización "{org_guardada.nombre}" fue actualizada.')
                return redirect('comunidadApp:lista_organizaciones')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = OrganizacionComunitariaForm(instance=organizacion, delegacion=delegacion_prof)

    return render(request, 'administrador/organizaciones/form_organizaciones.html', {
        'form': form,
        'titulo': 'Editar Organización Comunitaria'
    })


@login_required
@role_required('Administrador', 'Profesional')
def cambiar_estado_organizacion(request, id_organizacion):
    if request.method == 'POST':
        delegacion_prof = delegacion_del_profesional(request.user)
        qs_base = OrganizacionComunitaria.objects.all()
        if delegacion_prof is False:
            qs_base = OrganizacionComunitaria.objects.none()
        elif delegacion_prof is not None:
            qs_base = qs_base.filter(id_delegacion=delegacion_prof)

        organizacion = get_object_or_404(qs_base, id_organizacion=id_organizacion)

        with transaction.atomic():
            datos_antiguos = model_to_dict(organizacion)
            nuevo_estado = not organizacion.estado
            organizacion.estado = nuevo_estado
            organizacion.save()

            registrar_auditoria(request, "CAMBIO_ESTADO", "OrganizacionComunitaria", organizacion, datos_antiguos)

        accion = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'La organización "{organizacion.nombre}" fue {accion}.')

    return redirect('comunidadApp:lista_organizaciones')



# --- CRUD AFILIACIONES DE VECINOS ---




def _resolver_next_seguro(request, fallback_url):
    siguiente = (request.POST.get('next') or request.GET.get('next') or '').strip()
    if siguiente and siguiente.startswith('/') and url_has_allowed_host_and_scheme(
        url=siguiente,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return siguiente
    return fallback_url


@login_required
@role_required('Administrador', 'Profesional')
def lista_afiliaciones(request):
    query = (request.GET.get('q') or '').strip()
    organizacion_id = (request.GET.get('organizacion') or '').strip()
    delegacion_prof = delegacion_del_profesional(request.user)

    if delegacion_prof is False:
        afiliaciones = AfiliacionVecino.objects.none()
    elif delegacion_prof is not None:
        afiliaciones = AfiliacionVecino.objects.filter(
            Q(organizacion__id_delegacion=delegacion_prof) |
            Q(organizacion__tipo=OrganizacionComunitaria.TipoOrganizacion.FUNCIONAL)
        )
    else:
        afiliaciones = AfiliacionVecino.objects.all()

    afiliaciones = afiliaciones.select_related('vecino', 'organizacion').order_by('-id_afiliacion')

    if organizacion_id.isdigit():
        afiliaciones = afiliaciones.filter(organizacion_id=int(organizacion_id))

    if query:
        afiliaciones = afiliaciones.filter(
            Q(vecino__nombres__icontains=query) |
            Q(vecino__apellido_paterno__icontains=query) |
            Q(vecino__rut__icontains=query) |
            Q(organizacion__nombre__icontains=query) |
            Q(cargo_organizacion__icontains=query)
        ).distinct()

    organizaciones_filtro = OrganizacionComunitaria.objects.filter(estado=True).order_by('nombre')
    if delegacion_prof is not None and delegacion_prof is not False:
        organizaciones_filtro = organizaciones_filtro.filter(
            Q(id_delegacion=delegacion_prof) |
            Q(tipo=OrganizacionComunitaria.TipoOrganizacion.FUNCIONAL)
        ).distinct()

    return render(request, 'administrador/afiliaciones/lista_afiliaciones.html', {
        'afiliaciones': afiliaciones,
        'organizaciones_filtro': organizaciones_filtro,
        'organizacion_seleccionada': organizacion_id,
        'query': query,
    })


@login_required
@role_required('Administrador', 'Profesional')
def crear_afiliacion(request):
    vecino_id = (request.GET.get('vecino') or request.POST.get('vecino') or '').strip()
    vecino_obj = get_object_or_404(Vecino, pk=int(vecino_id)) if vecino_id.isdigit() else None

    organizacion_id = (request.GET.get('organizacion') or request.POST.get('organizacion') or '').strip()
    organizacion_obj = (
        get_object_or_404(OrganizacionComunitaria, pk=int(organizacion_id))
        if organizacion_id.isdigit()
        else None
    )

    delegacion_prof = delegacion_del_profesional(request.user)
    delegacion_filtro = delegacion_prof if (delegacion_prof and delegacion_prof is not False) else None
    next_url = _resolver_next_seguro(request, '')

    if request.method == 'POST':
        form = AfiliacionVecinoForm(request.POST, vecino=vecino_obj, delegacion=delegacion_filtro)
        if form.is_valid():
            try:
                with transaction.atomic():
                    afiliacion = form.save(commit=False)
                    if vecino_obj:
                        afiliacion.vecino = vecino_obj
                    afiliacion.estado = True
                    afiliacion.save()

                    registrar_auditoria(request, "CREACION", "AfiliacionVecino", afiliacion)

                messages.success(request, 'La afiliación del vecino fue registrada con éxito.')
                if next_url:
                    return redirect(next_url)
                return redirect('comunidadApp:lista_afiliaciones')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        initial_data = {}
        if vecino_obj:
            initial_data['vecino'] = vecino_obj
        if organizacion_obj:
            initial_data['organizacion'] = organizacion_obj
        form = AfiliacionVecinoForm(initial=initial_data, vecino=vecino_obj, delegacion=delegacion_filtro)

    return render(request, 'administrador/afiliaciones/form_afiliacion.html', {
        'form': form,
        'titulo': f'Registrar Afiliación para {vecino_obj}' if vecino_obj else 'Registrar Nueva Afiliación',
        'vecino_obj': vecino_obj,
        'organizacion_obj': organizacion_obj,
        'next_url': next_url,
    })


@login_required
@role_required('Administrador', 'Profesional')
def editar_afiliacion(request, id_afiliacion):
    afiliacion = get_object_or_404(AfiliacionVecino, id_afiliacion=id_afiliacion)
    delegacion_prof = delegacion_del_profesional(request.user)
    delegacion_filtro = delegacion_prof if (delegacion_prof and delegacion_prof is not False) else None
    next_url = _resolver_next_seguro(request, '')

    if request.method == 'POST':
        datos_antiguos = model_to_dict(afiliacion)
        form = AfiliacionVecinoForm(request.POST, instance=afiliacion, delegacion=delegacion_filtro)
        if form.is_valid():
            try:
                with transaction.atomic():
                    afiliacion_guardada = form.save()
                    registrar_auditoria(request, "EDICION", "AfiliacionVecino", afiliacion_guardada, datos_antiguos)

                messages.success(request, 'La afiliación fue actualizada correctamente.')
                if next_url:
                    return redirect(next_url)
                return redirect('comunidadApp:lista_afiliaciones')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = AfiliacionVecinoForm(instance=afiliacion, delegacion=delegacion_filtro)

    return render(request, 'administrador/afiliaciones/form_afiliacion.html', {
        'form': form,
        'titulo': 'Editar Afiliación',
        'next_url': next_url,
    })


@login_required
@role_required('Administrador', 'Profesional')
def cambiar_estado_afiliacion(request, id_afiliacion):
    if request.method == 'POST':
        afiliacion = get_object_or_404(AfiliacionVecino, id_afiliacion=id_afiliacion)

        with transaction.atomic():
            datos_antiguos = model_to_dict(afiliacion)
            nuevo_estado = not afiliacion.estado
            afiliacion.estado = nuevo_estado
            afiliacion.save()

            registrar_auditoria(request, "CAMBIO_ESTADO", "AfiliacionVecino", afiliacion, datos_antiguos)

        accion_str = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'La afiliación fue {accion_str} correctamente.')
        return redirect(_resolver_next_seguro(request, 'comunidadApp:lista_afiliaciones'))

    return redirect('comunidadApp:lista_afiliaciones')


from django.http import JsonResponse
from django.core.exceptions import ValidationError
from config.utils import validar_y_formatear_rut
from .forms import OrganizacionComunitariaForm, AfiliacionVecinoForm, CargaFamiliarForm, VincularCargaForm


@login_required
@role_required('Administrador', 'Profesional')
def buscar_carga_por_rut(request):
    rut_raw = (request.GET.get('rut') or '').strip()
    if not rut_raw:
        return JsonResponse({'encontrado': False, 'mensaje': ''})

    try:
        rut_formateado = validar_y_formatear_rut(rut_raw)
    except ValidationError:
        rut_formateado = rut_raw

    carga = (
        CargaFamiliar.objects
        .filter(Q(rut__iexact=rut_formateado) | Q(rut__iexact=rut_raw))
        .prefetch_related('vinculos__familiar')
        .first()
    )

    if not carga:
        return JsonResponse({
            'encontrado': False,
            'rut_formateado': rut_formateado,
            'mensaje': 'RUT no registrado previamente. Completa los datos para crear la carga.',
        })

    vinculos_activos = [
        {
            'familiar': f"{v.familiar.nombres} {v.familiar.apellido_paterno}",
            'parentesco': v.parentesco,
            'vive_con_este_vecino': v.vive_con_este_vecino,
        }
        for v in carga.vinculos.filter(estado=True)
    ]

    return JsonResponse({
        'encontrado': True,
        'carga': {
            'id_carga': carga.pk,
            'rut': carga.rut,
            'nombres': carga.nombres,
            'apellido_paterno': carga.apellido_paterno,
            'apellido_materno': carga.apellido_materno or '',
            'fecha_nacimiento': carga.fecha_nacimiento.strftime('%Y-%m-%d') if carga.fecha_nacimiento else '',
            'genero': carga.genero,
            'padres_separados': carga.padres_separados,
            'vinculos_activos': vinculos_activos,
        },
    })


@login_required
@role_required('Administrador', 'Profesional')
def lista_cargas(request):
    query = request.GET.get('q')
    cargas = CargaFamiliar.objects.all().order_by('-id_carga')

    if query:
        cargas = cargas.filter(
            Q(nombres__icontains=query) |
            Q(apellido_paterno__icontains=query) |
            Q(rut__icontains=query)
        ).distinct()

    return render(request, 'administrador/cargas/lista_cargas.html', {
        'cargas': cargas,
        'query': query,
    })


@login_required
@role_required('Administrador', 'Profesional')
def crear_carga(request):
    if request.method == 'POST':
        form = CargaFamiliarForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    carga = form.save(commit=False)
                    carga.estado = True
                    carga.save()
                    registrar_auditoria(request, "CREACION", "CargaFamiliar", carga)

                messages.success(request, 'La carga familiar fue registrada con éxito.')
                return redirect('comunidadApp:lista_cargas')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = CargaFamiliarForm()

    return render(request, 'administrador/cargas/form_carga.html', {
        'form': form,
        'titulo': 'Registrar Carga Familiar',
    })


@login_required
@role_required('Administrador', 'Profesional')
def editar_carga(request, id_carga):
    carga = get_object_or_404(CargaFamiliar, pk=id_carga)

    if request.method == 'POST':
        datos_antiguos = model_to_dict(carga)
        form = CargaFamiliarForm(request.POST, instance=carga, carga_existente=carga)
        if form.is_valid():
            try:
                with transaction.atomic():
                    carga_guardada = form.save()
                    registrar_auditoria(request, "EDICION", "CargaFamiliar", carga_guardada, datos_antiguos)

                messages.success(request, 'La carga familiar fue actualizada correctamente.')
                return redirect('comunidadApp:lista_cargas')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = CargaFamiliarForm(instance=carga, carga_existente=carga)

    return render(request, 'administrador/cargas/form_carga.html', {
        'form': form,
        'titulo': 'Editar Carga Familiar',
    })


@login_required
@role_required('Administrador', 'Profesional')
def cambiar_estado_carga(request, id_carga):
    if request.method == 'POST':
        carga = get_object_or_404(CargaFamiliar, pk=id_carga)

        with transaction.atomic():
            datos_antiguos = model_to_dict(carga)
            nuevo_estado = not carga.estado
            carga.estado = nuevo_estado
            carga.save()
            registrar_auditoria(request, "CAMBIO_ESTADO", "CargaFamiliar", carga, datos_antiguos)

        accion_str = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'La carga familiar fue {accion_str} correctamente.')

    return redirect('comunidadApp:lista_cargas')


@login_required
@role_required('Administrador', 'Profesional')
def lista_vinculos(request):
    query = request.GET.get('q')
    vinculos = VinculoFamiliar.objects.all().select_related('carga', 'familiar').order_by('-id_vinculo')

    if query:
        vinculos = vinculos.filter(
            Q(carga__nombres__icontains=query) |
            Q(carga__apellido_paterno__icontains=query) |
            Q(carga__rut__icontains=query) |
            Q(familiar__nombres__icontains=query) |
            Q(familiar__apellido_paterno__icontains=query) |
            Q(parentesco__icontains=query)
        ).distinct()

    return render(request, 'administrador/vinculos/lista_vinculos.html', {
        'vinculos': vinculos,
        'query': query,
    })


@login_required
@role_required('Administrador', 'Profesional')
def crear_vinculo(request):
    vecino_id = (request.GET.get('vecino') or request.POST.get('vecino') or '').strip()
    vecino_obj = get_object_or_404(Vecino, pk=int(vecino_id)) if vecino_id.isdigit() else None

    next_url = _resolver_next_seguro(request, '')
    carga_existente = None

    if request.method == 'POST':
        carga_existente_id = (request.POST.get('carga_existente_id') or '').strip()
        if carga_existente_id.isdigit():
            carga_existente = CargaFamiliar.objects.filter(pk=int(carga_existente_id)).first()

        if carga_existente is None:
            rut_post = (request.POST.get('rut') or '').strip()
            if rut_post:
                try:
                    rut_limpio = validar_y_formatear_rut(rut_post)
                except ValidationError:
                    rut_limpio = rut_post
                carga_existente = CargaFamiliar.objects.filter(
                    Q(rut__iexact=rut_limpio) | Q(rut__iexact=rut_post)
                ).first()

        carga_form = CargaFamiliarForm(
            request.POST,
            instance=carga_existente,
            carga_existente=carga_existente,
        )
        form = VincularCargaForm(
            request.POST,
            carga_existente=carga_existente,
            vecino_fijo=vecino_obj,
        )

        if carga_form.is_valid() and form.is_valid():
            try:
                with transaction.atomic():
                    if carga_existente is not None:
                        carga = carga_existente
                        if carga_form.cleaned_data.get('padres_separados') and not carga.padres_separados:
                            datos_ant_carga = model_to_dict(carga)
                            carga.padres_separados = True
                            carga.save()
                            registrar_auditoria(request, "EDICION", "CargaFamiliar", carga, datos_ant_carga)
                    else:
                        carga = carga_form.save(commit=False)
                        carga.estado = True
                        carga.save()
                        registrar_auditoria(request, "CREACION", "CargaFamiliar", carga)

                    vinculo = form.save(commit=False)
                    vinculo.carga = carga
                    if vecino_obj is not None:
                        vinculo.familiar = vecino_obj
                    vinculo.estado = True
                    vinculo.save()
                    registrar_auditoria(request, "CREACION", "VinculoFamiliar", vinculo)

                if carga_existente is not None:
                    messages.success(
                        request,
                        f'Se reutilizó la carga "{carga}" sin duplicarla y se vinculó con "{vinculo.familiar}".'
                    )
                else:
                    messages.success(
                        request,
                        f'Se registró la carga "{carga}" y se vinculó con "{vinculo.familiar}".'
                    )

                if next_url:
                    return redirect(next_url)
                return redirect('comunidadApp:lista_vinculos')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        carga_id_get = (request.GET.get('carga') or '').strip()
        if carga_id_get.isdigit():
            carga_existente = CargaFamiliar.objects.filter(pk=int(carga_id_get)).first()

        carga_form = CargaFamiliarForm(instance=carga_existente, carga_existente=carga_existente)
        initial_data = {'familiar': vecino_obj} if vecino_obj else {}
        form = VincularCargaForm(
            initial=initial_data,
            carga_existente=carga_existente,
            vecino_fijo=vecino_obj,
        )

    return render(request, 'administrador/vinculos/form_vinculo.html', {
        'form': form,
        'carga_form': carga_form,
        'carga_existente': carga_existente,
        'vecino_obj': vecino_obj,
        'next_url': next_url,
        'titulo': 'Registrar Vínculo Familiar',
        'es_edicion': False,
    })


@login_required
@role_required('Administrador', 'Profesional')
def editar_vinculo(request, id_vinculo):
    vinculo = get_object_or_404(VinculoFamiliar, pk=id_vinculo)
    carga = vinculo.carga
    next_url = _resolver_next_seguro(request, '')

    if request.method == 'POST':
        datos_antiguos_vinculo = model_to_dict(vinculo)
        datos_antiguos_carga = model_to_dict(carga)

        carga_form = CargaFamiliarForm(request.POST, instance=carga, carga_existente=carga)
        form = VincularCargaForm(request.POST, instance=vinculo, carga_existente=carga)

        if carga_form.is_valid() and form.is_valid():
            try:
                with transaction.atomic():
                    carga_guardada = carga_form.save()
                    registrar_auditoria(request, "EDICION", "CargaFamiliar", carga_guardada, datos_antiguos_carga)

                    vinculo_guardado = form.save()
                    registrar_auditoria(request, "EDICION", "VinculoFamiliar", vinculo_guardado, datos_antiguos_vinculo)

                messages.success(request, 'El vínculo familiar fue actualizado correctamente.')
                if next_url:
                    return redirect(next_url)
                return redirect('comunidadApp:lista_vinculos')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        carga_form = CargaFamiliarForm(instance=carga, carga_existente=carga)
        form = VincularCargaForm(instance=vinculo, carga_existente=carga)

    return render(request, 'administrador/vinculos/form_vinculo.html', {
        'form': form,
        'carga_form': carga_form,
        'carga_existente': carga,
        'next_url': next_url,
        'titulo': 'Editar Vínculo Familiar',
        'es_edicion': True,
    })


@login_required
@role_required('Administrador', 'Profesional')
def cambiar_estado_vinculo(request, id_vinculo):
    if request.method == 'POST':
        vinculo = get_object_or_404(VinculoFamiliar, pk=id_vinculo)

        with transaction.atomic():
            datos_antiguos = model_to_dict(vinculo)
            nuevo_estado = not vinculo.estado
            vinculo.estado = nuevo_estado
            vinculo.save()
            registrar_auditoria(request, "CAMBIO_ESTADO", "VinculoFamiliar", vinculo, datos_antiguos)

        accion_str = "habilitado" if nuevo_estado else "inhabilitado"
        messages.success(request, f'El vínculo familiar fue {accion_str} correctamente.')

    return redirect('comunidadApp:lista_vinculos')

@login_required
@role_required('Administrador', 'Profesional', 'Delegado', 'Coordinador')
def detalle_organizacion(request, id_organizacion):
    delegacion_prof = delegacion_del_profesional(request.user)
    qs_base = OrganizacionComunitaria.objects.select_related('id_delegacion', 'organizacion_matriz')

    if delegacion_prof is False:
        qs_base = OrganizacionComunitaria.objects.none()
    elif delegacion_prof is not None:
        qs_base = qs_base.filter(
            Q(id_delegacion=delegacion_prof) |
            Q(tipo=OrganizacionComunitaria.TipoOrganizacion.FUNCIONAL)
        )

    organizacion = get_object_or_404(qs_base, id_organizacion=id_organizacion)
    query = (request.GET.get('q') or '').strip()

    # Prioriza cargos de directiva al inicio de la nómina (CA3 / KAN-364)
    prioridad_cargo = Case(
        When(cargo_organizacion__icontains='president', then=Value(1)),
        When(cargo_organizacion__icontains='secretari', then=Value(2)),
        When(cargo_organizacion__icontains='tesorer', then=Value(3)),
        default=Value(4),
        output_field=IntegerField(),
    )

    afiliaciones_activas = (
        AfiliacionVecino.objects.filter(organizacion=organizacion, estado=True)
        .select_related('vecino')
        .annotate(orden_directiva=prioridad_cargo)
        .order_by('orden_directiva', 'vecino__apellido_paterno', 'vecino__nombres')
    )

    if query:
        afiliaciones_activas = afiliaciones_activas.filter(
            Q(vecino__nombres__icontains=query) |
            Q(vecino__apellido_paterno__icontains=query) |
            Q(vecino__apellido_materno__icontains=query) |
            Q(vecino__rut__icontains=query) |
            Q(cargo_organizacion__icontains=query)
        ).distinct()

    afiliaciones_inactivas = (
        AfiliacionVecino.objects.filter(organizacion=organizacion, estado=False)
        .select_related('vecino')
        .order_by('-id_afiliacion')
    )

    return render(request, 'profesional/detalle_organizacion.html', {
        'organizacion': organizacion,
        'afiliaciones_activas': afiliaciones_activas,
        'afiliaciones_inactivas': afiliaciones_inactivas,
        'total_integrantes_activos': afiliaciones_activas.count(),
        'query': query,
    })


@login_required
@role_required('Profesional')
def panel_profesional(request):
    query = (request.GET.get('q') or '').strip()
    solo_separados = request.GET.get('separados') == '1'

    vinculos_qs = (
        VinculoFamiliar.objects.filter(estado=True, carga__estado=True)
        .select_related('carga', 'familiar')
        .prefetch_related('carga__vinculos__familiar')
        .order_by('-id_vinculo')
    )

    if solo_separados:
        vinculos_qs = vinculos_qs.filter(carga__padres_separados=True)

    if query:
        vinculos_qs = vinculos_qs.filter(
            Q(carga__nombres__icontains=query) |
            Q(carga__apellido_paterno__icontains=query) |
            Q(carga__rut__icontains=query) |
            Q(familiar__nombres__icontains=query) |
            Q(familiar__apellido_paterno__icontains=query) |
            Q(familiar__rut__icontains=query)
        ).distinct()

    total_cargas_activas = CargaFamiliar.objects.filter(estado=True).count()
    total_padres_separados = CargaFamiliar.objects.filter(estado=True, padres_separados=True).count()
    total_vinculos_activos = VinculoFamiliar.objects.filter(estado=True).count()

    filas_profesional = []
    for v in vinculos_qs:
        otros_progenitores = [
            otro for otro in v.carga.vinculos.all()
            if otro.estado and otro.familiar_id != v.familiar_id
        ]
        if v.vive_con_este_vecino:
            badge_residencia = 'Vive en este domicilio'
            badge_clase = 'bg-success'
        elif v.carga.padres_separados:
            badge_residencia = 'Padres separados - Vive con otro progenitor'
            badge_clase = 'bg-warning text-dark'
        else:
            badge_residencia = 'No vive en este domicilio'
            badge_clase = 'bg-secondary'

        filas_profesional.append({
            'vinculo': v,
            'carga': v.carga,
            'vecino': v.familiar,
            'otros_progenitores': otros_progenitores,
            'badge_residencia': badge_residencia,
            'badge_clase': badge_clase,
        })

    return render(request, 'profesional/panel_vinculos_profesional.html', {
        'filas_profesional': filas_profesional,
        'query': query,
        'solo_separados': solo_separados,
        'total_cargas_activas': total_cargas_activas,
        'total_padres_separados': total_padres_separados,
        'total_vinculos_activos': total_vinculos_activos,
        'rol_menu': 'profesional',
    })