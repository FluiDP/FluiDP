from .services import get_config

def tema_global(request):
    return {'tema': get_config()}