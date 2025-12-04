from django.core.management.base import BaseCommand
from core import services
from core.models import Cargo, Lotacao
from django.contrib.auth import get_user_model
import os

class Command(BaseCommand):
    help = 'Importador Universal. Uso: python manage.py import [tipo] [arquivo]'

    def add_arguments(self, parser):
        parser.add_argument('tipo', type=str, help='Tipo: cargo, lotacao, usuario')
        parser.add_argument('arquivo', type=str, help='Caminho do arquivo')

    def handle(self, *args, **options):
        tipo = options['tipo'].lower()
        caminho = options['arquivo']
        
        if not os.path.exists(caminho):
            self.stdout.write(self.style.ERROR('Arquivo não encontrado'))
            return

        model_class = None
        mapa = {}
        campos_unicos = []

        if tipo == 'cargo':
            model_class = Cargo
            mapa = {
                'Nome': 'nome_cargo',
                'Nivel': 'hierarquia'
            }
            campos_unicos = ['nome_cargo']

        elif tipo == 'lotacao':
            model_class = Lotacao
            mapa = {
                'Nome': 'nome_lotacao',
                'Pai': ('lotacao_pai', Lotacao, 'nome_lotacao') 
            }
            campos_unicos = ['nome_lotacao']

        elif tipo == 'usuario':
            model_class = get_user_model()
            mapa = {
                'Email': 'email',
                'Nome': 'first_name',
                'CPF': 'cpf',
                'Matricula': 'matricula',
                'Cargo': ('cargo', Cargo, 'nome_cargo'),
                'Lotacao': ('lotacao', Lotacao, 'nome_lotacao')
            }
            campos_unicos = ['email']

        else:
            self.stdout.write(self.style.ERROR(f'Tipo "{tipo}" não configurado.'))
            return

        self.stdout.write(f'Importando {tipo}...')
        
        with open(caminho, 'rb') as f:
            resultado = services.importar_dados(
                f, 
                os.path.basename(caminho), 
                model_class, 
                mapa, 
                campos_unicos
            )

        if resultado['erros']:
            self.stdout.write(self.style.WARNING('Erros:'))
            for erro in resultado['erros']:
                self.stdout.write(erro)
        
        self.stdout.write(self.style.SUCCESS(f"Sucesso: {resultado['sucesso']} registros processados."))
