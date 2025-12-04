from django.urls import path
from . import views_dp as views

app_name = 'dp'

urlpatterns = [
    path('', views.dp_painel_view, name='home'),

    path('lotacoes', views.dp_lotacoes_view, name='lotacoes'),
    path('colaboradores', views.dp_colaboradores_view, name='colaboradores'),
    path('documentos', views.dp_documentos_view, name='documentos'),
    path('cargos', views.dp_cargos_view, name='cargos'),
    path('solicitacoes', views.dp_solicitacoes_view, name='solicitacoes'),

    path('lotacoes/criar/', views.create_lotacao_model_view, name='create_lotacao'),
    path('cargos/criar/', views.create_cargo_model_view, name='create_cargo'),
]
