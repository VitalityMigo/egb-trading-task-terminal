"""
notifier.py — envoi de notifications système.

Priorité : toast natif Windows via `win11toast` (WinRT, Centre de notifications).
Si indisponible (import qui échoue, erreur au runtime, ou OS différent de
Windows), on retombe sur `plyer` (cross-platform), ce qui permet de développer
et tester le même code sur Linux/macOS. En tout dernier recours (aucune des
deux libs disponible), on affiche simplement la notification dans la console
pour ne jamais faire planter l'appelant.

Round 22 : styling Windows rapproché d'un toast "app" moderne (icône ronde +
titre + texte, affichage plus long) façon Teams — voir _win11toast_kwargs
ci-dessous pour ce qui est réellement configurable via win11toast, et ce qui
ne l'est pas (limite honnête, pas de reproduction de l'identité visuelle
Teams elle-même).
"""

from __future__ import annotations

import shutil
import subprocess
import sys

from constants import NOTIFY_APP_NAME, NOTIFY_ICON_FILE


def _win11toast_kwargs() -> dict:
    """Options passées à win11toast.toast() pour un rendu plus "app" que le
    toast nu par défaut (pas d'icône = icône générique Python/console) :
    - icon : logo rond en surimpression (appLogoOverride, hint-crop circle) —
      c'est ce qui donne à un toast Windows son look "carte d'app" (Teams,
      Outlook, etc. font tous ça). Utilise assets/notify_icon.png si présent
      sur le poste ; sinon ce kwarg est simplement omis (win11toast retombe
      sur son comportement par défaut, pas d'erreur).
    - duration : "long" (~25s au lieu de ~5s par défaut) — le temps de lire
      un rappel de tâche sans avoir à rattraper le Centre de notifications.

    Limite honnête (pas de solution simple pour aller plus loin) : le nom
    affiché sous le titre ("Desk CLI" ici, via app_id) et le vrai style de
    carte "application installée" de Windows dépendent d'un AUMID enregistré
    (raccourci Menu Démarrer + activateur COM) — hors de portée d'un simple
    script lancé depuis un venv sans installeur. Sans ça, Windows peut encore
    grouper la notification sous "Python" dans le Centre de notifications
    selon la configuration du poste ; l'icône ronde et la durée longue sont
    ce qui rapproche le plus le rendu d'un toast Teams sans cette étape.
    """
    kwargs: dict = {"duration": "long"}
    if NOTIFY_ICON_FILE.exists():
        kwargs["icon"] = {
            "src": NOTIFY_ICON_FILE.resolve().as_uri(),
            "placement": "appLogoOverride",
            "hint-crop": "circle",
        }
    return kwargs


def send_notification(title: str, message: str) -> bool:
    """Tente d'envoyer une notification système. Retourne True si un des
    mécanismes a réussi, False si on est retombé sur l'affichage console."""
    if sys.platform == "win32":
        try:
            from win11toast import toast  # import paresseux : dépendance optionnelle

            toast(title, message, app_id=NOTIFY_APP_NAME, **_win11toast_kwargs())
            return True
        except Exception:
            pass  # on bascule sur le fallback ci-dessous

    if sys.platform == "darwin":
        # Constat d'Augustin (test sur macOS) : le tout premier envoi via
        # `plyer` déclenche bien la demande d'autorisation système
        # ("Python may send you alerts...", attribuée à "Python Launcher" —
        # l'app fournie par l'installeur python.org, pas à Desk CLI), mais
        # les envois suivants n'affichent plus rien. En cause : le backend
        # macOS de `plyer` (plyer/platforms/macosx/notification.py) utilise
        # `NSUserNotification`, une API dépréciée par Apple depuis macOS 11 —
        # `deliverNotification_` dépend d'un aller-retour XPC avec le démon
        # système `usernoted` que la boucle d'événements d'un simple script
        # Python (sans vraie NSApplication qui la pompe en continu) ne
        # relaie plus de façon fiable après le tout premier appel. C'est une
        # limite connue de `plyer`/`pyobjus` sur les versions récentes de
        # macOS, pas un souci de configuration côté Augustin.
        #
        # On essaie donc en priorité `terminal-notifier`
        # (https://github.com/julienXX/terminal-notifier,
        # `brew install terminal-notifier`) : un petit utilitaire en ligne de
        # commande, lui-même un vrai bundle .app signé, conçu justement pour
        # contourner cette limite de l'API dépréciée. S'il n'est pas
        # installé (poste de dev sans Homebrew, ou lib pas encore posée), on
        # retombe simplement sur `plyer` (peut fonctionner par intermittence)
        # puis sur la console — jamais d'erreur bloquante.
        if shutil.which("terminal-notifier"):
            try:
                subprocess.run(
                    [
                        "terminal-notifier",
                        "-title", title,
                        "-message", message,
                        "-sender", "org.python.python",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
                return True
            except Exception:
                pass  # on bascule sur le fallback plyer ci-dessous

    try:
        from plyer import notification  # import paresseux : dépendance optionnelle

        notification.notify(
            title=title,
            message=message,
            app_name=NOTIFY_APP_NAME,
            timeout=10,
        )
        return True
    except Exception:
        pass

    print(f"[NOTIFICATION] {title} — {message}")
    return False
