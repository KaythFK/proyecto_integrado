from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.db import transaction
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from usuariosApp.decorators import role_required
from .models import OrganizacionComunitaria, AfiliacionVecino, CargaFamiliar, VinculoFamiliar
from .forms import OrganizacionComunitariaForm, AfiliacionVecinoForm, CargaFamiliarForm, VinculoFamiliarForm
from administracionApp.models import Profesional, Auditoria # Añadido Auditoria

import json
from django.forms.models import model_to_dict

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
    organizaciones = OrganizacionComunitaria.objects.all().order_by('nombre')
    
    if query:
        organizaciones = organizaciones.filter(
            Q(nombre__icontains=query) |
            Q(territorio__icontains=query) |
            Q(rut_pj__icontains=query)
        ).distinct()
        
    return render(request, 'administrador/organizaciones/lista_organizaciones.html', {
        'organizaciones': organizaciones,
        'query': query
    })

@login_required
@role_required('Administrador', 'Profesional')
def crear_organizacion(request):
    if request.method == 'POST':
        form = OrganizacionComunitariaForm(request.POST)
        if form.is_valid():
            try:
                organizacion = form.save(commit=False)
                organizacion.estado = True
                organizacion.save()
                
                # AUDITORIA
                registrar_auditoria(request, "CREACION", "OrganizacionComunitaria", organizacion)
                
                messages.success(request, f'La organización "{organizacion.nombre}" fue registrada con éxito.')
                return redirect('comunidadApp:lista_organizaciones')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = OrganizacionComunitariaForm()
        
    return render(request, 'administrador/organizaciones/form_organizaciones.html', {
        'form': form,
        'titulo': 'Registrar Nueva Organización Comunitaria'
    })

@login_required
@role_required('Administrador', 'Profesional')
def editar_organizacion(request, id_organizacion):
    organizacion = get_object_or_404(OrganizacionComunitaria, id_organizacion=id_organizacion)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(organizacion)
        form = OrganizacionComunitariaForm(request.POST, instance=organizacion)
        if form.is_valid():
            try:
                org_guardada = form.save()
                
                # AUDITORIA
                registrar_auditoria(request, "EDICION", "OrganizacionComunitaria", org_guardada, datos_antiguos)
                
                messages.success(request, f'La organización "{organizacion.nombre}" fue actualizada.')
                return redirect('comunidadApp:lista_organizaciones')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = OrganizacionComunitariaForm(instance=organizacion)
        
    return render(request, 'administrador/organizaciones/form_organizaciones.html', {
        'form': form,
        'titulo': 'Editar Organización Comunitaria'
    })

@login_required
@role_required('Administrador', 'Profesional')
def cambiar_estado_organizacion(request, id_organizacion):
    if request.method == 'POST':
        organizacion = get_object_or_404(OrganizacionComunitaria, id_organizacion=id_organizacion)
        
        with transaction.atomic():
            datos_antiguos = model_to_dict(organizacion)
            nuevo_estado = not organizacion.estado
            organizacion.estado = nuevo_estado
            organizacion.save()
            
            # AUDITORIA
            registrar_auditoria(request, "CAMBIO_ESTADO", "OrganizacionComunitaria", organizacion, datos_antiguos)
                
        accion = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'La organización "{organizacion.nombre}" fue {accion}.')
        
    return redirect('comunidadApp:lista_organizaciones')



# --- CRUD AFILIACIONES DE VECINOS ---

@login_required
@role_required('Administrador', 'Profesional')
def lista_afiliaciones(request):
    query = request.GET.get('q')
    afiliaciones = AfiliacionVecino.objects.all().select_related('vecino', 'organizacion').order_by('-id_afiliacion')
    
    if query:
        afiliaciones = afiliaciones.filter(
            Q(vecino__nombres__icontains=query) |
            Q(vecino__apellido_paterno__icontains=query) |
            Q(vecino__rut__icontains=query) |
            Q(organizacion__nombre__icontains=query)
        ).distinct()
        
    return render(request, 'administrador/afiliaciones/lista_afiliaciones.html', {
        'afiliaciones': afiliaciones,
        'query': query
    })

@login_required
@role_required('Administrador', 'Profesional')
def crear_afiliacion(request):
    if request.method == 'POST':
        form = AfiliacionVecinoForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    afiliacion = form.save(commit=False)
                    afiliacion.estado = True
                    afiliacion.save()
                    
                    # AUDITORIA
                    registrar_auditoria(request, "CREACION", "AfiliacionVecino", afiliacion)
                    
                messages.success(request, 'La afiliación del vecino fue registrada con éxito.')
                return redirect('comunidadApp:lista_afiliaciones')
            except Exception as e:
                messages.error(request, f'Error al guardar: {str(e)}')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = AfiliacionVecinoForm()
        
    return render(request, 'administrador/afiliaciones/form_afiliacion.html', {
        'form': form,
        'titulo': 'Registrar Nueva Afiliación'
    })

@login_required
@role_required('Administrador', 'Profesional')
def editar_afiliacion(request, id_afiliacion):
    afiliacion = get_object_or_404(AfiliacionVecino, id_afiliacion=id_afiliacion)
    
    if request.method == 'POST':
        datos_antiguos = model_to_dict(afiliacion)
        form = AfiliacionVecinoForm(request.POST, instance=afiliacion)
        if form.is_valid():
            try:
                with transaction.atomic():
                    afiliacion_guardada = form.save()
                    
                    # AUDITORIA
                    registrar_auditoria(request, "EDICION", "AfiliacionVecino", afiliacion_guardada, datos_antiguos)
                    
                messages.success(request, 'La afiliación fue actualizada correctamente.')
                return redirect('comunidadApp:lista_afiliaciones')
            except Exception as e:
                messages.error(request, f'Error al actualizar: {str(e)}')
    else:
        form = AfiliacionVecinoForm(instance=afiliacion)
        
    return render(request, 'administrador/afiliaciones/form_afiliacion.html', {
        'form': form,
        'titulo': 'Editar Afiliación'
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
            
            # AUDITORIA
            registrar_auditoria(request, "CAMBIO_ESTADO", "AfiliacionVecino", afiliacion, datos_antiguos)
                
        accion_str = "habilitada" if nuevo_estado else "inhabilitada"
        messages.success(request, f'La afiliación fue {accion_str} correctamente.')
        
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