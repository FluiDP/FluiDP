from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import Solicitacao, LogAprovacao, Cargo

User = get_user_model()

class Command(BaseCommand):
    help = 'Verifica gestores ausentes (férias) ou mudanças de hierarquia e escalona solicitações pendentes.'

    def handle(self, *args, **kwargs):
        self.stdout.write("Iniciando rotina de verificação de escalonamento...")
        
        sistema_user, created = User.objects.get_or_create(
            username='sistema_automacao',
            defaults={
                'first_name': 'SISTEMA',
                'is_active': False,
                'cpf': '00000000000',
                'password': '!',
            }
        )

        if created:
            sistema_user.set_unusable_password()
            sistema_user.save()
        
        solicitacoes_pendentes = Solicitacao.objects.filter(
            status=Solicitacao.StatusChoices.PENDENTE_GESTOR
        ).select_related(
            'aprovador_atual',
            'colaborador',
            'colaborador__lotacao',
            'colaborador__cargo'
        )
        
        count_escalonadas = 0

        for sol in solicitacoes_pendentes:
            gestor_atual = sol.aprovador_atual
            
            if not gestor_atual:
                continue
                
            is_ausente = gestor_atual.is_ausente
            
            is_gestor_valido = self.is_gestor_na_hierarquia(sol.colaborador.lotacao, gestor_atual)
            
            if is_ausente or not is_gestor_valido:
                
                novo_gestor = sol.colaborador.lotacao.find_gestor_disponivel(solicitante=sol.colaborador)

                is_diretor = novo_gestor.cargo and novo_gestor.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR

                if novo_gestor and novo_gestor != gestor_atual:
                    sol.aprovador_atual = novo_gestor

                    if is_diretor:
                        sol.status = Solicitacao.StatusChoices.PENDENTE_DIRETOR
                    else:
                        sol.status = Solicitacao.StatusChoices.PENDENTE_GESTOR
                        
                    sol.save()
                    
                    motivo_txt = "encontra-se ausente" if is_ausente else "não é o responsável pelo colaborador no momento"
                    
                    LogAprovacao.objects.create(
                        solicitacao=sol,
                        ator=sistema_user,
                        acao=LogAprovacao.AcaoChoices.COMENTARIO,
                        detalhes=f'Escalonamento Automático: O aprovador anterior ({gestor_atual.get_full_name()}) {motivo_txt}. Solicitação encaminhada para {"direção" if is_diretor else "novo aprovador (" + novo_gestor.get_full_name() + ")"}.'
                    )
                    
                    self.stdout.write(self.style.SUCCESS(f"Solicitação #{sol.id} escalonada para {novo_gestor.get_full_name()}"))
                    count_escalonadas += 1
                
                elif not novo_gestor:
                    
                    sol.status = Solicitacao.StatusChoices.PENDENTE_DP
                    sol.aprovador_atual = None
                    sol.save()

                    motivo_txt = "encontra-se ausente" if is_ausente else "não é o responsável pelo colaborador no momento"
                    
                    LogAprovacao.objects.create(
                        solicitacao=sol,
                        ator=sistema_user,
                        acao=LogAprovacao.AcaoChoices.COMENTARIO,
                        detalhes=f'Escalonamento Automático: O aprovador anterior ({gestor_atual.get_full_name()}) {motivo_txt} e não houveram substitutos disponíveis. Encaminhado ao DP.'
                    )
                    self.stdout.write(self.style.WARNING(f"Solicitação #{sol.id} enviada ao DP (Sem chefia disponível)."))
                    count_escalonadas += 1

        self.stdout.write(self.style.SUCCESS(f"Rotina finalizada. {count_escalonadas} solicitações reatribuídas/escalonadas automaticamente."))

    def is_gestor_na_hierarquia(self, lotacao_colaborador, gestor):
        """
        Sobe a hierarquia da lotação do colaborador para verificar se o 'gestor'
        é o chefe direto ou chefe de alguma lotação pai.
        """
        if not lotacao_colaborador:
            return False
            
        atual = lotacao_colaborador
        visitados = set()
        
        while atual and atual.id not in visitados:
            visitados.add(atual.id)
            
            if atual.chefia == gestor or (atual.chefia_secundaria == gestor and (atual.chefia is None or atual.chefia.is_ausente)):
                return True
                
            atual = atual.lotacao_pai
            
        return False
