from django import forms
from django.contrib.auth import get_user_model
from .models import Cargo, Lotacao, CustomUser, TipoDocumento, Solicitacao


class CargoForm(forms.ModelForm):
    """
    Formulário para criar e editar Cargos.
    """
    class Meta:
        model = Cargo
        fields = ['nome_cargo', 'hierarquia']


class LotacaoForm(forms.ModelForm):
    """
    Formulário para criar e editar Lotações.
    """
    class Meta:
        model = Lotacao
        fields = ['nome_lotacao', 'chefia', 'chefia_secundaria', 'lotacao_pai']

    def __init__(self, *args, **kwargs):
        """
        Sobrescreve o __init__ para filtrar os campos de chefia.
        Isso impede que um usuário "Padrão" seja escolhido como chefe.
        """
        super().__init__(*args, **kwargs)

        gestores_qs = get_user_model().objects.filter(
            cargo__hierarquia__in=[
                Cargo.HierarquiaChoices.PADRAO,
                Cargo.HierarquiaChoices.DIRETOR,
                Cargo.HierarquiaChoices.GERENTE,
                Cargo.HierarquiaChoices.COORDENADOR
            ]
        )
        
        self.fields['chefia'].queryset = gestores_qs
        self.fields['chefia_secundaria'].queryset = gestores_qs


class CustomUserForm(forms.ModelForm):
    """
    Formulário para *editar* dados de um CustomUser.
    (Formulários de criação são geralmente separados).
    """
    class Meta:
        model = CustomUser
        
        fields = [
            'username', 'first_name', 'last_name', 'email',
            'cpf', 'matricula', 'cargo', 'lotacao',
            'ausencia_inicio', 'ausencia_fim',
            'is_active', 'is_staff'
        ]
        
        widgets = {
            'ausencia_inicio': forms.DateInput(
                attrs={'type': 'date'},
                format='%Y-%m-%d'
            ),
            'ausencia_fim': forms.DateInput(
                attrs={'type': 'date'},
                format='%Y-%m-%d'
            ),
        }


class TipoDocumentoForm(forms.ModelForm):
    """
    Formulário para criar e editar Tipos de Documento.
    """
    class Meta:
        model = TipoDocumento
        fields = [
            'nome_documento',
            'requer_aprovacao_gestor',
            'requer_aprovacao_diretor',
            'definicao_formulario'
        ]
        widgets = {
            'definicao_formulario': forms.Textarea(attrs={'rows': 10}),
        }
        help_texts = {
            'definicao_formulario': 'Defina a estrutura JSON para os campos dinâmicos deste formulário.'
        }


class SolicitacaoForm(forms.ModelForm):
    """
    Formulário para um *usuário criar* uma nova Solicitação.
    Campos como 'status' e 'aprovador_atual' são definidos no backend.
    """
    class Meta:
        model = Solicitacao
        
        fields = [
            'tipo_documento',
            'colaborador_secundario',
            'dados_preenchidos'
        ]
        
        widgets = {
            'dados_preenchidos': forms.Textarea(attrs={'rows': 5}),
        }
        help_texts = {
            'colaborador_secundario': 'Selecione um colega se este documento exigir aceite (ex: troca de plantão).',
            'dados_preenchidos': 'Dados específicos da solicitação (será um formulário dinâmico no futuro).'
        }

    def __init__(self, *args, **kwargs):
        """
        Torna campos opcionais realmente opcionais no formulário.
        """
        super().__init__(*args, **kwargs)
        self.fields['colaborador_secundario'].required = False
        self.fields['dados_preenchidos'].required = False
