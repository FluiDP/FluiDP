import re
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.conf import settings
from django.forms import ValidationError
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from jsonschema import validate
from django.core.validators import MinValueValidator, MaxValueValidator
import datetime

FORM_SCHEMA = {
    "type": "array",
    "minItems": 0,
    "items": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string", 
                "pattern": "^[a-zA-Z0-9_]+$"
            },
            "label": {"type": "string", "minLength": 3},
            "type": {
                "type": "string",
                "enum": ["text", "number", "date", "textarea", "select", "checkbox", "radio", "repeater", "calculated"]
            },
            "required": {"type": "boolean"},
            "placeholder": {"type": "string"},
            "help_text": {"type": "string"},
            
            "is_event_date": {
                "type": "boolean",
                "description": "Se True, usa este campo para validar o limite de dias de antecedência."
            },

            "sub_fields": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "pattern": "^[a-zA-Z0-9_]+$"},
                        "label": {"type": "string"},
                        "type": {
                            "type": "string",
                            "enum": ["text", "number", "date", "select", "checkbox", "radio"]
                        },
                        "required": {"type": "boolean"},
                        "placeholder": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "value": {"type": "string"},
                                    "label": {"type": "string"}
                                },
                                "required": ["value", "label"]
                            }
                        },
                        "extra_props": {
                            "type": "object",
                            "additionalProperties": True 
                        }
                    },
                    "required": ["name", "label", "type"],
                    "additionalProperties": False
                }
            },

            "target_repeater": {
                "type": "string",
                "description": "Nome do campo repeater alvo."
            },
            "target_subfield": {
                "type": "string",
                "description": "Nome do sub-campo numérico/hora a ser calculado."
            },
            "calc_format": {
                "type": "string",
                "enum": ["time", "integer", "decimal"],
                "description": "Formato do resultado: 'time' (HH:MM), 'integer' (10), 'decimal' (10.50)."
            },
            "calc_operator": {
                "type": "string",
                "enum": ["sum"], 
                "default": "sum",
                "description": "Operação base (por enquanto apenas soma, o sinal é controlado abaixo)."
            },
            "condition_field": {
                "type": "string",
                "description": "Nome do campo irmão (no repeater) que define o sinal (+/-). Ex: 'tipo_lancamento'."
            },
            "subtract_value": {
                "type": "string",
                "description": "Valor do campo acima que fará o número ser subtraído. Ex: 'debito'."
            },

            "extra_props": {
                "type": "object",
                "properties": {
                    "count_time_field": {"type": "boolean"},
                    "day_time_field": {"type": "boolean"}
                },
                "additionalProperties": True 
            },
            "options_source": {
                "type": "string",
                "enum": ["manual", "colaboradores_lotacao", "cargos"]
            },
            "options": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "label": {"type": "string"}
                    },
                    "required": ["value", "label"]
                }
            }
        },
        "required": ["name", "label", "type", "required"],
        "additionalProperties": False 
    }
}

class Cargo(models.Model):
    class Meta:
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"

    class HierarquiaChoices(models.IntegerChoices):
        DIRETOR = 1, 'Diretor'
        GERENTE = 2, 'Gerente'
        COORDENADOR = 3, 'Coordenador'
        PADRAO = 4, 'Padrão'

    nome_cargo = models.CharField(verbose_name="Nome do Cargo", max_length=100)
    hierarquia = models.IntegerField(
        verbose_name="Nível Hierárquico",
        choices=HierarquiaChoices.choices,
        default=HierarquiaChoices.PADRAO
    )

    arquivado = models.BooleanField(verbose_name="Arquivar?", default=False)

    def __str__(self):
        return self.nome_cargo

class Lotacao(models.Model):
    class Meta:
        verbose_name = "Lotação"
        verbose_name_plural = "Lotações"

    nome_lotacao = models.CharField(verbose_name="Nome da Lotação", max_length=100)

    chefia = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Chefia da Lotação",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lotacoes_gerenciadas"
    )

    chefia_secundaria = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Chefia Secundária",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lotacoes_dirigidas"
    )

    lotacao_pai = models.ForeignKey(
        'self',
        verbose_name="Lotação Pai",
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    
    arquivado = models.BooleanField(verbose_name="Arquivar?", default=False)

    def get_lotacao_raiz(self, _vistos=None):
        if _vistos is None:
            _vistos = set()
        identificador = self.pk if self.pk is not None else id(self)
        if identificador in _vistos:
            return self
        _vistos.add(identificador)
        
        if self.lotacao_pai:
            return self.lotacao_pai.get_lotacao_raiz(_vistos=_vistos)
        return self

    def find_gestor_disponivel(self, solicitante=None, visited=None):
        if visited is None:
            visited = set()
        
        if self.pk in visited:
            return None 
        visited.add(self.pk)

        if self.chefia and not self.chefia.is_ausente:
            if solicitante is None or self.chefia != solicitante:
                return self.chefia

        if self.chefia_secundaria and not self.chefia_secundaria.is_ausente:
            if solicitante is None or self.chefia_secundaria != solicitante:
                return self.chefia_secundaria

        if self.lotacao_pai:
            return self.lotacao_pai.find_gestor_disponivel(solicitante=solicitante, visited=visited)
            
        return self.get_lotacao_raiz().chefia if self.get_lotacao_raiz().chefia else None

    def lotacao_nome(self, separador=' > ', _vistos=None):
        if _vistos is None:
            _vistos = set()
        identificador = self.pk if self.pk is not None else id(self)
        if identificador in _vistos:
            return self.nome_lotacao
        _vistos.add(identificador)
        if self.lotacao_pai:
            return self.lotacao_pai.lotacao_nome(separador, _vistos) + separador + self.nome_lotacao
        return self.nome_lotacao
    
    def get_descendentes(self, include_self=False, _vistos=None):
        if _vistos is None:
            _vistos = set()
        identificador = self.pk if self.pk is not None else id(self)
        if identificador in _vistos:
            return []
        _vistos.add(identificador)
        
        descendentes = []
        if include_self:
            descendentes.append(self)
            
        filhos = Lotacao.objects.filter(lotacao_pai=self)
        for filho in filhos:
            descendentes.extend(filho.get_descendentes(include_self=True, _vistos=_vistos))
            
        return descendentes

    def __str__(self):
        return self.nome_lotacao

class CustomUser(AbstractUser):
    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"
    
    cpf = models.CharField(verbose_name="CPF", max_length=11, unique=True, null=True, blank=True)
    matricula = models.CharField(verbose_name="Matrícula", max_length=10, unique=True, null=True, blank=True)
    ausencia_inicio = models.DateField(verbose_name="Início do Período de Ausência", null=True, blank=True)
    ausencia_fim = models.DateField(verbose_name="Fim do Período de Ausência", null=True, blank=True)

    precisa_trocar_senha = models.BooleanField(verbose_name="Precisa trocar senha?", default=False, help_text="Se True, obriga o usuário a trocar a senha no próximo login.")

    cargo = models.ForeignKey(
        Cargo,
        verbose_name="Cargo",
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    lotacao = models.ForeignKey(
        Lotacao,
        verbose_name="Lotação",
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    @property
    def is_ausente(self):
        today = timezone.now().date()
        if self.ausencia_inicio and self.ausencia_fim:
            return self.ausencia_inicio <= today <= self.ausencia_fim
        return False

    def get_cpf_formatado(self):
        """
        Retorna o CPF formatado como 000.000.000-00.
        Se não houver CPF, retorna string vazia.
        """
        if not self.cpf or len(self.cpf) != 11:
            return self.cpf or ""
        return f"{self.cpf[:3]}.{self.cpf[3:6]}.{self.cpf[6:9]}-{self.cpf[9:]}"

    @property
    def cpf_mascarado(self):
        """
        Retorna o CPF parcialmente oculto para exibição segura.
        Ex: ***.456.789-**
        """
        if not self.cpf or len(self.cpf) != 11:
            return ""
        return f"***.{self.cpf[3:6]}.{self.cpf[6:9]}-**"

    def clean(self):
        super().clean()
        if self.cpf:
            self.cpf = re.sub(r'[^0-9]', '', str(self.cpf))

            if self.cpf.isdigit():
                self.cpf = self.cpf.zfill(11)

            if len(self.cpf) != 11:
                raise ValidationError({'cpf': 'O CPF deve conter exatamente 11 dígitos numéricos.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.first_name  + ' (' + self.matricula + ')' if self.first_name and self.matricula else self.first_name or self.username

class TipoDocumento(models.Model):
    class Meta:
        verbose_name = "Tipo de Documento"
        verbose_name_plural = "Tipos de Documento"
    
    nome_documento = models.CharField(verbose_name="Nome do Documento", max_length=100)
    requer_aprovacao_gestor = models.BooleanField(verbose_name="Requer aprovação do gestor?", default=True)
    requer_aprovacao_diretor = models.BooleanField(verbose_name="Requer aprovação do diretor?", default=True)

    dia_inicio = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Dia do mês de início do período de solicitação",
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Dia do mês que inicia o período (1-31). Ex: 1"
    )

    dia_fim = models.PositiveSmallIntegerField(
        default=31,
        verbose_name="Dia do mês de fim do período de solicitação",
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Dia do mês que encerra o período (1-31). Configure 31 para ir até o fim de qualquer mês."
    )
    
    limite_dias_antecedencia = models.IntegerField(
        default=0,
        verbose_name="Dias de antecedência necessários",
        null=True, blank=True,
        help_text="Mínimo de dias entre hoje e a data do evento (ex: troca de plantão)."
    )
    
    definicao_formulario = models.JSONField(default=list, blank=True)

    disponivel = models.BooleanField(
        default=True,
        verbose_name="Documento disponível para o colaborador?",
        help_text="Se ativo, este tipo de documento pode ser selecionado para novas solicitações."
    )
    
    arquivado = models.BooleanField(verbose_name="Arquivar?", default=False)

    def ativo(self):
        return self.disponivel and self.esta_no_periodo() and not self.arquivado

    def clean(self):
        super().clean()
        
        try:
            validate(instance=self.definicao_formulario, schema=FORM_SCHEMA)
        except JSONSchemaValidationError as e:
            raise ValidationError(f"Erro na estrutura do JSON: {e.message}")

        nomes_usados = set()
        for campo in self.definicao_formulario:
            nome = campo.get('name')
            tipo = campo.get('type')
            
            if nome in nomes_usados:
                raise ValidationError(f"O nome de campo '{nome}' está duplicado. Use nomes únicos.")
            nomes_usados.add(nome)

            if tipo in ['select', 'radio']:
                opcoes = campo.get('options', [])
                fonte = campo.get('options_source')
                
                if not fonte and len(opcoes) == 0:
                      raise ValidationError(f"O campo '{campo.get('label')}' é do tipo seleção mas não possui opções nem fonte de dados.")
        
        if (self.dia_inicio and not self.dia_fim) or (self.dia_fim and not self.dia_inicio):
            raise ValidationError("Para restringir datas, preencha tanto o dia de início quanto o dia de fim. Se não quiser restringir indique dia 1 como dia de início e dia 31 como dia de fim.")
            
        if self.dia_inicio and self.dia_fim:
            if self.dia_inicio > self.dia_fim:
                raise ValidationError("O dia de início deve ser menor ou igual ao dia de fim.")

    @property
    def periodo_abertura_texto(self):
        if self.dia_inicio and self.dia_fim:
            return f"Dia {self.dia_inicio} ao dia {self.dia_fim} de todo mês"
        return "Disponível o mês todo"

    def esta_no_periodo(self):
        """
        Verifica se o dia de hoje está dentro do intervalo configurado.
        """
        if not (self.dia_inicio and self.dia_fim):
            return True 

        hoje_dia = timezone.now().day
        return self.dia_inicio <= hoje_dia <= self.dia_fim

    def validar_regras(self, dados_valores):
        """
        Valida as regras de negócio para uma nova solicitação:
        1. Janela de Abertura (Dia do Mês).
        2. Antecedência Mínima (baseada no campo marcado com is_event_date).
        """
        
        if self.arquivado:
             raise ValidationError(
                f"O tipo de documento '{self.nome_documento}' foi descontinuado e não aceita novas solicitações."
            )

        if not self.esta_no_periodo():
            raise ValidationError(
                f"Este tipo de documento só aceita solicitações entre os dias {self.dia_inicio} e {self.dia_fim} de cada mês."
            )

        if self.limite_dias_antecedencia is not None and self.limite_dias_antecedencia > 0:
            campo_evento = next((campo for campo in self.definicao_formulario if campo.get('is_event_date')), None)
            
            if campo_evento:
                nome_campo = campo_evento.get('name')
                valor_str = dados_valores.get(nome_campo)
                
                if valor_str:
                    try:
                        data_evento = datetime.datetime.strptime(valor_str, "%Y-%m-%d").date()
                        hoje = timezone.now().date()
                        
                        data_minima = hoje + datetime.timedelta(days=self.limite_dias_antecedencia)
                        
                        if data_evento < data_minima:
                            raise ValidationError(
                                f"A data escolhida ({data_evento.strftime('%d/%m/%Y')}) não respeita a antecedência mínima de {self.limite_dias_antecedencia} dias. "
                                f"Selecione uma data a partir de {data_minima.strftime('%d/%m/%Y')}."
                            )
                    except ValueError:
                        pass 

    def is_empty_form(self):
        return len(self.definicao_formulario) == 0

    def __str__(self):
        return self.nome_documento

class Solicitacao(models.Model):
    class Meta:
        verbose_name = "Solicitação"
        verbose_name_plural = "Solicitações"

    class StatusChoices(models.TextChoices):
        PENDENTE_ACEITE_SECUNDARIO = 'PENDENTE_ACEITE', 'Aguardando Aceite do Colega'
        PENDENTE_GESTOR = 'PENDENTE_GESTOR', 'Pendente (Gestor)'
        PENDENTE_DIRETOR = 'PENDENTE_DIRETOR', 'Pendente (Diretor)'
        PENDENTE_DP = 'PENDENTE_DP', 'Pendente (DP)'
        LANCAMENTO = 'LANCAMENTO', 'Aguardando Lançamento' # nesse estágio, as solicitações devem ser processadas pelo DP, mas consideramos aprovadas as solicitações que passaram por todas as etapas de aprovação.
        FINALIZADO = 'FINALIZADO', 'Finalizado'
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
        verbose_name="Status da Solicitação",
        max_length=50,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDENTE_GESTOR
    )

    colaborador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Colaborador Solicitante",
        on_delete=models.PROTECT,
        related_name='solicitacoes_criadas'
    )
    
    colaborador_secundario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Colaborador Secundário",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='solicitacoes_secundarias'
    )
    
    tipo_documento = models.ForeignKey(
        TipoDocumento,
        verbose_name="Tipo de Documento",
        on_delete=models.PROTECT
    )
    
    aprovador_atual = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Aprovador Atual",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='aprovacoes_pendentes'
    )

    dados_preenchidos = models.JSONField(verbose_name="Dados Preenchidos", default=dict, blank=True)

    data = models.DateTimeField(auto_now_add=True)

    arquivado = models.BooleanField(verbose_name="Arquivar?", default=False)

    def clean(self):
        """
        Valida as regras de negócio antes de salvar.
        Chamado automaticamente pelo ModelForm ou manualmente via full_clean().
        """

        super().clean()

        if self.pk:
            return

        if self.tipo_documento_id:
            valores = self.dados_preenchidos.get('values', {})
            
            if not valores and isinstance(self.dados_preenchidos, dict):
                valores = self.dados_preenchidos

            self.tipo_documento.validar_regras(valores)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Solicitação {self.id} - {self.tipo_documento.nome_documento} - {self.status}"

class LogAprovacao(models.Model):
    class Meta:
        verbose_name = "Log de Aprovação"
        verbose_name_plural = "Logs de Aprovação"

    class AcaoChoices(models.TextChoices):
        CRIACAO = 'CRIACAO', 'Criação da Solicitação'
        CANCELAMENTO = 'CANCELAMENTO', 'Cancelado pelo Solicitante'
        ACEITE_SECUNDARIO = 'ACEITE_SECUNDARIO', 'Aceite pelo Colega'
        RECUSA_SECUNDARIO = 'RECUSA_SECUNDARIO', 'Recusado pelo Colega'
        APROVADO_GESTOR = 'APROVADO_GESTOR', 'Aprovado pelo Gestor'
        RECUSADO_GESTOR = 'RECUSADO_GESTOR', 'Recusado pelo Gestor'
        APROVADO_DIRETOR = 'APROVADO_DIRETOR', 'Aprovado pelo Diretor'
        RECUSADO_DIRETOR = 'RECUSADO_DIRETOR', 'Recusado pelo Diretor'
        APROVADO_DP = 'APROVADO_DP', 'Aprovado pelo DP'
        RECUSADO_DP = 'RECUSADO_DP', 'Recusado pelo DP'
        LANCADO = 'LANCADO', 'Lançado pelo DP'
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
