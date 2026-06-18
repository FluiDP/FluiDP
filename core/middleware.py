import re
from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import redirect

class HtmxRedirectMiddleware:
    """
    Se o Django tentar redirecionar para o Login durante uma requisição HTMX,
    nós interceptamos e enviamos um comando (HX-Redirect) para o navegador
    fazer o redirecionamento total.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if response.status_code == 302:
            is_htmx = request.headers.get('HX-Request') == 'true'
            
            if is_htmx:
                login_url = str(settings.LOGIN_URL)
                target_url = response.url

                if login_url in target_url:
                    response.content = b""
                    response.status_code = 200
                    response['HX-Redirect'] = target_url
        
        return response

class MobileRedirectMiddleware:
    """
    Verifica se o utilizador está a aceder por um dispositivo móvel E 
    se já tem a sessão iniciada. Caso positivo, redireciona para as rotas /m/
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'STATIC_URL', '/static/') and request.path.startswith(settings.STATIC_URL):
            return self.get_response(request)
        if getattr(settings, 'MEDIA_URL', '/media/') and request.path.startswith(settings.MEDIA_URL):
            return self.get_response(request)

        if request.path.startswith('/admin/'):
            return self.get_response(request)

        rotas_ignoradas = ['/login', '/logout', '/reset']
        if any(request.path.startswith(rota) for rota in rotas_ignoradas):
            return self.get_response(request)

        if request.path.startswith('/m/'):
            return self.get_response(request)

        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        mobile_keywords = r'mobile|android|iphone|ipad|ipod|windows phone'
        
        is_mobile_device = bool(re.search(mobile_keywords, user_agent))

        if is_mobile_device and request.user.is_authenticated:
            
            if request.headers.get('HX-Request') == 'true':
                return self.get_response(request)
            
            return redirect('/m/')

        return self.get_response(request)
    