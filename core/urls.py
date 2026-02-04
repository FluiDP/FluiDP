from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.index_view, name='index'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('reset_password/', views.CustomPasswordResetView.as_view(), name='reset_password'),
    path('reset_password/done/', views.CustomPasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset_password_confirm/<uidb64>/<token>/', views.CustomPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset_password/complete/', views.CustomPasswordResetCompleteView.as_view(), name='password_reset_complete'),

    path('painel/', views.painel_view, name='painel'),
    path('perfil/', views.perfil_view, name='perfil'),
    path('servico-indisponivel/', views.indisponibilidade_view, name='indisponibilidade'),

    path('administracao/', include('core.urls_dp')),
    path('colaborador/', include('core.urls_colaborador')),
    path('gestor/', include('core.urls_gestor')),

    path('solicitacao/pdf/<int:solicitacao_id>/', views.gerar_pdf_solicitacao_view, name='gerar_pdf_solicitacao'),

    path('relatorio-geral/', views.relatorio_geral_view, name='relatorio_geral'),
]
