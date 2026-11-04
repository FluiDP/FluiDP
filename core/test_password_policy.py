from django.contrib.auth.models import Group
from django.test import TestCase, override_settings, Client
from django.urls import reverse
from django.utils import timezone
from .models import CustomUser
from .forms import EditCustomUserForm


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class SenhaProvisoriaTests(TestCase):
    def test_enter_avanca_e_confirma_sem_envio_duplicado(self):
        import json
        import shutil
        import subprocess
        from .forms import SenhaDefinitivaForm, CustomSetPasswordForm
        if not shutil.which('node'):
            self.skipTest('Node necessário para testar eventos de teclado')
        for form, primeiro, segundo in (
            (EditCustomUserForm(instance=self.user), 'nova_senha', 'confirmar_senha'),
            (SenhaDefinitivaForm(self.user), 'new_password1', 'new_password2'),
            (CustomSetPasswordForm(self.user), 'new_password1', 'new_password2'),
        ):
            payload = {'first': form.fields[primeiro].widget.attrs['onkeydown'],
                       'last': form.fields[segundo].widget.attrs['onkeydown'], 'next': segundo}
            code = r"""
const assert = require('node:assert/strict'); let raw='';
process.stdin.on('data', x=>raw+=x); process.stdin.on('end',()=>{
 const data=JSON.parse(raw); let submitted=0,focused=0,prevented=0;
 const button={type:'submit'};
 const input={form:{elements:{namedItem:n=>{assert.equal(n,data.next);return {focus:()=>focused++};}},querySelector:()=>button,requestSubmit:b=>{assert.equal(b,button);submitted++;}}};
 function run(code, props={}){new Function('event',code).call(input,{key:'Enter',repeat:false,isComposing:false,preventDefault:()=>prevented++,stopPropagation:()=>{},...props});}
 run(data.first); assert.equal(focused,1); assert.equal(submitted,0); assert.equal(prevented,1);
 run(data.last); assert.equal(submitted,1);
 run(data.last,{repeat:true}); assert.equal(submitted,1);
 run(data.first,{isComposing:true}); assert.equal(focused,1);
 run(data.last,{key:'Tab'}); assert.equal(submitted,1);
});"""
            subprocess.run([shutil.which('node'), '-e', code], input=json.dumps(payload),
                           text=True, encoding='utf-8', capture_output=True, check=True)

    def setUp(self):
        self.user = CustomUser.objects.create_user(username='senha_teste', first_name='Teste',
            email='teste@example.com', cpf='52998224725', matricula='991', password='Provisoria!X234', precisa_trocar_senha=True, senha_provisoria_definida_em=timezone.now())

    def test_flag_legada_nao_obriga_troca_sem_nova_opcao(self):
        self.user.senha_provisoria_definida_em = None
        self.user.save()
        response = self.client.post(reverse('login'), {'username':'senha_teste','password':'Provisoria!X234'})
        self.assertRedirects(response, reverse('painel'), fetch_redirect_response=False)

    def dados(self, **extra):
        return {'first_name': 'Teste', 'email': 'teste@example.com', 'cpf': '52998224725',
                'matricula': '991', 'is_active': 'on', **extra}

    def test_senha_definitiva_pelo_cadastro_limpa_flag_anterior(self):
        form = EditCustomUserForm(self.dados(alterar_senha='on', nova_senha='NovaSenha!X234', confirmar_senha='NovaSenha!X234'), instance=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.user.refresh_from_db()
        self.assertFalse(self.user.precisa_trocar_senha)
        self.assertTrue(self.user.check_password('NovaSenha!X234'))

    def test_opcao_marcada_define_senha_provisoria(self):
        form = EditCustomUserForm(self.dados(alterar_senha='on', exigir_redefinicao='on', nova_senha='NovaSenha!X234', confirmar_senha='NovaSenha!X234'), instance=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertTrue(CustomUser.objects.get(pk=self.user.pk).precisa_trocar_senha)

    def test_senha_administrativa_preserva_exatamente_o_valor_digitado(self):
        senha = ' Provisoria!X234 '
        form = EditCustomUserForm(self.dados(alterar_senha='on', exigir_redefinicao='on',
            nova_senha=senha, confirmar_senha=senha), instance=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(senha))
        self.assertFalse(self.user.check_password(senha.strip()))
        response = self.client.post(reverse('login'), {'username':'991','password':senha})
        self.assertRedirects(response, reverse('senha_definitiva'))

    def test_editar_outros_dados_nao_muda_flag_nem_senha(self):
        for flag in (True, False):
            self.user.precisa_trocar_senha = flag
            self.user.save()
            form = EditCustomUserForm(self.dados(), instance=self.user)
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
            self.user.refresh_from_db()
            self.assertEqual(self.user.precisa_trocar_senha, flag)
            self.assertTrue(self.user.check_password('Provisoria!X234'))

    def test_login_senha_provisoria_abre_modal(self):
        response = self.client.post(reverse('login'), {'username':'senha_teste','password':'Provisoria!X234'})
        self.assertRedirects(response, reverse('senha_definitiva'))
        response = self.client.get(reverse('senha_definitiva'))
        self.assertContains(response, 'role="dialog"')

    def test_gate_bloqueia_paginas_post_e_htmx_inclusive_mobile(self):
        self.client.force_login(self.user)
        for path in ('/m/', '/admin/', '/administracao/', '/colaborador/', '/solicitacoes/lote/'):
            self.assertRedirects(self.client.get(path), reverse('senha_definitiva'))
            response = self.client.post(path, {}, headers={'HX-Request':'true'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['HX-Redirect'], reverse('senha_definitiva'))
        response = self.client.get(reverse('senha_definitiva'), HTTP_USER_AGENT='iPhone Mobile')
        self.assertContains(response, 'role="dialog"')

    def test_senha_definitiva_invalida_nao_libera(self):
        self.client.force_login(self.user)
        for senha, confirma in [('Provisoria!X234','Provisoria!X234'), ('abc','abc'), ('Definitiva!A567','outra')]:
            response = self.client.post(reverse('senha_definitiva'), {'new_password1':senha,'new_password2':confirma})
            self.assertEqual(response.status_code, 200)
            self.user.refresh_from_db()
            self.assertTrue(self.user.precisa_trocar_senha)
            self.assertTrue(self.user.check_password('Provisoria!X234'))

    def test_troca_invalida_senha_provisoria_e_mantem_sessao(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('senha_definitiva'), {'new_password1':'Definitiva!A567','new_password2':'Definitiva!A567'})
        self.assertRedirects(response, reverse('painel'), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertFalse(self.user.precisa_trocar_senha)
        self.assertTrue(self.user.check_password('Definitiva!A567'))
        self.assertIn('_auth_user_id', self.client.session)
        self.assertFalse(self.client.login(username='senha_teste',password='Provisoria!X234'))
        self.assertTrue(self.client.login(username='senha_teste',password='Definitiva!A567'))

    def test_senha_sem_exigencia_nao_abre_modal(self):
        self.user.precisa_trocar_senha = False
        self.user.save()
        response = self.client.post(reverse('login'), {'username':'senha_teste','password':'Provisoria!X234'})
        self.assertRedirects(response, reverse('painel'), fetch_redirect_response=False)

    def test_formulario_tem_opcao_e_acesso_continua_restrito(self):
        dp = CustomUser.objects.create_user(username='dp_password')
        dp.groups.add(Group.objects.create(name='DP'))
        self.client.force_login(dp)
        response = self.client.get(reverse('administracao:edit_colaborador',args=[self.user.pk]))
        self.assertContains(response, 'name="exigir_redefinicao"')
        self.user.precisa_trocar_senha=False
        self.user.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('administracao:edit_colaborador',args=[dp.pk])).status_code,403)

    def test_csrf_obrigatorio(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse('senha_definitiva'), {'new_password1':'Definitiva!A567','new_password2':'Definitiva!A567'}).status_code,403)

    def test_reset_por_email_tambem_encerra_exigencia(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        token = default_token_generator.make_token(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.get(reverse('password_reset_confirm', args=[uid,token]))
        pagina = self.client.get(response.url)
        self.assertContains(pagina, 'enterkeyhint="next"')
        self.assertContains(pagina, 'enterkeyhint="done"')
        response = self.client.post(response.url, {'new_password1':'Definitiva!A567','new_password2':'Definitiva!A567'})
        self.assertRedirects(response, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertFalse(self.user.precisa_trocar_senha)
