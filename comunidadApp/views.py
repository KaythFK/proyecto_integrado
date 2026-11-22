from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.db import transaction
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.forms.models import model_to_dict

from usuariosApp.decorators import role_required
from .models import OrganizacionComunitaria, AfiliacionVecino, CargaFamiliar, VinculoFamiliar
from .forms import OrganizacionComunitariaForm, AfiliacionVecinoForm, CargaFamiliarForm, VinculoFamiliarForm
from administracionApp.models import Profesional, Auditoria, Vecino
from config.utils import delegacion_del_profesional
from django.utils.http import url_has_allowed_host_and_scheme
from django.db.models import Case, When, Value, IntegerField



# --- FUNCIÓN AUXILIAR DE AUDITORÍA ---
def registrar_auditoria(request, evento, entidad, objeto_instancia, datos_anteriores=None):
    """
    Función centralizada para registrar auditoría con descripciones legibles.
    """
    try:
        profesional_actual = Profesional.objects.filter(usuario=request.user).first() if request.user.is_authenticated else None
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
        'query': query
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
                    
                    # AUDITORIA
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
        'titulo': 'Registrar Carga Familiar'
    })

@login_required
@role_required('Administrador', 'Profesional')
def editar_carga(request, id_carga):
    carga = get_object_or_404(CargaFamiliar, pk=id_carga)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(carga)
        form = CargaFamiliarForm(request.POST, instance=carga)
        if form.is_valid():
            try:
                with transaction.atomic():
                    carga_guardada = form.save()
                    
                    # AUDITORIA
                    registrar_auditoria(request, "EDICION", "CargaFamiliar", carga_guardada, datos_antiguos)
                    
                messages.success(request, 'La carga familiar fue actualizada correctamente.')
                return redirect('comunidadApp:lista_cargas')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = CargaFamiliarForm(instance=carga)
        
    return render(request, 'administrador/cargas/form_carga.html', {
        'form': form,
        'titulo': 'Editar Carga Familiar'
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
            
            # AUDITORIA
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
        'query': query
    })

@login_required
@role_required('Administrador', 'Profesional')
def crear_vinculo(request):
    if request.method == 'POST':
        form = VinculoFamiliarForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    vinculo = form.save(commit=False)
                    vinculo.estado = True
                    vinculo.save()
                    
                    # AUDITORIA
                    registrar_auditoria(request, "CREACION", "VinculoFamiliar", vinculo)
                    
                messages.success(request, 'El vínculo familiar fue registrado con éxito.')
                return redirect('comunidadApp:lista_vinculos')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = VinculoFamiliarForm()
        
    return render(request, 'administrador/vinculos/form_vinculo.html', {
        'form': form,
        'titulo': 'Registrar Vínculo Familiar'
    })

@login_required
@role_required('Administrador', 'Profesional')
def editar_vinculo(request, id_vinculo):
    vinculo = get_object_or_404(VinculoFamiliar, pk=id_vinculo)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(vinculo)
        form = VinculoFamiliarForm(request.POST, instance=vinculo)
        if form.is_valid():
            try:
                with transaction.atomic():
                    vinculo_guardado = form.save()
                    
                    # AUDITORIA
                    registrar_auditoria(request, "EDICION", "VinculoFamiliar", vinculo_guardado, datos_antiguos)
                    
                messages.success(request, 'El vínculo familiar fue actualizado correctamente.')
                return redirect('comunidadApp:lista_vinculos')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = VinculoFamiliarForm(instance=vinculo)
        
    return render(request, 'administrador/vinculos/form_vinculo.html', {
        'form': form,
        'titulo': 'Editar Vínculo Familiar'
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
            
            # AUDITORIA
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