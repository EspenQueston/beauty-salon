"""Extensions PostgreSQL requises par le schema.

btree_gist permet de melanger, dans un meme index GiST, des comparaisons
d'egalite sur des colonnes scalaires (tenant_id, staff_member_id) et un
test de chevauchement sur un intervalle. C'est ce qui rend possible la
contrainte anti double-reservation de apps/scheduling/models.py.
"""

from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [BtreeGistExtension()]
