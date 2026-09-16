"""Resolution hostname -> tenant, mise en cache.

Cette fonction est appelee a chaque requete de mini-site : elle doit etre
tres bon marche. Les resultats negatifs sont caches aussi, sinon un scan de
sous-domaines inexistants deviendrait un flot de requetes SQL.
"""

from django.conf import settings
from django.core.cache import cache

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
        return cached

    tenant_id = (
        Domain.objects.filter(hostname=hostname, active=True)
        .values_list("tenant_id", flat=True)
        .first()
    )

    if tenant_id is None:
        cache.set(key, _MISS, NEGATIVE_CACHE_TTL)
        return None

    tenant_id = str(tenant_id)
    cache.set(key, tenant_id, CACHE_TTL)
    return tenant_id


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
        is_primary=not Domain.objects.using(using).filter(
            tenant=tenant, is_primary=True
        ).exists(),
        active=True,
    )
    domain.save(using=using)
    invalidate_hostname(hostname)
    return domain
