import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from core.models import Lotacao, Cargo
from core.services import importar_dados 

class Command(BaseCommand):
    help = 'Importa dados de arquivos CSV ou Excel. Uso: python manage.py importer [tipo] [caminho_arquivo]'

    def add_arguments(self, parser):
        parser.add_argument('tipo', type=str, help='Tipo de dado a importar: usuario, lotacao, cargo')
        parser.add_argument('arquivo', type=str, help='Caminho do arquivo (.csv ou .xlsx)')

    def handle(self, *args, **options):
        tipo = options['tipo'].lower()
        caminho_arquivo = options['arquivo']

        if not os.path.exists(caminho_arquivo):
            raise CommandError(f'Arquivo não encontrado: "{caminho_arquivo}"')

        self.stdout.write(self.style.WARNING(f'Iniciando importação de {tipo}...'))

        mapa = {}
        campo_chave = [] 
        model = None

        if tipo == 'usuario':
            model = get_user_model()
            mapa = {
                'Nome': 'first_name',
                'Sobrenome': 'last_name',
                'Email': 'email',
                'Matricula': 'matricula',
                'CPF': 'cpf',
                'Cargo': ('cargo', Cargo, 'nome_cargo'), 
                'Lotação': ('lotacao', Lotacao, 'nome_lotacao'),
                'Lotação Secundaria': ('lotacao_secundaria', Lotacao, 'nome_lotacao')
            }
            campo_chave = ['cpf']

        elif tipo == 'lotacao':
            model = Lotacao
            mapa = {
                'Nome': 'nome_lotacao',
                'Pai': ('lotacao_pai', Lotacao, 'nome_lotacao') 
            }
            campo_chave = ['nome_lotacao']

        elif tipo == 'cargo':
            model = Cargo
            mapa = {
                'Nome': 'nome_cargo',
                'Nivel': 'hierarquia' 
            }
            campo_chave = ['nome_cargo']

        else:
            raise CommandError(f'Tipo "{tipo}" não reconhecido. Use: usuario, lotacao, cargo.')

        with open(caminho_arquivo, 'rb') as arquivo_handle:
            resultado = importar_dados(
                arquivo_io=arquivo_handle,
                nome_arquivo=caminho_arquivo,
                model_class=model,
                mapa_de_campos=mapa,
                campo_busca_fk=campo_chave
            )

        if resultado['erros']:
            self.stdout.write(self.style.ERROR('Erros encontrados:'))
            for erro in resultado['erros']:
                self.stdout.write(f" - {erro}")
        
        self.stdout.write(self.style.SUCCESS(
            f"Concluído! {resultado['sucesso']} registros processados com sucesso."
        ))