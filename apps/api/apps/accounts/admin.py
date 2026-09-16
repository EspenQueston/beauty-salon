from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm

from .forms import UserChangeForm, UserCreationForm
from .models import Membership, User


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ("tenant",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    change_password_form = AdminPasswordChangeForm
    ordering = ("email",)
    list_display = ("email", "display_name", "is_platform_admin", "is_active", "is_staff")
    list_filter = ("is_platform_admin", "is_active", "is_staff")
    search_fields = ("email", "display_name", "phone")
    inlines = (MembershipInline,)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profil", {"fields": ("display_name", "phone", "locale")}),
        (
            "Droits",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_platform_admin",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    readonly_fields = ("last_login", "created_at", "updated_at")

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "display_name", "password1", "password2"),
            },
        ),
    )


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "status")
    list_filter = ("role", "status")
    search_fields = ("user__email", "tenant__name", "tenant__slug")
    autocomplete_fields = ("tenant", "user")
