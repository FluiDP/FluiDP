from unittest.mock import patch
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from .models import CustomUser
from .services import enviar_email_recuperacao


@override_settings(SITE_URL='https://fluidp.example.test', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', STORAGES={
    'default': {'BACKEND':'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class RecuperacaoEmFilaTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(username='email_fila', email='fila@example.test', password='Teste!X24680')

    def solicitar(self, email='fila@example.test', htmx=True):
        return self.client.post(reverse('reset_password'), {'email':email},
            headers={'HX-Request':'true'} if htmx else {})

    @patch('core.forms.async_task')
    @patch('core.services.EmailMultiAlternatives.send', side_effect=RuntimeError('SMTP indisponivel'))
    def test_feedback_imediato_sem_chamar_smtp(self, send, queue):
        response = self.solicitar()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'E-mail de redefinição enviado!')
        self.assertNotContains(response, '<html')
        self.assertNotContains(response, 'type="submit"')
        send.assert_not_called()
        queue.assert_called_once()
        args = queue.call_args.args
        self.assertEqual(args[0], 'core.services.enviar_email_recuperacao')
        self.assertEqual(args[1], self.user.pk)
        self.assertEqual(args[4:6], ('fluidp.example.test', 'https'))

    @patch('core.forms.async_task')
    def test_worker_envia_email_com_link_valido(self, queue):
        self.solicitar()
        self.assertTrue(enviar_email_recuperacao(*queue.call_args.args[1:]))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['fila@example.test'])
        self.assertIn('https://fluidp.example.test/reset_password_confirm/', mail.outbox[0].alternatives[0][0])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Teste!X24680'))

    @patch('core.forms.async_task')
    def test_worker_descarta_link_invalidado_antes_do_envio(self, queue):
        self.solicitar()
        self.user.set_password('Outra!X24680')
        self.user.save()
        self.assertFalse(enviar_email_recuperacao(*queue.call_args.args[1:]))
        self.assertEqual(len(mail.outbox), 0)

    @patch('core.forms.async_task')
    def test_contas_inelegiveis_tem_mesmo_feedback_sem_tarefa(self, queue):
        for tipo in ('desconhecida', 'inativa', 'sem_senha'):
            if tipo == 'inativa':
                self.user.is_active = False
                self.user.save()
            elif tipo == 'sem_senha':
                self.user.is_active = True
                self.user.set_unusable_password()
                self.user.save()
            response = self.solicitar('outro@example.test' if tipo == 'desconhecida' else self.user.email)
            self.assertContains(response, 'E-mail de redefinição enviado!')
        queue.assert_not_called()

    @patch('core.forms.async_task', side_effect=RuntimeError('Fila indisponivel'))
    def test_falha_na_fila_mostra_erro_e_libera_tentativa(self, queue):
        with self.assertLogs('core.views', level='ERROR'):
            response = self.solicitar()
        self.assertContains(response, 'Não foi possível solicitar o envio agora.')
        self.assertNotContains(response, 'E-mail de redefinição enviado!')
        self.assertContains(response, 'type="submit"')

    @patch('core.forms.async_task')
    def test_fallback_sem_javascript_e_validacao(self, queue):
        response = self.solicitar(htmx=False)
        self.assertRedirects(response, reverse('password_reset_done'))
        response = self.solicitar(email='invalido')
        self.assertContains(response, 'name="email"')
        self.assertNotContains(response, 'E-mail de redefinição enviado!')
        self.assertEqual(queue.call_count, 1)

    @patch('core.forms.async_task')
    def test_falha_smtp_e_registravel_pelo_worker(self, queue):
        self.solicitar()
        with patch('core.services.EmailMultiAlternatives.send', side_effect=RuntimeError('SMTP indisponivel')):
            with self.assertRaises(RuntimeError):
                enviar_email_recuperacao(*queue.call_args.args[1:])
