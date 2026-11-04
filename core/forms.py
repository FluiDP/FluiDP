import json

from django import forms
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from .models import Cargo, Lotacao, CustomUser, TipoDocumento, Solicitacao
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django_q.tasks import async_task
from django.conf import settings
from urllib.parse import urlsplit

STYLE_INPUT = (
    "w-full px-4 py-3 border border-gray-300 rounded-lg text-gray-700 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-secondary focus:border-transparent bg-white"
)
STYLE_CHECKBOX = "h-5 w-5 text-secondary focus:ring-secondary border-gray-300 rounded mt-1"


def password_enter_attrs(next_field=None):
    action = (
        f"this.form.elements.namedItem('{next_field}').focus();" if next_field else
        "this.form.requestSubmit(this.form.querySelector('button[type=submit]'));"
    )
    return {
        'enterkeyhint': 'next' if next_field else 'done',
        'onkeydown': "if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); event.stopPropagation(); if (!event.repeat) { " + action + " } }",
    }


class SenhaDefinitivaForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': STYLE_INPUT, 'autocomplete': 'new-password'})
        self.fields['new_password1'].widget.attrs.update(password_enter_attrs('new_password2'))
        self.fields['new_password2'].widget.attrs.update(password_enter_attrs())

    def clean_new_password1(self):
        password = self.cleaned_data['new_password1']
        if self.user.check_password(password):
            raise forms.ValidationError('Escolha uma senha diferente da senha provisória.')
        return password

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
    is_dp = forms.BooleanField(
        label='Acesso do Departamento Pessoal (DP)',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': STYLE_CHECKBOX})
    )
    is_tic = forms.BooleanField(
        label='Acesso de administrador do sistema (TIC)',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': STYLE_CHECKBOX})
    )

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
            'is_active': forms.CheckboxInput(attrs={'class': STYLE_CHECKBOX})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['email'].required = True
        self.fields['cpf'].required = True
        self.fields['matricula'].required = True

    def save_groups(self, user):
        """Método auxiliar para salvar os grupos na criação do usuário."""
        dp_group, _ = Group.objects.get_or_create(name='DP')
        tic_group, _ = Group.objects.get_or_create(name='TIC')
        
        if self.cleaned_data.get('is_dp'):
            user.groups.add(dp_group)
        if self.cleaned_data.get('is_tic'):
            user.groups.add(tic_group)

class EditCustomUserForm(forms.ModelForm):
    """
    Formulário para editar dados de um CustomUser.
    """
    alterar_senha = forms.BooleanField(
        label='Alterar senha do colaborador?',
        required=False,
        help_text='Marque para definir uma nova senha para o colaborador.',
        widget=forms.CheckboxInput(attrs={
            'class': STYLE_CHECKBOX,
            'id': 'chk_alterar_senha',
            'onchange': 'toggleSenhaFields(this.checked)'
        })
    )
    nova_senha = forms.CharField(
        label='Nova Senha',
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': STYLE_INPUT, 
            'placeholder': 'Digite a nova senha',
            'id': 'input_nova_senha',
            **password_enter_attrs('confirmar_senha'),
        })
    )
    confirmar_senha = forms.CharField(
        label='Confirmar Nova Senha',
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': STYLE_INPUT, 
            'placeholder': 'Confirme a nova senha',
            'id': 'input_confirmar_senha',
            **password_enter_attrs(),
        })
    )
    exigir_redefinicao = forms.BooleanField(
        label='Exigir redefinição de senha no próximo acesso', required=False,
        help_text='Marcada: a senha acima será provisória e o colaborador deverá escolher outra ao entrar. Desmarcada: poderá usar normalmente a senha definida aqui.',
        widget=forms.CheckboxInput(attrs={'class': STYLE_CHECKBOX, 'id': 'chk_exigir_redefinicao'}),
    )
    is_dp = forms.BooleanField(
        label='Acesso do Departamento Pessoal (DP)',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': STYLE_CHECKBOX})
    )
    is_tic = forms.BooleanField(
        label='Acesso de administrador do sistema (TIC)',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': STYLE_CHECKBOX})
    )

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
            'is_active': forms.CheckboxInput(attrs={'class': STYLE_CHECKBOX})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['email'].required = True
        self.fields['cpf'].required = True
        self.fields['matricula'].required = True

        if self.instance and self.instance.pk:
            self.fields['is_dp'].initial = self.instance.groups.filter(name='DP').exists()
            self.fields['is_tic'].initial = self.instance.groups.filter(name='SYSTEM_ADMIN').exists()

    def clean(self):
        cleaned_data = super().clean()
        alterar = cleaned_data.get('alterar_senha')
        nova = cleaned_data.get('nova_senha')
        confirma = cleaned_data.get('confirmar_senha')

        if alterar:
            if not nova or not confirma:
                self.add_error('nova_senha', "Preencha a nova senha e a confirmação.")
            elif nova != confirma:
                self.add_error('confirmar_senha', "As senhas não coincidem. Tente novamente.")
                
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        
        if self.cleaned_data.get('alterar_senha'):
            nova_senha = self.cleaned_data.get('nova_senha')
            user.set_password(nova_senha)
            user.precisa_trocar_senha = self.cleaned_data.get('exigir_redefinicao', False)
            user.senha_provisoria_definida_em = timezone.now() if user.precisa_trocar_senha else None
            
        if commit:
            user.save()
            self.save_m2m()
            
            dp_group, _ = Group.objects.get_or_create(name='DP')
            tic_group, _ = Group.objects.get_or_create(name='SYSTEM_ADMIN')
            
            if self.cleaned_data.get('is_dp'):
                user.groups.add(dp_group)
            else:
                user.groups.remove(dp_group)
                
            if self.cleaned_data.get('is_tic'):
                user.groups.add(tic_group)
            else:
                user.groups.remove(tic_group)
                
        return user

class JSONTextarea(forms.Textarea):
    """Exibe JSON com indentação, preservando texto inválido para correção."""

    def format_value(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                return super().format_value(value)
        return json.dumps(value, ensure_ascii=False, indent=2)


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
            'tipo_referencia',
            'dia_abertura_mes_anterior',
            'dia_limite_mes_referencia',
            'restringir_datas_ao_mes_referencia',
            'limite_dias_antecedencia',
            'definicao_formulario',
            'disponivel',
        ]
        widgets = {
            'nome_documento': forms.TextInput(attrs={'class': STYLE_INPUT}),
            'dia_inicio': forms.NumberInput(attrs={'class': STYLE_INPUT, 'min': 1, 'max': 31}),
            'dia_fim': forms.NumberInput(attrs={'class': STYLE_INPUT, 'min': 1, 'max': 31}),
            'tipo_referencia': forms.Select(attrs={'class': STYLE_INPUT}),
            'dia_abertura_mes_anterior': forms.NumberInput(attrs={'class': STYLE_INPUT, 'min': 1, 'max': 31}),
            'dia_limite_mes_referencia': forms.NumberInput(attrs={'class': STYLE_INPUT, 'min': 1, 'max': 31}),
            'restringir_datas_ao_mes_referencia': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-secondary focus:ring-secondary border-gray-300 rounded'}),
            'limite_dias_antecedencia': forms.NumberInput(attrs={'class': STYLE_INPUT, 'min': 0}),
            'definicao_formulario': JSONTextarea(attrs={
                'rows': 18, 'class': STYLE_INPUT, 'spellcheck': 'false', 'wrap': 'off',
                'data-json-editor': 'true',
                'style': 'font-family: monospace; font-size: 0.9em; tab-size: 2;',
            }),
            'disponivel': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-secondary focus:ring-secondary border-gray-300 rounded'})
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

class CustomPasswordResetForm(PasswordResetForm):
    def send_mail(self, subject_template_name, email_template_name,
                  context, from_email, to_email, html_email_template_name=None):
        
        site = urlsplit(settings.SITE_URL)
        async_task(
            'core.services.enviar_email_recuperacao', context['user'].pk,
            context['uid'], context['token'], site.netloc, site.scheme, to_email,
            from_email, subject_template_name, email_template_name, html_email_template_name,
        )
