import re
import calendar
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.conf import settings
from django.forms import ValidationError
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from jsonschema import validate
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import date, timedelta, datetime

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
            "reference_month_date": {
                "type": "boolean",
                "description": "Se True, exige que a data pertença ao mês de referência da solicitação."
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
                "enum": ["manual", "colaboradores_lotacao", "cargos", "colaboradores_mesmo_cargo"]
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
            if solicitante is None or (self.chefia_secundaria != solicitante and self.chefia != solicitante):
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
    def is_ausente(self, date=None):
        today = date if date is not None else timezone.now().date()
        if self.ausencia_inicio and self.ausencia_fim:
            return self.ausencia_inicio <= today <= self.ausencia_fim
        return False
    
    @property
    def is_adm(self):
        return self.is_superuser or self.groups.filter(name='DP').exists() or self.groups.filter(name='SYSTEM_ADMIN').exists() or (self.cargo and self.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR)

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
    class TipoReferenciaChoices(models.TextChoices):
        NENHUMA = 'NENHUMA', 'Sem referência mensal'
        MENSAL = 'MENSAL', 'Referência mensal'

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

    tipo_referencia = models.CharField(
        max_length=20,
        choices=TipoReferenciaChoices.choices,
        default=TipoReferenciaChoices.NENHUMA,
        verbose_name="Tipo de referência",
        help_text="Use referência mensal para documentos cuja janela começa no mês anterior."
    )

    dia_abertura_mes_anterior = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        verbose_name="Dia de abertura no mês anterior",
        help_text="Ex.: 25 abre solicitações para o mês seguinte."
    )

    dia_limite_mes_referencia = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        verbose_name="Dia limite no mês de referência",
        help_text="Último dia para solicitar no próprio mês de referência."
    )

    restringir_datas_ao_mes_referencia = models.BooleanField(
        default=False,
        verbose_name="Restringir datas ao mês de referência",
        help_text="Exige que os campos marcados no schema pertençam ao mês de referência."
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

        if self.tipo_referencia == self.TipoReferenciaChoices.MENSAL:
            if not self.dia_abertura_mes_anterior or not self.dia_limite_mes_referencia:
                raise ValidationError(
                    "Para referência mensal, informe o dia de abertura no mês anterior e o dia limite no mês de referência."
                )
            if self.dia_abertura_mes_anterior <= self.dia_limite_mes_referencia:
                raise ValidationError(
                    "O dia de abertura no mês anterior deve ser maior que o dia limite do mês de referência."
                )
            if self.restringir_datas_ao_mes_referencia and not any(
                campo.get('reference_month_date') for campo in self.definicao_formulario
            ):
                raise ValidationError(
                    "Marque ao menos um campo do formulário com 'reference_month_date' para restringir datas ao mês de referência."
                )

    @property
    def periodo_abertura_texto(self):
        if self.tipo_referencia == self.TipoReferenciaChoices.MENSAL:
            return (
                f"Dia {self.dia_abertura_mes_anterior} do mês anterior ao dia "
                f"{self.dia_limite_mes_referencia} do mês de referência"
            )
        if self.dia_inicio and self.dia_fim:
            return f"Dia {self.dia_inicio} ao dia {self.dia_fim} de todo mês"
        return "Disponível o mês todo"

    def esta_no_periodo(self, date=None):
        """
        Verifica se o dia de hoje está dentro do intervalo configurado.
        """
        data_consulta = date or timezone.localdate()
        if isinstance(data_consulta, datetime):
            data_consulta = data_consulta.date()

        if self.tipo_referencia == self.TipoReferenciaChoices.MENSAL:
            return self.obter_mes_referencia(data_consulta) is not None

        if not (self.dia_inicio and self.dia_fim):
            return True

        dia = data_consulta.day

        if self.dia_inicio <= self.dia_fim:
            return self.dia_inicio <= dia <= self.dia_fim
        elif self.dia_inicio > self.dia_fim:
            return (self.dia_inicio <= dia <= 31) or (1 <= dia <= self.dia_fim)

    @staticmethod
    def _primeiro_dia_mes_seguinte(data_base):
        if data_base.month == 12:
            return date(data_base.year + 1, 1, 1)
        return date(data_base.year, data_base.month + 1, 1)

    def obter_mes_referencia(self, data_solicitacao=None):
        """Retorna o primeiro dia do mês de referência ou None fora da janela."""
        if self.tipo_referencia != self.TipoReferenciaChoices.MENSAL:
            return None

        data_solicitacao = data_solicitacao or timezone.localdate()
        if isinstance(data_solicitacao, datetime):
            data_solicitacao = data_solicitacao.date()

        ultimo_dia = calendar.monthrange(data_solicitacao.year, data_solicitacao.month)[1]
        dia_abertura = min(self.dia_abertura_mes_anterior, ultimo_dia)
        dia_limite = min(self.dia_limite_mes_referencia, ultimo_dia)

        if data_solicitacao.day >= dia_abertura:
            return self._primeiro_dia_mes_seguinte(data_solicitacao)
        if data_solicitacao.day <= dia_limite:
            return data_solicitacao.replace(day=1)
        return None

    def validar_regras(self, dados_valores, data_solicitacao=None):
        """
        Valida as regras de negócio para uma nova solicitação:
        1. Janela de Abertura (Dia do Mês).
        2. Antecedência Mínima (baseada no campo marcado com is_event_date).
        """
        
        if self.arquivado:
             raise ValidationError(
                f"O tipo de documento '{self.nome_documento}' foi descontinuado e não aceita novas solicitações."
            )

        data_solicitacao = data_solicitacao or timezone.localdate()
        if isinstance(data_solicitacao, datetime):
            data_solicitacao = data_solicitacao.date()

        if not self.esta_no_periodo(data_solicitacao):
            raise ValidationError(
                f"Este tipo de documento só aceita solicitações no período: {self.periodo_abertura_texto}."
            )

        mes_referencia = self.obter_mes_referencia(data_solicitacao)
        for campo in self.definicao_formulario:
            valida_antecedencia = campo.get('is_event_date')
            valida_referencia = (
                self.restringir_datas_ao_mes_referencia and campo.get('reference_month_date')
            )
            if not (valida_antecedencia or valida_referencia):
                continue

            valor_str = dados_valores.get(campo.get('name'))
            if not valor_str:
                continue
            try:
                data_evento = datetime.strptime(valor_str, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                raise ValidationError(f"A data informada em '{campo.get('label')}' é inválida.")

            if valida_antecedencia and self.limite_dias_antecedencia and self.limite_dias_antecedencia > 0:
                data_minima = data_solicitacao + timedelta(days=self.limite_dias_antecedencia)
                if data_evento < data_minima:
                    raise ValidationError(
                        f"A data de '{campo.get('label')}' ({data_evento.strftime('%d/%m/%Y')}) não respeita "
                        f"a antecedência mínima de {self.limite_dias_antecedencia} dias. "
                        f"Selecione uma data a partir de {data_minima.strftime('%d/%m/%Y')}."
                    )

            if valida_referencia and mes_referencia and (
                data_evento.year != mes_referencia.year or data_evento.month != mes_referencia.month
            ):
                raise ValidationError(
                    f"A data de '{campo.get('label')}' deve pertencer ao mês de referência "
                    f"{mes_referencia.strftime('%m/%Y')}."
                )

        return mes_referencia

    def motivo_prazo_expirado(self, dados_valores, data_abertura, mes_referencia=None, data_consulta=None):
        """Retorna o motivo de expiração de uma solicitação ativa, ou ``None``."""
        hoje = data_consulta or timezone.localdate()
        if isinstance(hoje, datetime):
            hoje = hoje.date()
        if isinstance(data_abertura, datetime):
            data_abertura = timezone.localtime(data_abertura).date()

        if self.tipo_referencia == self.TipoReferenciaChoices.MENSAL:
            referencia_atual = self.obter_mes_referencia(hoje)
            if not mes_referencia or referencia_atual != mes_referencia:
                return f'o prazo de solicitação para a referência {mes_referencia:%m/%Y} foi encerrado' if mes_referencia else 'o prazo configurado para a solicitação foi encerrado'
        elif self.dia_inicio and self.dia_fim:
            if self.dia_inicio <= self.dia_fim:
                ultimo_dia = calendar.monthrange(data_abertura.year, data_abertura.month)[1]
                encerramento = data_abertura.replace(day=min(self.dia_fim, ultimo_dia))
            elif data_abertura.day >= self.dia_inicio:
                proximo_mes = self._primeiro_dia_mes_seguinte(data_abertura)
                ultimo_dia = calendar.monthrange(proximo_mes.year, proximo_mes.month)[1]
                encerramento = proximo_mes.replace(day=min(self.dia_fim, ultimo_dia))
            else:
                ultimo_dia = calendar.monthrange(data_abertura.year, data_abertura.month)[1]
                encerramento = data_abertura.replace(day=min(self.dia_fim, ultimo_dia))
            if hoje > encerramento:
                return f'o prazo configurado para este documento encerrou em {encerramento:%d/%m/%Y}'

        antecedencia = self.limite_dias_antecedencia or 0
        if antecedencia > 0:
            data_minima = hoje + timedelta(days=antecedencia)
            for campo in self.definicao_formulario:
                if not campo.get('is_event_date'):
                    continue
                valor = dados_valores.get(campo.get('name'))
                if not valor:
                    continue
                try:
                    data_evento = datetime.strptime(valor, '%Y-%m-%d').date()
                except (TypeError, ValueError):
                    continue
                if data_evento < data_minima:
                    return (
                        f"a data de '{campo.get('label')}' deixou de respeitar a antecedência "
                        f'mínima de {antecedencia} dias'
                    )
        return None

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
        PENDENTE_DIRETOR = 'PENDENTE_DIRETOR', 'Pendente (Diretor)' # em nova regra de negócio, não será visível a pendência da direção
        PENDENTE_DP = 'PENDENTE_DP', 'Pendente (DP)'
        LANCAMENTO = 'LANCAMENTO', 'Recebido pelo DP' # nesse estágio, as solicitações devem ser processadas pelo DP, mas consideramos aprovadas as solicitações que passaram por todas as etapas de aprovação.
        FINALIZADO = 'FINALIZADO', 'Aprovado'
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
            self.StatusChoices.FINALIZADO,
            self.StatusChoices.RECUSADO,
            self.StatusChoices.CANCELADO,
        ]
    
    @property
    def is_aprovada(self):
        return self.status == self.StatusChoices.FINALIZADO

    @property
    def data_finalizacao(self):
        """
        Retorna a data e hora do log que finalizou a solicitação.
        Retorna None se a solicitação não estiver em um status finalizado.
        """
        if not self.is_finalizada:
            return None

        LogAprovacaoModel = self.logs.model
        
        acoes_terminais = [
            LogAprovacaoModel.AcaoChoices.CANCELAMENTO,
            LogAprovacaoModel.AcaoChoices.CANCELAMENTO_SISTEMA,
            LogAprovacaoModel.AcaoChoices.RECUSA_SECUNDARIO,
            LogAprovacaoModel.AcaoChoices.RECUSADO_GESTOR,
            LogAprovacaoModel.AcaoChoices.RECUSADO_DIRETOR,
            LogAprovacaoModel.AcaoChoices.RECUSADO_DP,
            LogAprovacaoModel.AcaoChoices.LANCADO,
        ]

        ultimo_log_final = self.logs.filter(acao__in=acoes_terminais).order_by('-data_acao').first()

        return ultimo_log_final.data_acao if ultimo_log_final else None
    
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

    mes_referencia = models.DateField(
        null=True, blank=True,
        verbose_name="Mês de referência",
        help_text="Armazenado como o primeiro dia do mês para preservar o histórico da regra aplicada."
    )

    data = models.DateTimeField(auto_now_add=True)

    arquivado = models.BooleanField(verbose_name="Arquivar?", default=False)

    def can_comment(self, user):
        """
        Qualquer usuário na posição de aprovador atual, o DP, ou o próprio colaborador pode comentar, desde que a solicitação não esteja finalizada.
        """
        is_dp = user.groups.filter(name='DP').exists()
        is_aprovador_atual = (
            self.status == self.StatusChoices.PENDENTE_ACEITE_SECUNDARIO and self.colaborador_secundario == user or
            self.status == self.StatusChoices.PENDENTE_GESTOR and self.aprovador_atual == user or
            self.status == self.StatusChoices.PENDENTE_DIRETOR and user.cargo and user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR
        )
        is_colaborador = self.colaborador == user
        is_ultimo_aprovador = False
        ultimo_log = self.logs.filter(
            acao__in=[
                self.logs.model.AcaoChoices.APROVADO_GESTOR,
                self.logs.model.AcaoChoices.RECUSADO_GESTOR,
                self.logs.model.AcaoChoices.APROVADO_DIRETOR,
                self.logs.model.AcaoChoices.RECUSADO_DIRETOR,
                self.logs.model.AcaoChoices.APROVADO_DP,
                self.logs.model.AcaoChoices.RECUSADO_DP,
                self.logs.model.AcaoChoices.LANCADO,
            ]
        ).order_by('-data_acao').first()
        if ultimo_log and ultimo_log.ator == user:
            is_ultimo_aprovador = True

        return not self.is_finalizada and (is_dp or is_aprovador_atual or is_ultimo_aprovador or is_colaborador)

    def can_edit(self, user):
        """
        Editar somente se não houver nenhum log de mudança de status (solicitações recém criadas), 
        pelo colaborador que solicitou.
        """
        if self.colaborador != user:
            return False

        if self.status in [self.StatusChoices.FINALIZADO, self.StatusChoices.CANCELADO, self.StatusChoices.RECUSADO]:
            return False
            
        LogAprovacaoModel = self.logs.model
        
        logs_mudanca = [
            LogAprovacaoModel.AcaoChoices.ACEITE_SECUNDARIO,
            LogAprovacaoModel.AcaoChoices.RECUSA_SECUNDARIO,
            LogAprovacaoModel.AcaoChoices.APROVADO_GESTOR,
            LogAprovacaoModel.AcaoChoices.RECUSADO_GESTOR,
            LogAprovacaoModel.AcaoChoices.APROVADO_DIRETOR,
            LogAprovacaoModel.AcaoChoices.RECUSADO_DIRETOR,
            LogAprovacaoModel.AcaoChoices.APROVADO_DP,
            LogAprovacaoModel.AcaoChoices.RECUSADO_DP,
            LogAprovacaoModel.AcaoChoices.LANCADO,
            LogAprovacaoModel.AcaoChoices.CANCELAMENTO,
            LogAprovacaoModel.AcaoChoices.REVERSAO,
        ]
        
        return not self.logs.filter(acao__in=logs_mudanca).exists()

    def can_cancel(self, user):
        """
        Cancelar apenas pelo colaborador solicitante em estado não terminal.
        """
        if self.colaborador != user:
            return False
        if self.status in [self.StatusChoices.FINALIZADO, self.StatusChoices.CANCELADO, self.StatusChoices.RECUSADO]:
            return False
        
        LogAprovacaoModel = self.logs.model
        etapas_avancadas = [
            LogAprovacaoModel.AcaoChoices.APROVADO_GESTOR,
            LogAprovacaoModel.AcaoChoices.APROVADO_DIRETOR,
            LogAprovacaoModel.AcaoChoices.APROVADO_DP,
            LogAprovacaoModel.AcaoChoices.LANCADO,
        ]
        return not self.logs.filter(acao__in=etapas_avancadas).exists()

    def can_edit_dp(self, user):
        """
        Editar pelo usuário da administração, somente nos status pendente DP ou lançamento, 
        somente quando o editor for do DP.
        """
        is_dp = user.groups.filter(name='DP').exists() or user.is_superuser
        return is_dp and self.status in [self.StatusChoices.PENDENTE_DP, self.StatusChoices.LANCAMENTO]

    def ja_revertido_por(self, user):
        """
        Retorna True se este usuário já executou uma reversão nesta solicitação.
        Cada usuário só pode reverter uma decisão por solicitação.
        """
        LogAprovacaoModel = self.logs.model
        return self.logs.filter(
            acao=LogAprovacaoModel.AcaoChoices.REVERSAO,
            ator=user
        ).exists()

    def can_reverse_status(self, user):
        """
        Reverter status, apenas para solicitações que não possuam status terminal,
        apenas pela última pessoa (secundário ou gestor) ou grupo (direção ou DP)
        que aprovou, apenas dentro de 24h desde a última ação registrada, e apenas
        uma vez por usuário nesta solicitação.
        """
        if self.status in [self.StatusChoices.CANCELADO]:
            return False

        if self.ja_revertido_por(user):
            return False

        LogAprovacaoModel = self.logs.model
        acoes_decisao = [
            LogAprovacaoModel.AcaoChoices.ACEITE_SECUNDARIO,
            LogAprovacaoModel.AcaoChoices.RECUSA_SECUNDARIO,
            LogAprovacaoModel.AcaoChoices.APROVADO_GESTOR,
            LogAprovacaoModel.AcaoChoices.RECUSADO_GESTOR,
            LogAprovacaoModel.AcaoChoices.APROVADO_DIRETOR,
            LogAprovacaoModel.AcaoChoices.RECUSADO_DIRETOR,
            LogAprovacaoModel.AcaoChoices.APROVADO_DP,
            LogAprovacaoModel.AcaoChoices.RECUSADO_DP,
            LogAprovacaoModel.AcaoChoices.LANCADO,
        ]

        ultimo_log = self.logs.filter(acao__in=acoes_decisao).order_by('-data_acao').first()
        if not ultimo_log:
            return False

        is_user_direcao = (user.cargo and user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR)
        is_user_dp = user.groups.filter(name='DP').exists()

        prazo_limite = ultimo_log.data_acao + timedelta(hours=24)
        if (timezone.now() > prazo_limite) and not is_user_dp:
            return False

        is_last_action_direcao = ultimo_log.acao in [
            LogAprovacaoModel.AcaoChoices.APROVADO_DIRETOR,
            LogAprovacaoModel.AcaoChoices.RECUSADO_DIRETOR,
        ]
        is_last_action_dp = ultimo_log.acao in [
            LogAprovacaoModel.AcaoChoices.APROVADO_DP,
            LogAprovacaoModel.AcaoChoices.RECUSADO_DP,
            LogAprovacaoModel.AcaoChoices.LANCADO,
        ]
        is_last_action_gestor = ultimo_log.acao in [
            LogAprovacaoModel.AcaoChoices.APROVADO_GESTOR,
            LogAprovacaoModel.AcaoChoices.RECUSADO_GESTOR,
        ]
        is_last_action_colega = ultimo_log.acao in [
            LogAprovacaoModel.AcaoChoices.ACEITE_SECUNDARIO,
            LogAprovacaoModel.AcaoChoices.RECUSA_SECUNDARIO,
        ]

        if is_user_direcao and is_last_action_direcao:
            return True

        if is_user_dp and is_last_action_dp:
            return True

        if is_last_action_gestor and ultimo_log.ator == user:
            return True

        if is_last_action_colega and ultimo_log.ator == user:
            return True

        return False

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

            self.mes_referencia = self.tipo_documento.validar_regras(valores)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Solicitação {self.id} - {self.tipo_documento.nome_documento} - {self.status}"

class NotificacaoAtivaManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(excluida_em__isnull=True)


class Notificacao(models.Model):
    class TipoChoices(models.TextChoices):
        SOLICITACAO_ABERTA = 'SOLICITACAO_ABERTA', 'Solicitação aberta'
        PENDENCIA_SECUNDARIO = 'PENDENCIA_SECUNDARIO', 'Pendente de aceite'
        RESUMO_SEMANAL = 'RESUMO_SEMANAL', 'Resumo semanal'
        APROVADA_DP = 'APROVADA_DP', 'Aprovada pelo DP'
        RECUSADA = 'RECUSADA', 'Solicitação recusada'
        COMENTARIO = 'COMENTARIO', 'Comentário adicionado'
        CANCELADA_SISTEMA = 'CANCELADA_SISTEMA', 'Cancelada pelo sistema'

    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notificacoes',
    )
    solicitacao = models.ForeignKey(
        Solicitacao,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notificacoes',
    )
    tipo = models.CharField(max_length=30, choices=TipoChoices.choices)
    titulo = models.CharField(max_length=150)
    mensagem = models.TextField()
    criada_em = models.DateTimeField(auto_now_add=True)
    visualizada_em = models.DateTimeField(null=True, blank=True)
    excluida_em = models.DateTimeField(null=True, blank=True)
    aviso_login_exibido_em = models.DateTimeField(null=True, blank=True)
    chave = models.CharField(max_length=180, null=True, blank=True, unique=True)

    objects = NotificacaoAtivaManager()
    todos_objetos = models.Manager()

    class Meta:
        ordering = ['-criada_em']
        indexes = [
            models.Index(fields=['destinatario', 'visualizada_em', '-criada_em']),
        ]
        verbose_name = 'Notificação'
        verbose_name_plural = 'Notificações'

    def __str__(self):
        return f'{self.titulo} para {self.destinatario}'


class LogAprovacao(models.Model):
    class Meta:
        verbose_name = "Log de Aprovação"
        verbose_name_plural = "Logs de Aprovação"

    class AcaoChoices(models.TextChoices):
        CRIACAO = 'CRIACAO', 'Criação da Solicitação'
        EDICAO = 'EDICAO', 'Edição da Solicitação'
        CANCELAMENTO = 'CANCELAMENTO', 'Cancelado pelo Solicitante'
        CANCELAMENTO_SISTEMA = 'CANCELAMENTO_SISTEMA', 'Cancelado automaticamente pelo Sistema'
        ACEITE_SECUNDARIO = 'ACEITE_SECUNDARIO', 'Aceite pelo Colega'
        RECUSA_SECUNDARIO = 'RECUSA_SECUNDARIO', 'Recusado pelo Colega'
        APROVADO_GESTOR = 'APROVADO_GESTOR', 'Aprovado pelo Gestor'
        RECUSADO_GESTOR = 'RECUSADO_GESTOR', 'Recusado pelo Gestor'
        APROVADO_DIRETOR = 'APROVADO_DIRETOR', 'Aprovado pelo Diretor'
        RECUSADO_DIRETOR = 'RECUSADO_DIRETOR', 'Recusado pelo Diretor'
        APROVADO_DP = 'APROVADO_DP', 'Documento recebido pelo DP (aguardando a aprovação final)'
        RECUSADO_DP = 'RECUSADO_DP', 'Recusado pelo DP'
        LANCADO = 'LANCADO', 'Aprovado pelo DP'
        COMENTARIO = 'COMENTARIO', 'Comentário Adicionado'
        REVERSAO = 'REVERSAO', 'Reversão de Decisão'

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

class SingletonModel(models.Model):
    """
    Classe abstrata que garante a existência de apenas uma instância (registro) 
    deste model no banco de dados.
    """
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

class Config(SingletonModel):
    """
    Model de configuração global do sistema herdando as características de Singleton.
    """

    nome_instituicao = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Nome da Instituição"
    )
    
    primary_color = models.CharField(
        max_length=7, 
        default="#4f39f6",
        verbose_name="Cor Primária"
    )
    
    secondary_color = models.CharField(
        max_length=7, 
        default="#372aac",
        verbose_name="Cor Secundária"
    )

    emphasis_color = models.CharField(
        max_length=7, 
        default="#ebefff",
        verbose_name="Cor de Destaque"
    )

    logo = models.ImageField(
        upload_to='logos/',
        blank=True,
        null=True,
        verbose_name="Logo da Empresa"
    )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Configuração do Sistema"
        verbose_name_plural = "Configurações do Sistema"

    def __str__(self):
        return "Configurações Globais"
