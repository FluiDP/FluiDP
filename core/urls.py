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
    path('configuracao/', views.config_view, name='config'),
    path('configuracao/salvar/', views.save_config_view, name='save_config'),
    path('servico-indisponivel/', views.indisponibilidade_view, name='indisponibilidade'),
    path('notificacoes/visualizar/', views.visualizar_notificacoes_view, name='visualizar_notificacoes'),
    path('notificacoes/<int:notificacao_id>/marcar-lida/', views.marcar_notificacao_lida_view, name='marcar_notificacao_lida'),
    path('notificacoes/<int:notificacao_id>/abrir/', views.abrir_notificacao_view, name='abrir_notificacao'),
    path('notificacoes/marcar-todas-lidas/', views.marcar_todas_notificacoes_lidas_view, name='marcar_todas_notificacoes_lidas'),
    path('notificacoes/<int:notificacao_id>/excluir/', views.excluir_notificacao_view, name='excluir_notificacao'),

    path('administracao/', include('core.urls_dp')),
    path('colaborador/', include('core.urls_colaborador')),
    path('gestor/', include('core.urls_gestor')),
    path('m/', include('core.urls_mobile')),

    path('solicitacao/editar/<int:solicitacao_id>/', views.edit_solicitacao_modal_view, name='edit_solicitacao_modal'),
    path('solicitacao/cancelar/<int:solicitacao_id>/', views.cancelar_solicitacao_view, name='cancelar_solicitacao'),
    path('solicitacao/reverter-status/<int:solicitacao_id>/', views.solicitacao_reverter_status_view, name='reverter_status'),
    path('solicitacao/comentar/<int:solicitacao_id>/', views.comentar_solicitacao_modal_view, name='comentar_solicitacao_modal'),

    path('solicitacao/pdf/<int:solicitacao_id>/', views.gerar_pdf_solicitacao_view, name='gerar_pdf_solicitacao'),

    path('relatorio-geral/', views.relatorio_geral_view, name='relatorio_geral'),

    path('solicitacoes/lote/', views.processar_lote_solicitacoes_view, name='processar_lote_solicitacoes'),
]
