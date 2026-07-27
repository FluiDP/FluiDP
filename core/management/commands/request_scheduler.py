from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from core.models import Solicitacao, LogAprovacao, Cargo

User = get_user_model()

class Command(BaseCommand):
    help = """
    Verifica gestores ausentes (férias) ou mudanças de hierarquia e escalona solicitações pendentes.
    Adicionalmente, cancela solicitações que possuem prazo após 30 dias do encerramento do período ou que envolvam um colaborador e/ou colaborador
    secundário inativos no sistema.
    """

    data_hora = None

    def handle(self, *args, **kwargs):
        self.data_hora = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S")
        self.stdout.write(f"{self.data_hora} - Iniciando verificação de escalonamento...")

        dias_arquivamento_apos_finalizacao = 30
        
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

        solicitacoes_pendencia_secundaria = Solicitacao.objects.filter(
            status=Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO
        ).select_related(
            'colaborador',
            'colaborador__lotacao',
            'colaborador__cargo'
        )
        
        solicitacoes_pendentes = Solicitacao.objects.filter(
            status=Solicitacao.StatusChoices.PENDENTE_GESTOR
        ).select_related(
            'aprovador_atual',
            'colaborador',
            'colaborador__lotacao',
            'colaborador__cargo'
        )

        solicitacoes_finalizadas = Solicitacao.objects.filter(
            status__in=[
                Solicitacao.StatusChoices.CANCELADO,
                Solicitacao.StatusChoices.RECUSADO,
                Solicitacao.StatusChoices.FINALIZADO
            ]
        )
        
        count_escalonadas = 0
        count_canceladas = 0

        for sol in solicitacoes_pendencia_secundaria:
            colega = sol.colaborador_secundario
            tipo_doc = sol.tipo_documento
            motivo_txt = ""

            if not colega:
                sol.status = Solicitacao.StatusChoices.CANCELADO
                sol.save()
                motivo_txt = "não há um colaborador substituto definido"
                count_canceladas += 1

            elif colega.is_ausente and colega.ausencia_fim and not sol.tipo_documento.esta_no_periodo(date=colega.ausencia_fim):
                sol.status = Solicitacao.StatusChoices.CANCELADO
                sol.save()
                motivo_txt = f"o colaborador substituto ({colega.get_full_name()}) encontra-se ausente até {colega.ausencia_fim.strftime('%d/%m/%Y')} (após o prazo final de aceite para as trocas)."
                count_canceladas += 1

            elif not sol.tipo_documento.esta_no_periodo():
                sol.status = Solicitacao.StatusChoices.CANCELADO
                sol.save()
                motivo_txt = f"solicitação não aceita pelo colega dentro do período determinado por regras institucionais"
                count_canceladas += 1

            if motivo_txt:
                LogAprovacao.objects.create(
                    solicitacao=sol,
                    ator=sistema_user,
                    acao=LogAprovacao.AcaoChoices.COMENTARIO,
                    detalhes=f'Cancelamento automático: {motivo_txt}.'
                )

        for sol in solicitacoes_pendentes:
            gestor_atual = sol.aprovador_atual
            
            if not gestor_atual:
                continue
                
            is_ausente = gestor_atual.is_ausente
            
            is_gestor_valido = self.is_prox_gestor_na_hierarquia(sol.colaborador.lotacao, gestor_atual)
            
            if is_ausente or not is_gestor_valido:
                novo_gestor = sol.colaborador.lotacao.find_gestor_disponivel(solicitante=sol.colaborador)
                is_diretor = novo_gestor and novo_gestor.cargo and novo_gestor.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR

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
                    
                    self.stdout.write(self.style.SUCCESS(f"{self.data_hora} - Solicitação #{sol.id} escalonada para {novo_gestor.get_full_name()}"))
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
                    self.stdout.write(self.style.WARNING(f"{self.data_hora} - Solicitação #{sol.id} enviada ao DP (Sem chefia disponível)."))
                    count_escalonadas += 1

        prazo_arquivamento = timezone.now() - timedelta(days=dias_arquivamento_apos_finalizacao)

        for sol in solicitacoes_finalizadas:
            if sol.data_finalizacao and sol.data_finalizacao < prazo_arquivamento:
                sol.arquivado = True
                sol.save()
                
                self.stdout.write(self.style.SUCCESS(
                    f"{self.data_hora} - Solicitação #{sol.id} arquivada (finalizada em {sol.data_finalizacao.strftime('%d/%m/%Y')})."
                ))

        self.stdout.write(self.style.SUCCESS(f"{self.data_hora} - Rotina finalizada. {count_escalonadas} solicitações reatribuídas/escalonadas e {count_canceladas} canceladas automaticamente."))

    def is_prox_gestor_na_hierarquia(self, lotacao_colaborador, gestor):
        """
        Sobe a hierarquia da lotação do colaborador para verificar se o gestor é exatamente o próximo na hierarquia.
        """
        if not lotacao_colaborador:
            return False
            
        atual = lotacao_colaborador
        visitados = set()
        
        while atual and atual.id not in visitados:
            visitados.add(atual.id)
            
            chefia_ausente = getattr(atual.chefia, 'is_ausente', False) if atual.chefia else False
            
            if atual.chefia == gestor or (atual.chefia_secundaria == gestor and (atual.chefia is None or chefia_ausente)):
                return True
                
            if atual.chefia is not None or atual.chefia_secundaria is not None:
                return False
                
            atual = atual.lotacao_pai
            
        return False
