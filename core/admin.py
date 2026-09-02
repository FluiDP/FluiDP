from django.contrib import admin
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Cargo, Lotacao, TipoDocumento, Solicitacao, LogAprovacao, Notificacao

class CustomUserAdmin(UserAdmin):
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),

        ("Dados Institucionais (ERS)", {
            "fields": ("matricula", "cpf", "cargo", "lotacao"),
        }),
        
        ("Permissions", {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            ),
        }),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'matricula')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'lotacao', 'cargo')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'matricula')

admin.site.register(CustomUser, CustomUserAdmin)

@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ('nome_cargo',)
    search_fields = ('nome_cargo',)

@admin.register(Lotacao)
class LotacaoAdmin(admin.ModelAdmin):
    list_display = ('nome_lotacao', 'chefia', 'chefia_secundaria', 'lotacao_pai')
    search_fields = ('nome_lotacao',)
    list_filter = ('chefia', 'chefia_secundaria')
    
@admin.register(TipoDocumento)
class TipoDocumentoAdmin(admin.ModelAdmin):
    list_display = ('nome_documento', 'requer_aprovacao_gestor', 'requer_aprovacao_diretor')
    list_filter = ('requer_aprovacao_gestor', 'requer_aprovacao_diretor')

@admin.register(Solicitacao)
class SolicitacaoAdmin(admin.ModelAdmin):
    list_display = ('id', '__str__', 'status', 'colaborador', 'mes_referencia', 'aprovador_atual')
    search_fields = ('colaborador__username', 'tipo_documento__nome_documento')
    list_filter = ('status', 'tipo_documento')

@admin.register(LogAprovacao)
class LogAprovacaoAdmin(admin.ModelAdmin):
    list_display = ('solicitacao', 'acao', 'ator', 'data_acao')
    list_filter = ('acao',)
    readonly_fields = ('solicitacao', 'ator', 'acao', 'data_acao', 'detalhes')


@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'destinatario', 'tipo', 'criada_em', 'visualizada_em', 'excluida_em')
    list_filter = ('tipo', 'visualizada_em', 'excluida_em')
    search_fields = ('titulo', 'mensagem', 'destinatario__username')
    readonly_fields = ('criada_em', 'visualizada_em', 'excluida_em')

    def get_queryset(self, request):
        return Notificacao.todos_objetos.all()
