# Calendrier OM 2026-2027 (.ics)

Génère automatiquement un calendrier `.ics` de tous les matchs officiels de l'Olympique de Marseille
pour la saison 2026-2027 (Ligue 1, coupes d'Europe, Coupe de France), avec la chaîne TV française
dans le titre, et le publie sur GitHub Pages.

```
OM - Le Havre · DAZN / Ligue 1+ 3
Lens - OM · DAZN / Ligue 1+
OM - OGC Nice · chaîne à venir
```

## Fonctionnement

| Étape | Détail |
|---|---|
| Matchs et dates | [fixtur.es/en/team/olympique-marseille](https://fixtur.es/en/team/olympique-marseille) (données structurées JSON-LD de la page). Les matchs amicaux sont exclus. |
| Chaîne TV | [footmercato.net/programme-tv/club/om](https://www.footmercato.net/programme-tv/club/om). Le match est rapproché par adversaire et date (± 4 jours). Plusieurs diffuseurs sont séparés par « / ». Si rien n'est encore annoncé : « · chaîne à venir ». |
| Titre et description | `Domicile - Extérieur · Chaîne`, avec compétition, chaîne, stade et score (une fois le match joué) dans la description. |
| Reprogrammation | Chaque match garde le même `UID` (tiré de l'identifiant fixtur.es) pour toute la saison. Quand l'horaire change, `DTSTART` est mis à jour et `SEQUENCE` est incrémenté : votre agenda **déplace** l'événement au lieu d'en créer un second. L'horaire de Foot Mercato est prioritaire, parce qu'il suit les reprogrammations LFP/UEFA. |
| Alerte | `VALARM` 30 minutes avant chaque match dont l'horaire est connu. Un match sans horaire fixé apparaît en « journée entière » avec la mention « Horaire à confirmer ». |
| Robustesse | Si une source est indisponible, on garde les données précédentes (`data/state.json`). Le calendrier n'est jamais vidé et une chaîne déjà connue n'est jamais effacée. |
| Automatisation | GitHub Actions, 2 fois par jour, puis publication sur GitHub Pages. |

Structure :

```
omcal/sources.py      # lecture fixtur.es + Foot Mercato, rapprochement des matchs
omcal/build.py        # construction des événements, gestion UID/SEQUENCE, CLI
omcal/ics.py          # écriture iCalendar (RFC 5545)
data/state.json       # état persistant (UID, séquence, chaînes connues…)
public/om.ics         # le calendrier publié
public/index.html     # page d'accueil avec les boutons d'abonnement
.github/workflows/update-calendar.yml
tests/                # tests pytest (avec extraits HTML des deux sites)
```

## Lancer en local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest -q
python -m omcal            # met à jour data/state.json et public/om.ics
```

---

## Guide pas à pas : dépôt, activation, URL d'abonnement

### 1. Créer le dépôt GitHub

1. Connectez-vous sur [github.com](https://github.com), cliquez sur **+** (en haut à droite) puis **New repository**.
2. Donnez un nom, par exemple `om-calendrier`.
3. Choisissez **Public**. Sur un compte gratuit, GitHub Pages ne fonctionne qu'avec un dépôt public.
4. Ne cochez **pas** « Add a README » : le projet en contient déjà un. Cliquez sur **Create repository**.

> Vous pouvez aussi utiliser un dépôt existant (celui-ci par exemple). Il faut seulement que le code
> se trouve sur la branche **`main`**, parce que GitHub n'exécute les tâches planifiées que sur la
> branche par défaut. Si le code est sur une autre branche, ouvrez une Pull Request vers `main` et
> fusionnez-la.

### 2. Envoyer le code

Depuis le dossier du projet :

```bash
git remote add origin https://github.com/<VOTRE-UTILISATEUR>/om-calendrier.git   # si nécessaire
git branch -M main
git push -u origin main
```

Vous pouvez aussi faire **Add file → Upload files** sur la page du dépôt et glisser-déposer tous
les fichiers. Gardez bien le dossier `.github/workflows/`.

### 3. Activer GitHub Pages

1. Dans le dépôt, ouvrez **Settings** puis **Pages** (menu de gauche).
2. Sous **Build and deployment**, puis **Source**, choisissez **GitHub Actions**.

### 4. Autoriser le workflow à enregistrer ses mises à jour

1. Ouvrez **Settings**, puis **Actions**, puis **General**.
2. Sous **Workflow permissions**, cochez **Read and write permissions**, puis **Save**.
   C'est nécessaire pour que le workflow puisse enregistrer `data/state.json`, qui conserve les identifiants et les chaînes connues.

### 5. Lancer la première exécution

1. Ouvrez l'onglet **Actions**. Si GitHub le demande, cliquez sur **I understand my workflows, go ahead and enable them**.
2. Choisissez **Mise à jour du calendrier OM**, puis **Run workflow** et **Run workflow**.
3. Attendez 1 à 2 minutes que les deux jobs (`build` et `deploy`) soient verts ✅.

Ensuite, le calendrier se met à jour seul **2 fois par jour** : à 7h17 et 19h17, heure de Paris, en
été, et une heure plus tôt en hiver. Vous pouvez relancer à tout moment avec **Run workflow**.

### 6. Récupérer l'URL d'abonnement

L'URL est affichée dans **Settings**, puis **Pages** (« Your site is live at… »), et dans le job
`deploy`. Elle suit ce format :

```
https://<VOTRE-UTILISATEUR>.github.io/<NOM-DU-DÉPÔT>/om.ics
```

Par exemple, pour le dépôt `zwjmw95jg7-create/-b-ne` :
`https://zwjmw95jg7-create.github.io/-b-ne/om.ics`

La page `https://<VOTRE-UTILISATEUR>.github.io/<NOM-DU-DÉPÔT>/` propose des boutons d'abonnement
prêts à l'emploi et un bouton pour copier l'URL.

### 7. S'abonner

- **iPhone / iPad** : **Réglages**, puis **Calendrier**, **Comptes**, **Ajouter un compte**, **Autre**,
  et **Ajouter un calendrier avec abonnement**. Collez l'URL. Vous pouvez aussi toucher le bouton
  « S'abonner » de la page d'accueil.
- **Mac (Calendrier)** : **Fichier**, puis **Nouvel abonnement à un calendrier…**, et collez l'URL.
  Choisissez « Actualiser : toutes les heures ».
- **Google Agenda (web)** : à côté de **Autres agendas**, cliquez sur **+**, puis **À partir de l'URL**,
  collez l'URL et cliquez sur **Ajouter l'agenda**.
  ⚠️ Google ignore les alertes des agendas abonnés et ne rafraîchit l'agenda que toutes les 12 à
  24 h environ. Pour retrouver l'alerte de 30 min, ouvrez les paramètres de l'agenda « OM 2026-2027 »,
  puis **Notifications des événements**, et ajoutez « 30 minutes avant ».
- **Outlook** : **Ajouter un calendrier**, puis **S'abonner à partir du web**, et collez l'URL.

> Abonnez-vous avec l'URL plutôt que d'importer le fichier une seule fois. C'est l'abonnement qui
> permet de recevoir les nouvelles chaînes TV et les changements d'horaire.

## Personnalisation

- **Compétitions** : liste `COMPETITIONS` dans `omcal/build.py`. Ajoutez par exemple
  `("Trophée des Champions", "Trophée des Champions")`.
- **Horaires d'exécution** : ligne `cron` de `.github/workflows/update-calendar.yml` (en UTC).
- **Durée d'un match** : par défaut, celle donnée par fixtur.es (1h45).

## Limites connues

- Les deux sources sont des pages web, pas des API officielles. Si leur structure change, le
  workflow conserve le dernier calendrier valide, affiche un avertissement dans l'onglet Actions,
  et il faudra adapter `omcal/sources.py`.
- Foot Mercato annonce les diffuseurs quelques semaines à l'avance. Les matchs plus lointains
  restent en « chaîne à venir ». Les matchs déjà joués avant la mise en service n'ont pas de
  chaîne.
- Un match supprimé de fixtur.es reste dans le calendrier. On préfère ne rien effacer à cause
  d'une page incomplète.
- GitHub peut désactiver les workflows planifiés d'un dépôt resté 60 jours sans activité. Vous
  recevez alors un e-mail. Dans ce cas, ouvrez **Actions**, puis le workflow, et cliquez sur
  **Enable workflow**.
