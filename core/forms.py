from django import forms
from django.contrib.auth import get_user_model
from .models import Cargo, Lotacao, CustomUser, TipoDocumento, Solicitacao

STYLE_INPUT = (
    "w-full px-4 py-3 border border-gray-300 rounded-lg text-gray-700 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white"
)

class CargoForm(forms.ModelForm):
    """
    Formulário para criar e editar Cargos.
    """
    class Meta:
        model = Cargo
        fields = ['nome_cargo', 'hierarquia']
        widgets = {
            'nome_cargo': forms.TextInput(attrs={'class': STYLE_INPUT, 'placeholder': 'Ex: Analista de RH'}),
            'hierarquia': forms.Select(attrs={'class': STYLE_INPUT}),
        }


class LotacaoForm(forms.ModelForm):
    """
    Formulário para criar e editar Lotações.
    """
    class Meta:
        model = Lotacao
        fields = ['nome_lotacao', 'chefia', 'chefia_secundaria', 'lotacao_pai']
        widgets = {
            'nome_lotacao': forms.TextInput(attrs={'class': STYLE_INPUT, 'placeholder': 'Ex: Departamento Pessoal'}),
            'chefia': forms.Select(attrs={'class': STYLE_INPUT}),
            'chefia_secundaria': forms.Select(attrs={'class': STYLE_INPUT}),
            'lotacao_pai': forms.Select(attrs={'class': STYLE_INPUT}),
        }

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
        
        self.fields['chefia'].empty_label = "Selecione um Gestor (Opcional)"
        self.fields['chefia_secundaria'].empty_label = "Selecione um Substituto (Opcional)"
        self.fields['lotacao_pai'].empty_label = "Nenhuma (Lotação Raiz)"


class CustomUserForm(forms.ModelForm):
    """
    Formulário para cadastrar usuário.
    """
    class Meta:
        model = CustomUser
        
        fields = [
            'first_name', 'email',
            'cpf', 'matricula', 'cargo', 'lotacao',
            'is_active'
        ]

        labels = {
            'first_name': 'Nome Completo',
        }
        
        widgets = {
            'first_name': forms.TextInput(attrs={'class': STYLE_INPUT, 'required': True}),
            'email': forms.EmailInput(attrs={'class': STYLE_INPUT}),
            'cpf': forms.TextInput(attrs={'class': STYLE_INPUT, 'required': True}),
            'matricula': forms.TextInput(attrs={'class': STYLE_INPUT, 'required': True}),
            'cargo': forms.Select(attrs={'class': STYLE_INPUT, 'required': True}),
            'lotacao': forms.Select(attrs={'class': STYLE_INPUT, 'required': True}),
        }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['first_name'].required = True
            self.fields['email'].required = True
            self.fields['cpf'].required = True
            self.fields['matricula'].required = True

class EditCustomUserForm(forms.ModelForm):
    """
    Formulário para editar dados de um CustomUser.
    """
    class Meta:
        model = CustomUser
        
        fields = [
            'first_name', 'email',
            'cpf', 'matricula', 'cargo', 'lotacao',
            'ausencia_inicio', 'ausencia_fim',
            'is_active'
        ]

        labels = {
            'first_name': 'Nome Completo',
        }
        
        widgets = {
            'first_name': forms.TextInput(attrs={'class': STYLE_INPUT}),
            'email': forms.EmailInput(attrs={'class': STYLE_INPUT}),
            'cpf': forms.TextInput(attrs={'class': STYLE_INPUT}),
            'matricula': forms.TextInput(attrs={'class': STYLE_INPUT}),
            'cargo': forms.Select(attrs={'class': STYLE_INPUT}),
            'lotacao': forms.Select(attrs={'class': STYLE_INPUT}),
            'ausencia_inicio': forms.DateInput(attrs={'type': 'date', 'class': STYLE_INPUT}, format='%Y-%m-%d'),
            'ausencia_fim': forms.DateInput(attrs={'type': 'date', 'class': STYLE_INPUT}, format='%Y-%m-%d'),
        }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['first_name'].required = True
            self.fields['email'].required = True
            self.fields['cpf'].required = True
            self.fields['matricula'].required = True

class TipoDocumentoForm(forms.ModelForm):
    """
    Formulário para criar e editar Tipos de Documento.
    """
    class Meta:
        model = TipoDocumento
        fields = [
            'nome_documento',
            'dia_inicio',
            'dia_fim',
            'limite_dias_antecedencia',
            'definicao_formulario',
            'disponivel',
        ]
        widgets = {
            'nome_documento': forms.TextInput(attrs={'class': STYLE_INPUT}),
            'dia_inicio': forms.NumberInput(attrs={'class': STYLE_INPUT, 'min': 1, 'max': 31}),
            'dia_fim': forms.NumberInput(attrs={'class': STYLE_INPUT, 'min': 1, 'max': 31}),
            'limite_dias_antecedencia': forms.NumberInput(attrs={'class': STYLE_INPUT, 'min': 0}),
            'definicao_formulario': forms.Textarea(attrs={'rows': 10, 'class': STYLE_INPUT, 'style': 'font-family: monospace; font-size: 0.9em;'}),
            'disponivel': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded'})
        }


class SolicitacaoForm(forms.ModelForm):
    """
    Formulário para um *usuário criar* uma nova Solicitação.
    """
    class Meta:
        model = Solicitacao
        
        fields = [
            'tipo_documento',
            'colaborador_secundario',
            'dados_preenchidos'
        ]
        
        widgets = {
            'tipo_documento': forms.Select(attrs={'class': STYLE_INPUT}),
            'colaborador_secundario': forms.Select(attrs={'class': STYLE_INPUT}),
            'dados_preenchidos': forms.Textarea(attrs={'rows': 5, 'class': STYLE_INPUT}),
        }
        help_texts = {
            'colaborador_secundario': 'Selecione um colega se este documento exigir aceite.',
            'dados_preenchidos': 'Dados específicos da solicitação (formulário dinâmico).'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['colaborador_secundario'].required = False
        self.fields['dados_preenchidos'].required = False