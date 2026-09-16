"""Recettes et depenses : saisie, synthese, export."""

from datetime import date, timedelta

from django.http import HttpResponse
from django.utils.text import slugify
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Membership
from apps.common.viewsets import TenantModelViewSet
from apps.tenants.models import Tenant

from . import services
from .excel import build_workbook
from .models import Transaction

# Les comptes du salon ne regardent pas l'equipe.
#
# Un prestataire voit son agenda, pas la marge du mois ni le loyer. C'est la
# seule partie du produit ou la reception elle-meme est exclue : elle
# encaisse, elle ne tient pas la comptabilite.
OWNERS = (Membership.Role.OWNER, Membership.Role.MANAGER)

# Fenetre par defaut : l'annee glissante. Assez longue pour qu'une courbe
# mensuelle ait une forme, assez courte pour rester rapide.
DEFAULT_WINDOW_DAYS = 365


class TransactionSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(read_only=True)
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    from_booking = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = (
            "id",
            "kind",
            "category",
            "category_label",
            "label",
            "amount",
            "occurred_on",
            "method",
            "method_label",
            "counterparty",
            "note",
            "source",
            "source_label",
            "from_booking",
            "created_at",
        )
        read_only_fields = ("created_at", "source")

    def get_from_booking(self, transaction) -> bool:
        """Dit si la ligne est nee d'un rendez-vous.

        L'ecran s'en sert pour la signaler : une recette automatique se
        corrige, mais la supprimer sans comprendre d'ou elle vient laisserait
        un trou dans la caisse.
        """
        return transaction.booking_id is not None

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        category = attrs.get("category", getattr(self.instance, "category", None))

        if kind and category:
            allowed = (
                Transaction.IncomeCategory
                if kind == Transaction.Kind.INCOME
                else Transaction.ExpenseCategory
            )
            if category not in allowed.values:
                raise serializers.ValidationError(
                    {
                        "category": "Ce poste n'existe pas pour "
                        + ("une recette." if kind == Transaction.Kind.INCOME else "une dépense.")
                    }
                )

        occurred_on = attrs.get("occurred_on")
        if occurred_on and occurred_on > self._today():
            # Une depense future est une prevision, pas un mouvement. La
            # melanger au realise fausserait tous les totaux.
            raise serializers.ValidationError(
                {"occurred_on": "Une date future ne peut pas être enregistrée."}
            )

        return attrs

    def _today(self) -> date:
        """La date du jour **chez le salon**.

        Comparer a `date.today()` revenait a comparer a la date du serveur.
        Un salon a Shanghai saisissant une depense du jour se la voyait
        refuser comme « future » pendant les huit heures ou UTC est encore la
        veille - un message incomprehensible devant une depense bien reelle.
        """
        request = self.context.get("request")
        tenant_id = getattr(request, "tenant_id", None)
        tenant = Tenant.objects.filter(pk=tenant_id).first() if tenant_id else None
        return services.aujourdhui_du_salon(tenant) if tenant else date.today()


class TransactionViewSet(TenantModelViewSet):
    serializer_class = TransactionSerializer
    model = Transaction
    required_roles = OWNERS
    safe_roles = OWNERS

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        start, end = self._window()
        queryset = queryset.filter(occurred_on__gte=start, occurred_on__lte=end)

        if kind := params.get("kind"):
            queryset = queryset.filter(kind=kind)
        if category := params.get("category"):
            queryset = queryset.filter(category=category)
        if search := params.get("search"):
            from django.db.models import Q

            queryset = queryset.filter(
                Q(label__icontains=search) | Q(counterparty__icontains=search)
            )

        return queryset.order_by("-occurred_on", "-created_at")

    def _window(self) -> tuple[date, date]:
        params = self.request.query_params

        # « Aujourd'hui » est celui du salon, pas celui du serveur. Sans cela,
        # une requete sans bornes explicites coupe la journee au mauvais
        # endroit pour tout salon eloigne d'UTC - huit heures de decalage a
        # Shanghai, assez pour que les recettes du jour disparaissent.
        tenant = Tenant.objects.filter(pk=self.request.tenant_id).first()
        today = services.aujourdhui_du_salon(tenant) if tenant else date.today()

        def parse(value, fallback):
            try:
                return date.fromisoformat(value) if value else fallback
            except ValueError:
                return fallback

        start = parse(params.get("from"), today - timedelta(days=DEFAULT_WINDOW_DAYS))
        end = parse(params.get("to"), today)
        return (start, end) if start <= end else (end, start)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Tout ce qu'affiche le tableau de bord, en une reponse.

        Les quatre graphiques et les quatre chiffres d'en-tete viennent d'ici :
        quatre appels separes auraient multiplie par quatre le temps
        d'affichage sur un reseau mobile, pour des donnees qui se calculent
        sur le meme ensemble de lignes.
        """
        tenant = Tenant.objects.get(pk=request.tenant_id)
        queryset = self.get_queryset()
        start, end = self._window()

        expenses = services.by_category(queryset, Transaction.Kind.EXPENSE)
        incomes = services.by_category(queryset, Transaction.Kind.INCOME)

        return Response(
            {
                "currency": tenant.currency,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "totals": services.totals(queryset),
                "monthly": services.monthly(queryset, tenant),
                # La liste complete alimente les barres classees ; la version
                # regroupee alimente l'anneau, qui ne peut pas porter plus de
                # trois teintes lisibles.
                "expense_by_category": expenses,
                "income_by_category": incomes,
                "income_slices": services.top_slices(incomes),
            }
        )

    @action(detail=False, methods=["get"])
    def export(self, request):
        """Classeur Excel : recettes et depenses sur deux feuilles."""
        tenant = Tenant.objects.get(pk=request.tenant_id)
        start, end = self._window()

        content = build_workbook(
            self.get_queryset(), currency=tenant.currency, salon_name=tenant.name
        )

        name = f"comptes-{slugify(tenant.name) or 'salon'}-{start}-{end}.xlsx"
        response = HttpResponse(
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        # Sans cet en-tete, le navigateur ne laisse pas le JavaScript lire le
        # nom du fichier sur une reponse d'un autre hote.
        response["Access-Control-Expose-Headers"] = "Content-Disposition"
        return response
