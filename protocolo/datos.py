from django.db import models as M


def crear(Modelo, **extra):
    """Crea un registro completando con valores mínimos los campos obligatorios que no se indiquen."""
    datos = {}
    for campo in Modelo._meta.concrete_fields:
        if campo.primary_key or campo.has_default() or campo.name in extra or campo.null:
            continue
        if isinstance(campo, M.ForeignKey):
            datos[campo.name] = crear(campo.related_model)
        elif getattr(campo, 'choices', None):
            datos[campo.name] = campo.choices[0][0]
        elif isinstance(campo, (M.CharField, M.TextField)):
            datos[campo.name] = 'x%d' % Modelo.objects.count()
        elif isinstance(campo, (M.IntegerField, M.DecimalField)):
            datos[campo.name] = 1
        elif isinstance(campo, M.DateField):
            datos[campo.name] = '2026-01-01'
    datos.update(extra)
    return Modelo.objects.create(**datos)
