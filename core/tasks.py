import os
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.core.mail import get_connection
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings

from .services import importar_dados, new_collaborator_email
from .models import Cargo, Lotacao

def processar_importacao_task(task_id, file_path, tipo_dado):
    """
    Tarefa em background que processa o arquivo, salva no banco e envia os e-mails em lote.
    """
    try:
        cache.set(task_id, {'status': 'processing', 'message': 'Lendo arquivo...'})
        
        mapa = {}
        campo_chave = []
        model = None

        if tipo_dado == 'colaboradores':
            model = get_user_model()
            mapa = {
                'Nome': 'first_name',
                'Email': 'email',
                'Matricula': 'matricula',
                'CPF': 'cpf',
                'Cargo': ('cargo', Cargo, 'nome_cargo'), 
                'Lotacao': ('lotacao', Lotacao, 'nome_lotacao'),
            }
            campo_chave = ['cpf'] 
        elif tipo_dado == 'lotacoes':
            model = Lotacao
            mapa = {'Nome': 'nome_lotacao', 'Pai': ('lotacao_pai', Lotacao, 'nome_lotacao')}
            campo_chave = ['nome_lotacao']
        elif tipo_dado == 'cargos':
            model = Cargo
            mapa = {'Nome': 'nome_cargo', 'Nivel': 'hierarquia'}
            campo_chave = ['nome_cargo']

        with default_storage.open(file_path, 'rb') as arquivo_io:
            cache.set(task_id, {'status': 'processing', 'message': 'Processando dados e salvando no banco...'})
            
            resultado = importar_dados(
                arquivo_io=arquivo_io,
                nome_arquivo=file_path,
                model_class=model,
                mapa_de_campos=mapa,
                campo_busca_fk=campo_chave
            )

        default_storage.delete(file_path)

        if resultado.get('sucesso', 0) > 0:
            msg = f"Sucesso! {resultado['sucesso']} registros processados."
            if resultado.get('erros'):
                msg += f" (Com {len(resultado['erros'])} alertas)"
            cache.set(task_id, {'status': 'success', 'message': msg})
        else:
            erro_txt = resultado['erros'][0] if resultado.get('erros') else "Erro desconhecido"
            cache.set(task_id, {'status': 'error', 'message': f"Falha: {erro_txt}"})

    except Exception as e:
        cache.set(task_id, {'status': 'error', 'message': f"Erro crítico na importação: {str(e)}"})

def enviar_email_simples_task(assunto, mensagem, destinatarios):
    send_mail(
        subject=assunto,
        message=mensagem,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=destinatarios,
        fail_silently=False,
    )
