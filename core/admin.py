from django.contrib import admin
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Cargo, Lotacao, TipoDocumento, Solicitacao, LogAprovacao

class CustomUserAdmin(UserAdmin):
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),

        ("Dados Institucionais (ERS)", {
            "fields": ("matricula", "cpf", "id_cargo", "id_lotacao"),
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
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'id_lotacao', 'id_cargo')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'matricula')

admin.site.register(CustomUser, CustomUserAdmin)

@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ('nome_cargo',)
    search_fields = ('nome_cargo',)

@admin.register(Lotacao)
class LotacaoAdmin(admin.ModelAdmin):
    list_display = ('nome_lotacao', 'id_gestor_imediato', 'id_diretor_responsavel', 'id_lotacao_pai')
    search_fields = ('nome_lotacao',)
    list_filter = ('id_gestor_imediato', 'id_diretor_responsavel')
    
@admin.register(TipoDocumento)
class TipoDocumentoAdmin(admin.ModelAdmin):
    list_display = ('nome_documento', 'requer_aprovacao_gestor', 'requer_aprovacao_diretor')
    list_filter = ('requer_aprovacao_gestor', 'requer_aprovacao_diretor')

@admin.register(Solicitacao)
class SolicitacaoAdmin(admin.ModelAdmin):
    list_display = ('id', '__str__', 'status', 'id_colaborador', 'id_aprovador_atual')
    search_fields = ('id_colaborador__username', 'id_tipo_documento__nome_documento')
    list_filter = ('status', 'id_tipo_documento')

@admin.register(LogAprovacao)
class LogAprovacaoAdmin(admin.ModelAdmin):
    list_display = ('id_solicitacao', 'acao', 'id_ator', 'data_acao')
    list_filter = ('acao',)
    readonly_fields = ('id_solicitacao', 'id_ator', 'acao', 'data_acao', 'detalhes')