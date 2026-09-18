"""Les images qui ont un emploi, et n'ont donc rien a faire dans la galerie.

---------------------------------------------------------------------------
Le probleme, et pourquoi il est revenu trois fois
---------------------------------------------------------------------------

Tout ce qui se televersait depuis le panneau atterrissait dans la meme
reserve avec `kind = gallery` : le selecteur de medias est partage, et aucun
ecran ne disait au serveur a quoi l'image allait servir.

Un logo, une banniere, un QR code de paiement, la photo d'un article : chacun
finissait par s'afficher au milieu des coiffures du salon. Le logo d'abord,
les QR codes WeChat et Alipay ensuite - puis une troisieme fois, sur des QR
codes televerses et **jamais rattaches** a un moyen de paiement, que ce
fichier-ci ne pouvait pas voir.

---------------------------------------------------------------------------
Deux barrieres, et il en faut deux
---------------------------------------------------------------------------

**Le genre, pose au televersement.** C'est la barriere principale depuis que
chaque ecran declare ce qu'il fait : un QR part en `payment`, une preuve de
versement en `proof`, une photo d'article en `product`. Une image jamais
rattachee est donc ecartee comme les autres - c'est ce qui manquait.

**L'emploi reel, lu ici.** Elle rattrape le cas inverse : une image rangee
dans la galerie, puis choisie comme logo ou comme banniere. On ne liste pas
les emplois, on demande a Django **qui pointe vers MediaAsset** : toute cle
etrangere vers ce modele - presente ou future, declaree n'importe ou - est
trouvee automatiquement.

`include_hidden=True` est necessaire : ces relations sont declarees avec
`related_name="+"`, ce qui les rend invisibles aux parcours habituels. C'est
justement ce qui les avait fait oublier.

Cette seconde exclusion reste faite **a la lecture**, pas en changeant le
`kind` : retirer une photo de galerie de son role de banniere la rend a la
galerie, ce qui est le comportement attendu.
"""

from __future__ import annotations

from django.apps import apps

# Les preuves de versement portent desormais leur propre genre (`proof`) et
# ne sont donc jamais candidates a la galerie. Les interroger ici n'apporterait
# rien - et sur un salon qui tourne depuis deux ans, cette table est la plus
# grosse de toute la liste.
_IGNORED = {("payments", "DepositProof", "image")}


def reserved_media_ids() -> set:
    """Identifiants des medias employes ailleurs que dans la galerie.

    Une requete par modele referencant, sur des tables qui comptent quelques
    lignes par salon. Le tout reste borne au tenant courant par les
    politiques RLS, comme n'importe quelle autre lecture.
    """
    media_model = apps.get_model("media", "MediaAsset")
    taken: set = set()

    for relation in media_model._meta.get_fields(include_hidden=True):
        if not relation.is_relation or not relation.auto_created:
            continue

        source = relation.related_model
        field = relation.field.name

        if source is None or source is media_model:
            continue
        if (source._meta.app_label, source.__name__, field) in _IGNORED:
            continue

        taken.update(
            source.objects.filter(**{f"{field}__isnull": False})
            .values_list(f"{field}_id", flat=True)
        )

    return taken


def duplicate_media_ids(assets) -> set:
    """Les seconds exemplaires d'un meme fichier televerse plusieurs fois.

    -----------------------------------------------------------------------
    Pourquoi c'est un defaut a part entiere
    -----------------------------------------------------------------------

    Le selecteur de medias televerse a chaque choix : essayer deux fichiers,
    ou remplacer un QR code par un autre, laisse dans la reserve autant de
    copies que d'essais. La galerie les affichait toutes - la meme photo
    deux fois de suite dans une mosaique de realisations se lit comme un bug,
    et c'en est un.

    -----------------------------------------------------------------------
    Comment deux copies se reconnaissent
    -----------------------------------------------------------------------

    Meme nom de fichier d'origine **et** meme poids exact. Deux photos
    differentes ne partagent pas les deux : le nom vient du fichier choisi
    par le salon, le poids de son contenu. C'est le meme critere qu'un
    explorateur de fichiers propose pour trouver les doublons, et il ne
    demande pas de relire les octets.

    Le premier exemplaire **dans l'ordre d'affichage** est conserve, les
    suivants sortent. C'est l'ordre ou le salon les verrait, pas celui ou il
    les a televerses : deux copies rangees a la meme position se departagent
    donc a la date, et laquelle des deux survit n'a aucune importance -
    elles portent le meme fichier.

    L'appelant range la liste avant de l'appeler, et passe en tete les medias
    deja employes ailleurs : c'est ce qui permet d'ecarter la seconde copie
    d'un QR code dont la premiere sert reellement de moyen de paiement.
    """
    seen: dict[tuple[str, int], object] = {}
    extra: set = set()

    for asset in assets:
        # Le nom d'origine, sans le dossier propre a chaque media : le chemin
        # contient l'identifiant de l'asset, donc deux copies n'y sont jamais
        # egales.
        empreinte = (asset.file.name.rsplit("/", 1)[-1], asset.byte_size)
        if empreinte in seen:
            extra.add(asset.id)
        else:
            seen[empreinte] = asset.id

    return extra
