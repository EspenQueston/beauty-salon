"""Resolution hostname -> tenant, mise en cache.

Cette fonction est appelee a chaque requete de mini-site : elle doit etre
tres bon marche. Les resultats negatifs sont caches aussi, sinon un scan de
sous-domaines inexistants deviendrait un flot de requetes SQL.
"""

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

from .models import Domain

CACHE_TTL = 300
NEGATIVE_CACHE_TTL = 60
_MISS = "__miss__"


def _cache_key(hostname: str) -> str:
    return f"domain:tenant:{hostname}"


def resolve_tenant_id(hostname: str) -> str | None:
    hostname = hostname.strip().lower()
    if not hostname:
        return None

    key = _cache_key(hostname)
    cached = cache.get(key)
    if cached == _MISS:
        return None
    if cached:
        return _ouvrir(cached)

    # Un domaine personnalise n'est routable qu'une fois verifie : une ligne
    # saisie a la main sans preuve ne fait arriver aucun trafic.
    ligne = (
        Domain.objects.filter(hostname=hostname, active=True)
        .filter(Q(kind=Domain.Kind.PLATFORM_SUBDOMAIN) | Q(verified_at__isnull=False))
        .values_list("tenant_id", "kind")
        .first()
    )

    if ligne is None:
        cache.set(key, _MISS, NEGATIVE_CACHE_TTL)
        return None

    tenant_id, kind = str(ligne[0]), ligne[1]
    valeur = f"{_PERSO}{tenant_id}" if kind == Domain.Kind.CUSTOM_DOMAIN else tenant_id
    cache.set(key, valeur, CACHE_TTL)
    return _ouvrir(valeur)


_PERSO = "perso:"


def _ouvrir(valeur: str) -> str | None:
    """Le salon d'une entree de cache — sauf domaine personnalise en pause.

    Le droit (offre Pro, fonction ouverte) se relit a part, avec son propre
    cache court : une descente ou une coupure prend effet en deux minutes,
    sans attendre l'expiration de la resolution.
    """
    if not valeur.startswith(_PERSO):
        return valeur
    tenant_id = valeur[len(_PERSO) :]
    from .personnalises import domaine_perso_ouvert

    return tenant_id if domaine_perso_ouvert(tenant_id) else None


def invalidate_hostname(hostname: str) -> None:
    cache.delete(_cache_key(hostname.strip().lower()))


def platform_hostname(slug: str) -> str:
    return f"{slug}.{settings.PLATFORM_DOMAIN}"


def ensure_platform_domain(tenant, *, using: str = "default") -> Domain:
    """Cree (ou retrouve) le sous-domaine plateforme d'un salon."""
    hostname = platform_hostname(tenant.slug)
    domain = Domain.objects.using(using).filter(hostname=hostname).first()
    if domain is not None:
        return domain

    domain = Domain(
        tenant=tenant,
        hostname=hostname,
        kind=Domain.Kind.PLATFORM_SUBDOMAIN,
        is_primary=not Domain.objects.using(using).filter(tenant=tenant, is_primary=True).exists(),
        active=True,
    )
    domain.save(using=using)
    invalidate_hostname(hostname)
    return domain
