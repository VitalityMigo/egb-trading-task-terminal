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

# Diagnostic du dernier appel à send_notification() : liste de
# (mécanisme, erreur ou None) dans l'ordre où ils ont été essayés — lue par
# tui/app.py après un "NOTIF TEST"/F10 pour l'afficher dans le toast
# *interne* de l'app (Textual `self.notify()`), qui lui s'affiche toujours à
# l'écran quel que soit l'état des notifications système. Utile pour
# diagnostiquer à distance (ex. retour d'Augustin "ça ne marche toujours pas"
# sans plus de détail) sans dépendre de la console, invisible pendant qu'une
# TUI Textual tourne (écran alternatif du terminal). Réinitialisée à chaque
# appel de send_notification().
last_attempt_log: list[tuple[str, str | None]] = []


def _record_attempt(mechanism: str, error: BaseException | None = None) -> None:
    detail = f"{type(error).__name__}: {error}" if error else None
    last_attempt_log.append((mechanism, detail))


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
    last_attempt_log.clear()

    if sys.platform == "win32":
        try:
            from win11toast import toast  # import paresseux : dépendance optionnelle

            toast(title, message, app_id=NOTIFY_APP_NAME, **_win11toast_kwargs())
            _record_attempt("win11toast")
            return True
        except Exception as exc:
            _record_attempt("win11toast", exc)  # on bascule sur le fallback ci-dessous

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
                # Pas de `-sender` : ce paramètre demande à terminal-notifier
                # d'emprunter l'icône d'un bundle applicatif précis (ex.
                # "org.python.python"), qui peut ne pas exister/être valide
                # sur le poste — source d'échec silencieuse inutile ici,
                # l'icône par défaut de terminal-notifier suffit.
                result = subprocess.run(
                    [
                        "terminal-notifier",
                        "-title", title,
                        "-message", message,
                    ],
                    capture_output=True,
                    timeout=5,
                    text=True,
                )
                if result.returncode == 0:
                    _record_attempt("terminal-notifier")
                    return True
                _record_attempt(
                    "terminal-notifier",
                    RuntimeError(
                        f"code retour {result.returncode} : "
                        f"{(result.stderr or result.stdout or '(aucun détail)').strip()}"
                    ),
                )
            except Exception as exc:
                _record_attempt("terminal-notifier", exc)
                # on bascule sur le fallback plyer ci-dessous

    try:
        from plyer import notification  # import paresseux : dépendance optionnelle

        notification.notify(
            title=title,
            message=message,
            app_name=NOTIFY_APP_NAME,
            timeout=10,
        )
        _record_attempt("plyer")
        return True
    except Exception as exc:
        _record_attempt("plyer", exc)

    print(f"[NOTIFICATION] {title} — {message}")
    return False
