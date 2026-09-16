# Sécurité

Ce document dit trois choses : ce qui protège les données d'un salon
aujourd'hui, ce qu'il faut régler avant une mise en ligne, et ce qui reste
ouvert. Il est écrit pour être relu avant chaque déploiement, pas une fois.

Le produit garde le fichier clientes de plusieurs salons dans **une seule
base de données**. C'est ce qui rend la question sérieuse : une erreur ne fuit
pas les données d'un commerce, elle fuit celles de tous.

---

## 1. Ce qui est en place

### Isolation entre salons — deux verrous, pas un

| Couche | Mécanisme | Ce qu'elle rattrape |
|---|---|---|
| Applicative | `TenantManager` filtre sur le salon du contexte courant | Une requête qui oublie son `WHERE` |
| Base | PostgreSQL Row-Level Security, `FORCE ROW LEVEL SECURITY` | Une requête qui contourne le manager |

Deux rôles PostgreSQL pour une seule base : `salon_app` (`NOBYPASSRLS`) porte
tout le trafic métier, `salon_admin` (`BYPASSRLS`) ne sert qu'aux migrations
et à l'administration plateforme.

Sans `app.tenant_id` posé, les politiques ne laissent passer **aucune ligne** —
un oubli de contexte produit une page vide, jamais les données du voisin.
`tests/test_rls.py` vérifie qu'aucun modèle rattaché à un salon n'existe sans
sa politique : ajouter un modèle sans sa migration RLS fait échouer la suite.

### Authentification

- Session Django sur cookie `HttpOnly`, jamais de jeton en `localStorage`.
- Mot de passe : 10 caractères minimum, plus les validateurs Django
  (similarité, mots courants, tout-numérique).
- **Double authentification obligatoire** pour les comptes plateforme
  (`PLATFORM_ADMIN_MFA_REQUIRED`). Un tel compte ouvre l'alias qui contourne
  les politiques RLS : un mot de passe seul n'y suffit jamais.
- Réponse identique que le compte existe ou non sur la réinitialisation, pour
  que le formulaire ne devienne pas un annuaire des adresses inscrites.

### Bornes sur les routes publiques

Tout ce qui s'écrit sans être connecté est limité par `ScopedRateThrottle` :

| Portée | Limite |
|---|---|
| `login` | 10 / min |
| `signup`, `password_reset` | 5 / h |
| `booking_create` | 10 / h |
| `waitlist_create` | 20 / h |
| `deposit_proof` | 30 / h |
| `public_read` | 120 / min |

### Jetons signés

Paiement, changement de statut, arrivée et invitation à laisser un avis
passent par `django.core.signing` avec un **sel distinct par usage** : un
jeton de paiement ne peut pas être rejoué sur une autre route.

### Import d'images par URL

`apps/media/fetch.py` refuse tout ce qui ne doit pas être atteint depuis le
réseau interne : schémas autres que `http`/`https`, et toute adresse dont la
résolution DNS ne tombe pas dans une plage **globale** — ce qui couvre d'un
coup la boucle locale, les plages privées et `169.254.169.254`, l'adresse des
métadonnées cloud. Les redirections ne sont pas suivies automatiquement :
chaque saut est revalidé, sinon seule la première adresse serait contrôlée.

### En-têtes de réponse (Next.js)

`Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options:
nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, et une
`Permissions-Policy` qui **laisse la caméra** — le scan du QR d'arrivée en
dépend — et ferme le reste.

### Ce qui n'est exposé qu'en développement

Le schéma OpenAPI, la page `/api/docs` et le service des fichiers média par
Django. En production, rien de tout cela n'est monté.

---

## 2. Avant toute mise en ligne

### Les trois variables qui comptent

```bash
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")
PLATFORM_DOMAIN=mon-domaine.com
```

`config.settings.production` **refuse de démarrer** si la clé est absente,
trop courte, ou restée à la valeur de développement. C'est délibéré : un
déploiement qui ne démarre pas se voit, une clé de développement en
production, non.

La clé ne signe pas que les sessions. Les liens de réinitialisation, les
jetons de paiement, les codes d'arrivée et les invitations à laisser un avis
en dérivent tous. **Qui la connaît les forge tous, pour tous les salons.**

### Vérifier

```bash
uv run python manage.py check --deploy
```

Aucun avertissement `security.*` ne doit rester, à l'exception de `W021`
(inscription HSTS preload), qui est volontairement laissée au choix.

```bash
uv run pytest tests/test_securite_deploiement.py
```

Ces douze tests chargent le module de production comme le ferait un
déploiement et vérifient ce qu'il produit. Un drapeau qui repasse à `False`
les fait échouer avant la mise en ligne, pas après.

### Le reste de la liste

- [ ] `DATABASE_URL` pointe sur `salon_app`, **jamais** sur `salon_admin`.
- [ ] Les deux rôles PostgreSQL ont des mots de passe distincts et non
      triviaux (`infra/postgres/init/01-roles.sql` en donne la forme).
- [ ] Le reverse proxy pose `X-Forwarded-Proto` et l'écrase systématiquement.
      Sans cela, `SECURE_PROXY_SSL_HEADER` devient falsifiable par l'appelant.
- [ ] Redis n'est pas joignable depuis l'extérieur. Il porte les sessions.
- [ ] Sauvegardes chiffrées, et une restauration réellement testée.
- [ ] `SECURE_HSTS_PRELOAD` reste à `False` tant que le certificat n'a pas été
      vérifié sur **tous** les sous-domaines : l'inscription sur la liste des
      navigateurs est irréversible pendant des mois.
- [ ] `ADMIN_PATH` changé pour autre chose que `admin/` — pas une protection,
      une façon de ne pas figurer dans les balayages automatisés.

---

## 3. Ce qui reste ouvert

Écrit ici parce qu'un risque connu et noté vaut mieux qu'un risque oublié.

### Les preuves de versement sont protégées par l'adresse seule

Une capture de paiement porte le nom de la cliente et parfois son solde
bancaire. Elle est rangée en `visibility=private` et en `kind=proof`, ce qui
la tient hors de la vitrine et hors de la médiathèque du salon — mais le
fichier lui-même est servi à une adresse publique :

```
/media/tenants/<uuid-salon>/media/<uuid-media>/<nom-du-fichier>
```

Deux UUID v4 font environ 244 bits : l'adresse n'est pas devinable. Elle peut
en revanche **fuir** — par un `Referer`, un journal de proxy, un partage.

*Correction à prévoir* : une route authentifiée qui sert les médias privés
après vérification du membership, et un stockage hors de la racine web (ou des
URL signées à durée limitée si l'on passe à un stockage objet). Le champ
`visibility` existe déjà ; il ne lui manque que le contrôle à la lecture.

### Le type d'un fichier téléversé est déclaré par le navigateur

`validate_file` s'appuie sur le type MIME annoncé. Le contenu réel n'est
ouvert qu'ensuite, à la génération des dérivées. Un fichier au type menteur
est donc écrit sur disque avant d'être écarté. La conséquence est bornée —
`X-Content-Type-Options: nosniff` empêche le navigateur de réinterpréter une
image comme une page — mais la vérification par signature (« magic bytes ») au
moment du téléversement serait plus juste.

### Rebinding DNS sur l'import d'images

`_guard` résout le nom, vérifie l'adresse, puis `urllib` ouvre la connexion et
résout une seconde fois. Entre les deux, un serveur DNS hostile peut changer
sa réponse. La fenêtre est étroite et l'exploitation demande de contrôler la
zone DNS ; la correction propre consiste à se connecter à l'adresse IP
vérifiée plutôt qu'au nom.

### La politique de contenu accepte `'unsafe-inline'` sur les scripts

Deux scripts en ligne sont indispensables : celui qui pose le thème
clair/sombre avant le premier pixel, et ceux que Next injecte pour
l'hydratation. Les supprimer demanderait un nonce par requête, donc un
middleware qui rend chaque page dynamique. Le gain serait faible tant qu'aucun
HTML de tiers n'est rendu — et il n'y en a aucun : tout texte saisi par un
salon passe par React, qui l'échappe. `frame-ancestors`, `base-uri`,
`form-action` et `object-src`, eux, sont bien fermés.

---

## 4. Signaler une faille

Écrire à l'adresse de contact de la plateforme, sans ouvrir d'issue publique.
Merci d'y joindre de quoi reproduire : c'est ce qui sépare un rapport d'une
inquiétude.
