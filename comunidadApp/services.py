from comunidadApp.models import OrganizacionComunitaria


def clasificar_desde_nombre(nombre_org: str):
    n = (nombre_org or "").upper().strip()
    Tipo = OrganizacionComunitaria.TipoOrganizacion
    Subtipo = OrganizacionComunitaria.SubtipoOrganizacion

    if "JUNTA DE VECINOS" in n or "JJ.VV" in n or "JJVV" in n:
        return Tipo.TERRITORIAL, Subtipo.JUNTA_VECINOS
    if "UNION COMUNAL" in n or "UNIÓN COMUNAL" in n:
        return Tipo.FUNCIONAL, Subtipo.UNION_COMUNAL
    if "ADULTO MAYOR" in n or "ADULTOS MAYORES" in n or "ABUELITO" in n:
        return Tipo.FUNCIONAL, Subtipo.ADULTO_MAYOR
    if "COMITE DE ALLEGADOS" in n or "COMITÉ DE ALLEGADOS" in n:
        return Tipo.FUNCIONAL, Subtipo.COMITE_ALLEGADOS
    if "COMITE DE SEGURIDAD" in n or "COMITÉ DE SEGURIDAD" in n or "SEGURIDAD CIUDADANA" in n:
        return Tipo.FUNCIONAL, Subtipo.COMITE_SEGURIDAD
    if "COMITE" in n or "COMITÉ" in n:
        return Tipo.FUNCIONAL, Subtipo.COMITE_VIVIENDA
    if "CENTRO DE MADRES" in n:
        return Tipo.FUNCIONAL, Subtipo.CENTRO_MADRES
    if "CULTURAL" in n:
        return Tipo.FUNCIONAL, Subtipo.CULTURAL
    if "JUVENIL" in n or "JOVENES" in n or "JÓVENES" in n:
        return Tipo.FUNCIONAL, Subtipo.JUVENIL
    if "DEPORTIV" in n or "FUTBOL" in n or "FÚTBOL" in n or "CUECA" in n or "CLUB" in n:
        return Tipo.FUNCIONAL, Subtipo.CLUB_DEPORTIVO

    return Tipo.FUNCIONAL, Subtipo.OTRO