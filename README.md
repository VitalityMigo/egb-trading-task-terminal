# Desk CLI

Outil de suivi de tâches et d'adjudications pour desk de trading, en local,
sans dépendance réseau. Une seule interface : `tui/app.py`, style terminal
Bloomberg rétro (Textual).

## Installation (Windows, venv)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Lancement

```powershell
python tui\app.py
```

L'outil n'est pas censé tourner en continu : à chaque ouverture, les statuts
(urgent / fait / prévu) sont recalculés à partir de l'heure actuelle — rien
n'est mis en cache d'une session à l'autre, donc rouvrir après une absence
affiche toujours l'état à jour. Pendant qu'une session reste ouverte, la vue
se rafraîchit aussi automatiquement (horloge chaque seconde, données toutes
les 30s).

Le bandeau garde la marque/date/horloge/compteurs urgent-fait à gauche ; le
navigateur Jour / Semaine est à l'extrême droite ("JOUR ◂ AUJOURD'HUI ▸"). Il
est **global** : la même position (un jour donné, ou la semaine calendaire qui
le contient) s'applique à la fois à la vue Tâches et à la vue Adjudications —
plus de pagination séparée côté Adjudications. `Tab` bascule entre mode Jour
et mode Semaine ; les flèches ◂ / ▸ (ou PgUp/PgDn) reculent/avancent d'un jour
ou d'une semaine. Le navigateur est aussi utilisable **à la souris** : clic
sur JOUR/SEMAINE pour changer de mode, sur ◂/▸ pour avancer/reculer, sur la
date pour revenir à aujourd'hui. La case à cocher **☐ Tout**, juste à côté,
affiche toute la liste (Tâches ou Adjudications, indépendamment l'une de
l'autre) sans filtre de date — pratique pour un coup d'œil d'ensemble. Le
bandeau s'adapte à la largeur du terminal (date masquée, compteurs abrégés,
puis coupe nette plutôt que retour à la ligne en dessous d'un certain seuil).

Après un ajout (tâche ou adjudication), l'app bascule automatiquement le
navigateur sur le jour du nouvel élément et le confirme en bas de l'écran —
pour ne jamais avoir l'impression qu'un ajout "a disparu" alors qu'il est bien
enregistré.

## Notifications

Le suivi des notifications tourne dans un **process séparé**, indépendant de
l'interface (un crash de l'un n'affecte pas l'autre) :

```powershell
python notify_daemon.py
```

ou en double-cliquant sur `start_notify_daemon.bat`. Il vérifie toutes les
30 secondes si une tâche vient d'entrer en zone d'urgence (30 min avant
l'heure prévue, non faite) et déclenche une notification système :

- toast natif du Centre de notifications Windows (`win11toast`) en priorité ;
- repli automatique sur `plyer` (cross-platform) si `win11toast` est
  indisponible — permet de tester le même code sur Linux/macOS pendant le dev ;
- en tout dernier recours, affichage dans la console (aucune des deux libs
  disponible).

Chaque tâche n'est notifiée qu'une fois par jour (déduplication persistée
dans `data/notified.json`, réinitialisée automatiquement au changement de
jour). `Ctrl+C` pour arrêter le daemon.

## Structure du projet

```
desk_cli/
├── constants.py, models.py, storage.py, business_days.py   # fondations
├── task_service.py, auction_service.py                     # logique métier
├── notifier.py, notify_daemon.py, start_notify_daemon.bat   # notifications
├── tui/
│   ├── app.py            # interface (Textual)
│   ├── theme.tcss          # palette ambre/noir façon Bloomberg
│   ├── screens/            # formulaires modaux, confirmations, aide
│   └── widgets/             # bandeau horloge, barre de commande
├── data/                    # tasks.json, auctions.json, notified.json (créés au premier lancement)
└── requirements.txt
```

Toute la logique métier (dates, urgence, génération de tâches depuis une
adjudication) vit dans `task_service.py` / `auction_service.py` /
`business_days.py` — `tui/` n'en duplique aucune ligne.

## Raccourcis

| Touche | Action |
|---|---|
| F1 | Aide / légende des couleurs |
| F2 / F3 | Vue Tâches / Adjudications |
| F4 | Ajouter (ou modifier si une adjudication est sélectionnée) |
| F5 | Marquer fait |
| F6 | Supprimer |
| Tab (ou clic sur JOUR/SEMAINE) | Bascule le navigateur Jour / Semaine (bandeau, global aux 2 vues) |
| ◂ / ▸ (flèches, PgUp/PgDn, ou clic) | Jour ou semaine précédent(e) / suivant(e) |
| Clic sur la date du navigateur | Revient à aujourd'hui |
| Clic sur ☐ Tout (bandeau) | Affiche toute la liste de la vue courante, sans filtre de date |
| Entrée | Actions rapides sur la ligne sélectionnée |
| / | Focus la barre de commande (`TASK ADD`, `TASK DONE 3`, `AUCTION LIST`, `WEEK`, ...) |
| Échap | Ferme un modal / vide la barre de commande |
| F9 | Quitter |

## Colonnes

Tâches : N°, Heure, Tâche, Détails, Statut, **Note**.
Adjudications : N°, Pays, Date, Heure, Type, Instrument, Maturité, Volume (M),
NCO, **Note**.

La Note est un champ libre optionnel, disponible dans les deux formulaires
d'ajout/édition.

## Choix retenus (non explicitement tranchés dans le blueprint)

- **Jour ouvré** = lundi → vendredi, sans calendrier de jours fériés (aucun
  n'a été fourni). Pour en ajouter un plus tard, il suffit de brancher une
  fonction `is_holiday(date)` dans `business_days.py`, sans toucher aux
  appelants.
- **Vue "Semaine"** = semaine calendaire en cours (lundi → dimanche).
- **Heure par défaut** des tâches auto-générées dont la règle n'est pas calée
  sur l'heure de l'adjudication (Bond Definition J-2, Pre-Auction Bills
  Report J-1, Italian Fees le jour même) : `09:00`, modifiable dans
  `constants.AUTO_TASK_DEFAULT_TIME`. Si l'adjudication n'a pas d'heure
  renseignée, les règles calées sur l'heure (+1h Bond Historisation, +2h NCO
  Estimate) sont simplement sautées, avec un message d'avertissement affiché
  à l'écran plutôt qu'une erreur bloquante.

## Dépendances

`textual` (interface, inclut `rich`), `plyer` (notifications de repli),
`win11toast` (toast natif Windows, ne s'installe que sur Windows). Rien
d'autre : pas d'ORM, pas de base de données, pas d'appel réseau.
