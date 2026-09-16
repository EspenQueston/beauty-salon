"""Active l isolation Row-Level Security sur les invitations."""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_invitation")]

    operations = enable_rls("accounts_invitation")
