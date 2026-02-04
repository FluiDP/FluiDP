from django.conf import settings
from django.http import HttpResponseRedirect

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
