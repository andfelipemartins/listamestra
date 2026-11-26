from django.contrib import admin

from .models import BackupTentativa


@admin.register(BackupTentativa)
class BackupTentativaAdmin(admin.ModelAdmin):
    list_display = ("criada_em", "data_backup", "status", "origem", "tamanho_bytes", "caminho")
    list_filter = ("status", "origem", "data_backup")
    search_fields = ("caminho", "mensagem")
    readonly_fields = tuple(field.name for field in BackupTentativa._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
