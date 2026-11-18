from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Acesso à plataforma", {"fields": ("perfil", "empresa")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Acesso à plataforma", {"fields": ("perfil", "empresa")}),
    )
    list_display = ("username", "first_name", "last_name", "email", "perfil", "empresa", "is_staff")
    list_filter = ("perfil", "is_staff", "is_active")
