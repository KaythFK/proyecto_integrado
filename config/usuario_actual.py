from contextvars import ContextVar

_usuario = ContextVar('usuario_actual', default=None)


def usuario_actual():
    return _usuario.get()


class UsuarioActualMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        marca = _usuario.set(getattr(request, 'user', None))
        try:
            return self.get_response(request)
        finally:
            _usuario.reset(marca)
