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

Le bandeau garde la marque/date/horloge/compteurs à faire-urgent à gauche ; le
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

Depuis le round 22, le suivi des notifications tourne **dans le même
process** que l'interface (plus de daemon séparé à lancer à côté) : dès que
le dashboard est ouvert, un contrôle tourne en tâche de fond toutes les
2 minutes (`constants.NOTIFY_CHECK_INTERVAL_SECONDS`), plus un contrôle
immédiat à chaque lancement. Trois types de notifications :

- **par tâche** : dès qu'une tâche entre en zone d'urgence (30 min avant
  l'heure prévue, non faite) ;
- **récapitulatif général**, deux fois par jour (8h45 et 15h00,
  `constants.GENERAL_NOTIFICATION_TIMES`) : nombre de tâches du jour pas
  encore faites ("X tâches restantes aujourd'hui") ;
- **test**, à la demande — `F8` (round 23 : déplacé de `F10`, la barre de
  commande ayant été retirée) — pratique pour vérifier que les notifications
  système fonctionnent sur le poste, sans attendre qu'une vraie tâche
  devienne urgente.

Mécanisme d'envoi (`notifier.py`) :

- toast natif du Centre de notifications Windows (`win11toast`) en priorité,
  avec une icône ronde (`assets/notify_icon.png`) et un affichage plus long,
  pour se rapprocher visuellement d'un toast d'application moderne (dans
  l'esprit d'un toast Teams, sans reproduire son identité visuelle) ;
- sur macOS, `terminal-notifier` en priorité si installé
  (`brew install terminal-notifier`) — contourne un défaut connu de l'API
  macOS utilisée par `plyer` (`NSUserNotification`, dépréciée par Apple) :
  celle-ci demande bien l'autorisation système au premier envoi (attribuée à
  "Python Launcher"), mais reste ensuite silencieuse sur les envois
  suivants. Sans `terminal-notifier`, repli sur `plyer` (peut fonctionner par
  intermittence sur macOS pour cette raison — nécessite en plus la
  dépendance optionnelle `pyobjus`, non installée par défaut) ;
- repli automatique sur `plyer` (cross-platform) si `win11toast` est
  indisponible, ou en dernier recours sur macOS — permet de tester le même
  code sur Linux/macOS pendant le dev ;
- en tout dernier recours, affichage dans la console (aucun des mécanismes
  ci-dessus disponible).

Chaque tâche/récapitulatif n'est notifié qu'une fois par jour (déduplication
persistée dans `data/notified.json`, réinitialisée automatiquement au
changement de jour). Chaque notification réellement envoyée est aussi
journalisée (`data/notifications_log.json`) et consultable dans l'app via la
troisième page **Log** (`F7`), qui affiche celles reçues **aujourd'hui**.

## Structure du projet

```
desk_cli/
├── constants.py, models.py, storage.py, business_days.py   # fondations
├── task_service.py, auction_service.py                     # logique métier
├── notifier.py, notification_service.py                    # notifications
├── assets/notify_icon.png                                   # icône toast Windows
├── tui/
│   ├── app.py            # interface (Textual)
│   ├── theme.tcss          # palette ambre/noir façon Bloomberg
│   ├── screens/            # formulaires modaux, confirmations, log
│   │                         # (help.py : code mort depuis le round 23, F1
│   │                         # ne pointe plus dessus — laissé sur le disque)
│   └── widgets/             # bandeau horloge
│                             # (command_bar.py : code mort depuis le round 23,
│                             # la barre de commande "/" a été retirée — idem)
├── data/                    # tasks.json, auctions.json, notified.json, notifications_log.json (créés au premier lancement)
└── requirements.txt
```

Toute la logique métier (dates, urgence, génération de tâches depuis une
adjudication, notifications) vit dans `task_service.py` / `auction_service.py`
/ `business_days.py` / `notification_service.py` — `tui/` n'en duplique
aucune ligne.

## Raccourcis

Depuis le round 23, plus de barre de commande (`/`) ni d'aide (`F1`) — tout
ce qu'elles apportaient a un équivalent clavier direct listé ci-dessous.
Navigation ligne par ligne dans les tableaux (Tâches/Adjudications) avec les
flèches ↑ / ↓ (natif Textual) : `F5`/`F6` agissent sur la ligne où se trouve
le curseur, pas toujours la première.

| Touche | Action |
|---|---|
| F1 / F2 / F3 | Vue Tâches / Adjudications / Log (notifications du jour) |
| ↑ / ↓ | Déplace le curseur ligne par ligne dans le tableau (Tâches/Adjudications) |
| F4 | Ajouter (ou modifier si une adjudication est sélectionnée) |
| F5 | Bascule fait / pas fait sur la ligne sélectionnée (tâches) — dans les deux sens |
| F6 | Supprimer la ligne sélectionnée |
| F7 | Actualise l'affichage immédiatement (sans attendre le rafraîchissement automatique toutes les 30s) |
| F8 | Envoie une notification de test |
| Tab (ou clic sur JOUR/SEMAINE) | Bascule le navigateur Jour / Semaine (bandeau, global Tâches/Adjudications) |
| ◂ / ▸ (flèches gauche/droite, PgUp/PgDn, ou clic) | Jour ou semaine précédent(e) / suivant(e) |
| Clic sur la date du navigateur | Revient à aujourd'hui |
| Clic sur ☐ Tout (bandeau) | Affiche toute la liste de la vue courante, sans filtre de date |
| Entrée | Actions rapides sur la ligne sélectionnée |
| Échap | Ferme un modal |
| F9 | Quitter |

## Colonnes

Tâches : N°, **Date**, Heure, Tâche, Détails, Statut, **Note**.
Adjudications : N°, **Date**, Heure, Pays, Type, Maturité, Volume (M),
NCO, **Note**.
Log : N°, Heure, Type (Urgent / Général / Test), Titre, Message.

La colonne **Date** (format `JJ/MM`, sans année — round 23) aide à se
repérer quand le navigateur est en mode Semaine ou sur ☐ Tout (plusieurs
jours affichés à la fois dans la même liste).

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
