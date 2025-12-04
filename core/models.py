from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.conf import settings
from django.forms import ValidationError
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from jsonschema import validate

FORM_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "label": {"type": "string"},
            "type": {
                "type": "string",
                "enum": ["text", "number", "date", "textarea", "select", "checkbox", "radio"]
            },
            "required": {"type": "boolean"},
            "placeholder": {"type": "string"},
            "help_text": {"type": "string"},
            "options": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}, "label": {"type": "string"}},
                    "required": ["value", "label"]
                }
            }
        },
        "required": ["name", "label", "type", "required"]
    }
}

class Cargo(models.Model):
    class HierarquiaChoices(models.IntegerChoices):
        DIRETOR = 1, 'Diretor'
        GERENTE = 2, 'Gerente'
        COORDENADOR = 3, 'Coordenador'
        PADRAO = 4, 'Padrão'

    nome_cargo = models.CharField(max_length=100)
    hierarquia = models.IntegerField(
        choices=HierarquiaChoices.choices,
        default=HierarquiaChoices.PADRAO
    )

    def __str__(self):
        return self.nome_cargo

class Lotacao(models.Model):
    nome_lotacao = models.CharField(max_length=100)

    chefia = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lotacoes_gerenciadas"
    )

    chefia_secundaria = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lotacoes_dirigidas"
    )

    lotacao_pai = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    def find_gestor_disponivel(self, solicitante=None, visited=None):
        """Sobe recursivamente na hierarquia procurando uma chefia (Gestor) que não esteja ausente."""
        if visited is None:
            visited = set()
        
        if self.pk in visited:
            return None 
        visited.add(self.pk)

        if self.chefia and not self.chefia.is_ausente and self.chefia != solicitante:
            return self.chefia

        if self.chefia_secundaria and not self.chefia_secundaria.is_ausente and self.chefia != solicitante:
            return self.chefia_secundaria

        if self.lotacao_pai:
            return self.lotacao_pai.find_gestor_disponivel(visited=visited)
            
        return None

    def lotacao_fullname(self, separador=' > ', _vistos=None):
        if _vistos is None:
            _vistos = set()
            
        identificador = self.pk if self.pk is not None else id(self)
        
        if identificador in _vistos: 
            return self.nome_lotacao
            
        _vistos.add(identificador)
        
        if self.lotacao_pai:
            return self.lotacao_pai.lotacao_fullname(separador, _vistos) + separador + self.nome_lotacao
            
        return self.nome_lotacao

    def __str__(self):
        return self.nome_lotacao

class CustomUser(AbstractUser):
    cpf = models.CharField(max_length=11, unique=True, null=True, blank=True)
    matricula = models.CharField(max_length=10, unique=True, null=True, blank=True)
    ausencia_inicio = models.DateField(null=True, blank=True)
    ausencia_fim = models.DateField(null=True, blank=True)

    cargo = models.ForeignKey(
        Cargo,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    lotacao = models.ForeignKey(
        Lotacao,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    @property
    def is_ausente(self):
        """Verifica se o usuário está ausente (férias, etc.)"""
        today = timezone.now().date()
        if self.ausencia_inicio and self.ausencia_fim:
            return self.ausencia_inicio <= today <= self.ausencia_fim
        return False

    def __str__(self):
        return self.first_name + ' ' + self.last_name if self.first_name and self.last_name else self.username

class TipoDocumento(models.Model):
    nome_documento = models.CharField(max_length=100)
    requer_aprovacao_gestor = models.BooleanField(default=False)
    requer_aprovacao_diretor = models.BooleanField(default=False)
    data_inicio = models.DateField(null=True, blank=True)
    data_fim = models.DateField(null=True, blank=True)
    limite_dias_antecedencia = models.IntegerField(null=True, blank=True)
    definicao_formulario = models.JSONField(default=dict, blank=True)

    def clean(self):
        super().clean()
        try:
            validate(instance=self.definicao_formulario, schema=FORM_SCHEMA)
        except JSONSchemaValidationError as e:
            raise ValidationError(f"Erro na estrutura do JSON 'definicao_formulario': {e.message}")

    def __str__(self):
        return self.nome_documento

class Solicitacao(models.Model):
    
    class StatusChoices(models.TextChoices):
        PENDENTE_ACEITE_SECUNDARIO = 'PENDENTE_ACEITE', 'Aguardando Aceite do Colega'
        PENDENTE_GESTOR = 'PENDENTE_GESTOR', 'Pendente (Gestor)'
        PENDENTE_DIRETOR = 'PENDENTE_DIRETOR', 'Pendente (Diretor)'
        PENDENTE_DP = 'PENDENTE_DP', 'Pendente (DP)'
        APROVADO = 'APROVADO', 'Aprovado'
        RECUSADO = 'RECUSADO', 'Recusado'
        CANCELADO = 'CANCELADO', 'Cancelado'

    @property
    def is_pendente(self):
        return self.status in [
            self.StatusChoices.PENDENTE_GESTOR,
            self.StatusChoices.PENDENTE_DIRETOR,
            self.StatusChoices.PENDENTE_DP,
            self.StatusChoices.PENDENTE_ACEITE_SECUNDARIO,
        ]
    
    @property
    def is_finalizada(self):
        return self.status in [
            self.StatusChoices.APROVADO,
            self.StatusChoices.RECUSADO,
            self.StatusChoices.CANCELADO,
        ]
    
    @property
    def is_aprovada(self):
        return self.status == self.StatusChoices.APROVADO
    
    status = models.CharField(
        max_length=50,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDENTE_GESTOR
    )

    colaborador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='solicitacoes_criadas'
    )
    
    colaborador_secundario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='solicitacoes_secundarias'
    )
    
    tipo_documento = models.ForeignKey(
        TipoDocumento,
        on_delete=models.PROTECT
    )
    
    aprovador_atual = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='aprovacoes_pendentes'
    )

    dados_preenchidos = models.JSONField(default=dict, blank=True)
    data = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Solicitação {self.id} - {self.tipo_documento.nome_documento} - {self.status}"

class LogAprovacao(models.Model):
    class AcaoChoices(models.TextChoices):
        CRIACAO = 'CRIACAO', 'Criação da Solicitação'
        CANCELAMENTO = 'CANCELAMENTO', 'Cancelado pelo Solicitante'
        ACEITE_SECUNDARIO = 'ACEITE_SECUNDARIO', 'Aceite pelo Colega'
        RECUSA_SECUNDARIO = 'RECUSA_SECUNDARIO', 'Recusado pelo Colega'
        APROVADO_GESTOR = 'APROVADO_GESTOR', 'Aprovado pelo Gestor'
        RECUSADO_GESTOR = 'RECUSADO_GESTOR', 'Recusado pelo Gestor'
        APROVADO_DIRETOR = 'APROVADO_DIRETOR', 'Aprovado pelo Diretor'
        RECUSADO_DIRETOR = 'RECUSADO_DIRETOR', 'Recusado pelo Diretor'
        PROCESSADO_DP = 'PROCESSADO_DP', 'Processado pelo DP'
        RECUSADO_DP = 'RECUSADO_DP', 'Reusado pelo DP'
        COMENTARIO = 'COMENTARIO', 'Comentário Adicionado'

    solicitacao = models.ForeignKey(
        Solicitacao,
        on_delete=models.CASCADE,
        related_name='logs'
    )
    
    ator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )
    
    acao = models.CharField(max_length=50, choices=AcaoChoices.choices)
    data_acao = models.DateTimeField(auto_now_add=True)
    detalhes = models.TextField(blank=True)

    def __str__(self):
        return f"Log {self.acao} por {self.ator} em {self.data_acao}"
