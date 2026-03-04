"""
Interface d'entraînement Pygame pour l'enregistrement des inputs clavier.

Usage:
    uv run python training_ui.py
"""

import sys
import time

import pygame

from app.models.schema import create_tables
from app.services.pygame_record_service import PygameRecordService

# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────

WIDTH, HEIGHT = 800, 560
FPS = 60

# Durée d'une répétition (secondes)
REPETITION_DURATION = 10

# Phrase à taper à chaque répétition
TRAINING_PHRASE = "the quick brown fox jumps over the lazy dog"

# Couleurs
BG = (18, 18, 28)
SURFACE = (30, 30, 46)
BORDER = (80, 80, 120)
WHITE = (230, 230, 255)
MUTED = (120, 120, 160)
ACCENT = (120, 180, 255)
GREEN = (100, 220, 130)
RED = (220, 100, 100)
YELLOW = (255, 200, 60)
BAR_BG = (50, 50, 75)
BAR_FG = (100, 160, 255)
BAR_DONE = (100, 220, 130)

# ──────────────────────────────────────────────────────────────
# États de l'application
# ──────────────────────────────────────────────────────────────

STATE_HOME = "home"
STATE_RECORDING = "recording"
STATE_REST = "rest"
STATE_DONE = "done"


# ──────────────────────────────────────────────────────────────
# Helpers de rendu
# ──────────────────────────────────────────────────────────────


def draw_rounded_rect(surf, color, rect, radius=12, border=0, border_color=None):
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if border and border_color:
        pygame.draw.rect(surf, border_color, rect, border, border_radius=radius)


def draw_text(surf, text, font, color, cx, cy, align="center"):
    rendered = font.render(text, True, color)
    rect = rendered.get_rect()
    if align == "center":
        rect.center = (cx, cy)
    elif align == "left":
        rect.midleft = (cx, cy)
    elif align == "right":
        rect.midright = (cx, cy)
    surf.blit(rendered, rect)
    return rect


def draw_progress_bar(surf, x, y, w, h, progress, done=False):
    draw_rounded_rect(surf, BAR_BG, (x, y, w, h), radius=h // 2)
    fill_w = int(w * min(progress, 1.0))
    if fill_w > 0:
        color = BAR_DONE if done else BAR_FG
        draw_rounded_rect(surf, color, (x, y, fill_w, h), radius=h // 2)


def draw_phrase(surf, phrase, typed, font_phrase, x, y, max_width):
    """
    Affiche la phrase avec coloration caractère par caractère :
      - vert  : caractère correct
      - rouge : caractère incorrect
      - blanc : non encore tapé
    Revient à la ligne automatiquement.
    """
    char_w = font_phrase.size("a")[0]
    cols = max(1, max_width // char_w)

    cx, cy = x, y
    for i, ch in enumerate(phrase):
        if i < len(typed):
            color = GREEN if typed[i] == ch else RED
        else:
            color = WHITE if i == len(typed) else MUTED

        glyph = font_phrase.render(ch if ch != " " else "·", True, color)
        surf.blit(glyph, (cx, cy))
        cx += char_w
        if (i + 1) % cols == 0:
            cx = x
            cy += font_phrase.get_linesize() + 2


# ──────────────────────────────────────────────────────────────
# Écrans
# ──────────────────────────────────────────────────────────────


def screen_home(
    surf, fonts, username, activity, repetitions, total_reps, cursor_visible
):
    surf.fill(BG)

    # Titre
    draw_text(surf, "KeySentinel", fonts["title"], ACCENT, WIDTH // 2, 70)
    draw_text(surf, "Entraînement clavier", fonts["sub"], MUTED, WIDTH // 2, 110)

    # Panneau de config
    panel = pygame.Rect(80, 150, WIDTH - 160, 260)
    draw_rounded_rect(surf, SURFACE, panel, radius=16, border=1, border_color=BORDER)

    # Champs
    fields = [
        ("Utilisateur", username, 160, 200),
        ("Activité", activity, 160, 270),
        ("Répétitions", str(repetitions), 160, 340),
    ]
    for label, value, lx, ly in fields:
        draw_text(surf, label, fonts["label"], MUTED, lx, ly, align="left")
        field_rect = pygame.Rect(300, ly - 18, 340, 36)
        draw_rounded_rect(surf, BG, field_rect, radius=8, border=1, border_color=BORDER)
        display = value + (
            "|"
            if cursor_visible
            and (
                (label == "Utilisateur" and total_reps == -1)
                or (label == "Activité" and total_reps == -2)
                or (label == "Répétitions" and total_reps == -3)
            )
            else ""
        )
        draw_text(surf, display, fonts["value"], WHITE, 310, ly, align="left")

    draw_text(
        surf,
        "Cliquez sur un champ pour l'éditer, puis appuyez Entrée",
        fonts["hint"],
        MUTED,
        WIDTH // 2,
        390,
    )

    # Bouton Start
    btn = pygame.Rect(WIDTH // 2 - 120, 450, 240, 50)
    can_start = bool(username.strip() and activity.strip() and repetitions > 0)
    btn_color = ACCENT if can_start else BORDER
    draw_rounded_rect(surf, btn_color, btn, radius=10)
    draw_text(
        surf, "▶  Démarrer", fonts["btn"], BG if can_start else MUTED, WIDTH // 2, 475
    )

    return btn, can_start, fields


def screen_recording(surf, fonts, rep, total_reps, elapsed, phrase, typed):
    surf.fill(BG)

    # En-tête
    draw_text(
        surf, f"Répétition {rep} / {total_reps}", fonts["title"], ACCENT, WIDTH // 2, 55
    )

    progress = elapsed / REPETITION_DURATION
    draw_progress_bar(surf, 80, 90, WIDTH - 160, 18, progress)
    remaining = max(0.0, REPETITION_DURATION - elapsed)
    draw_text(surf, f"{remaining:.1f} s", fonts["label"], MUTED, WIDTH // 2, 122)

    # Phrase à taper
    panel = pygame.Rect(60, 150, WIDTH - 120, 220)
    draw_rounded_rect(surf, SURFACE, panel, radius=14, border=1, border_color=BORDER)
    draw_text(surf, "Tapez la phrase :", fonts["label"], MUTED, 80, 175, align="left")
    draw_phrase(surf, phrase, typed, fonts["phrase"], 75, 200, WIDTH - 150)

    # Avancement de la phrase
    correct = sum(1 for i, c in enumerate(typed) if i < len(phrase) and c == phrase[i])
    pct = correct / len(phrase) if phrase else 0
    draw_text(
        surf,
        f"Précision : {int(pct * 100)} %  |  {correct} / {len(phrase)} caractères",
        fonts["hint"],
        MUTED,
        WIDTH // 2,
        390,
    )
    draw_progress_bar(surf, 80, 400, WIDTH - 160, 12, pct, done=True)

    # Barre répétitions globale
    rep_progress = (rep - 1) / total_reps
    draw_progress_bar(surf, 80, 440, WIDTH - 160, 10, rep_progress)
    draw_text(
        surf,
        f"Progression globale : {rep - 1} / {total_reps} répétitions",
        fonts["hint"],
        MUTED,
        WIDTH // 2,
        466,
    )

    draw_text(surf, "Enregistrement en cours…", fonts["hint"], RED, WIDTH // 2, 510)


def screen_rest(surf, fonts, rep, total_reps, elapsed, rest_duration):
    surf.fill(BG)
    draw_text(surf, "Pause", fonts["title"], YELLOW, WIDTH // 2, HEIGHT // 2 - 80)
    draw_text(
        surf,
        f"Répétition {rep - 1} / {total_reps} terminée",
        fonts["sub"],
        MUTED,
        WIDTH // 2,
        HEIGHT // 2 - 30,
    )
    remaining = max(0.0, rest_duration - elapsed)
    draw_text(
        surf,
        f"Prochaine répétition dans {remaining:.1f} s",
        fonts["label"],
        WHITE,
        WIDTH // 2,
        HEIGHT // 2 + 20,
    )
    draw_progress_bar(
        surf, 160, HEIGHT // 2 + 60, WIDTH - 320, 16, elapsed / rest_duration
    )


def screen_done(surf, fonts, total_reps, username):
    surf.fill(BG)
    draw_text(
        surf,
        "Entraînement terminé !",
        fonts["title"],
        GREEN,
        WIDTH // 2,
        HEIGHT // 2 - 80,
    )
    draw_text(
        surf,
        f"{total_reps} répétitions enregistrées pour « {username} »",
        fonts["sub"],
        MUTED,
        WIDTH // 2,
        HEIGHT // 2 - 20,
    )
    draw_text(
        surf,
        "Appuyez sur Échap ou fermez la fenêtre pour quitter.",
        fonts["hint"],
        MUTED,
        WIDTH // 2,
        HEIGHT // 2 + 50,
    )

    btn = pygame.Rect(WIDTH // 2 - 130, HEIGHT // 2 + 110, 260, 50)
    draw_rounded_rect(surf, ACCENT, btn, radius=10)
    draw_text(
        surf, "↩  Nouvel entraînement", fonts["btn"], BG, WIDTH // 2, HEIGHT // 2 + 135
    )
    return btn


# ──────────────────────────────────────────────────────────────
# Boucle principale
# ──────────────────────────────────────────────────────────────


def main():
    pygame.init()
    surf = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("KeySentinel – Entraînement")
    clock = pygame.time.Clock()

    # Polices
    fonts = {
        "title": pygame.font.SysFont("Segoe UI", 36, bold=True),
        "sub": pygame.font.SysFont("Segoe UI", 20),
        "label": pygame.font.SysFont("Segoe UI", 17),
        "value": pygame.font.SysFont("Segoe UI", 17),
        "hint": pygame.font.SysFont("Segoe UI", 14),
        "btn": pygame.font.SysFont("Segoe UI", 18, bold=True),
        "phrase": pygame.font.SysFont("Courier New", 18, bold=True),
    }

    # ── État de l'application ──────────────────────────────────
    state = STATE_HOME

    # Champs du formulaire
    username = ""
    activity = "training"
    rep_input = "12"  # chaîne saisie pour les reps
    active_field = "username"  # "username" | "activity" | "reps"

    # Rects des boutons (mis à jour à chaque frame de rendu, utilisés dans les events)
    btn_start = pygame.Rect(0, 0, 0, 0)
    btn_new = pygame.Rect(0, 0, 0, 0)

    # Session d'entraînement
    total_reps = 0
    current_rep = 0
    rep_start = 0.0
    rest_start = 0.0
    REST_DURATION = 3.0

    service: PygameRecordService | None = None
    typed = ""  # texte tapé pendant la répétition courante

    cursor_timer = 0.0
    cursor_visible = True

    create_tables()

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        cursor_timer += dt
        if cursor_timer >= 0.5:
            cursor_visible = not cursor_visible
            cursor_timer = 0.0

        now = time.time()

        # ── Événements ────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            # Alimentation du service d'enregistrement (seulement en cours de session)
            if state == STATE_RECORDING and service:
                service.feed(event)

            # ── HOME ──────────────────────────────────────────
            if state == STATE_HOME:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    # Zones cliquables des champs
                    if 182 <= my <= 218:
                        active_field = "username"
                    elif 252 <= my <= 288:
                        active_field = "activity"
                    elif 322 <= my <= 358:
                        active_field = "reps"
                    # Bouton Démarrer
                    elif btn_start.collidepoint(mx, my):
                        try:
                            reps = int(rep_input)
                        except ValueError:
                            reps = 0
                        if username.strip() and activity.strip() and reps > 0:
                            total_reps = reps
                            current_rep = 1
                            typed = ""
                            service = PygameRecordService(
                                username=username.strip(),
                                activity_label=activity.strip(),
                            )
                            service.start()
                            rep_start = now
                            state = STATE_RECORDING

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_TAB:
                        cycle = ["username", "activity", "reps"]
                        idx = cycle.index(active_field)
                        active_field = cycle[(idx + 1) % len(cycle)]

                    elif event.key == pygame.K_RETURN:
                        try:
                            reps = int(rep_input)
                        except ValueError:
                            reps = 0
                        if username.strip() and activity.strip() and reps > 0:
                            total_reps = reps
                            current_rep = 1
                            typed = ""
                            service = PygameRecordService(
                                username=username.strip(),
                                activity_label=activity.strip(),
                            )
                            service.start()
                            rep_start = now
                            state = STATE_RECORDING

                    elif event.key == pygame.K_BACKSPACE:
                        if active_field == "username":
                            username = username[:-1]
                        elif active_field == "activity":
                            activity = activity[:-1]
                        elif active_field == "reps":
                            rep_input = rep_input[:-1]

                    elif event.unicode and event.unicode.isprintable():
                        if active_field == "username":
                            username += event.unicode
                        elif active_field == "activity":
                            activity += event.unicode
                        elif active_field == "reps" and event.unicode.isdigit():
                            rep_input += event.unicode

            # ── RECORDING ─────────────────────────────────────
            elif state == STATE_RECORDING:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if service:
                            service.stop()
                            service = None
                        state = STATE_HOME

                    elif event.key == pygame.K_BACKSPACE:
                        typed = typed[:-1]

                    elif event.unicode and event.unicode.isprintable():
                        if len(typed) < len(TRAINING_PHRASE):
                            typed += event.unicode

            # ── REST ──────────────────────────────────────────
            elif state == STATE_REST:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if service:
                        service.stop()
                        service = None
                    state = STATE_HOME

            # ── DONE ──────────────────────────────────────────
            elif state == STATE_DONE:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if btn_new.collidepoint(event.pos):
                        state = STATE_HOME

        # ── Transitions temporelles ───────────────────────────
        if state == STATE_RECORDING:
            elapsed = now - rep_start
            if elapsed >= REPETITION_DURATION:
                if current_rep >= total_reps:
                    if service:
                        service.stop()
                        service = None
                    state = STATE_DONE
                else:
                    # Stopper la session courante, démarrer la pause
                    if service:
                        service.stop()
                        service = None
                    rest_start = now
                    current_rep += 1
                    state = STATE_REST

        elif state == STATE_REST:
            elapsed_rest = now - rest_start
            if elapsed_rest >= REST_DURATION:
                typed = ""
                service = PygameRecordService(
                    username=username.strip(),
                    activity_label=activity.strip(),
                )
                service.start()
                rep_start = now
                state = STATE_RECORDING

        # ── Rendu ─────────────────────────────────────────────
        if state == STATE_HOME:
            try:
                reps_val = int(rep_input)
            except ValueError:
                reps_val = 0

            field_flag = {"username": -1, "activity": -2, "reps": -3}[active_field]

            btn_start, _, _ = screen_home(
                surf,
                fonts,
                username,
                activity,
                reps_val,
                field_flag,
                cursor_visible,
            )

        elif state == STATE_RECORDING:
            elapsed = now - rep_start
            screen_recording(
                surf,
                fonts,
                current_rep,
                total_reps,
                elapsed,
                TRAINING_PHRASE,
                typed,
            )

        elif state == STATE_REST:
            elapsed_rest = now - rest_start
            screen_rest(
                surf, fonts, current_rep, total_reps, elapsed_rest, REST_DURATION
            )

        elif state == STATE_DONE:
            btn_new = screen_done(surf, fonts, total_reps, username)

        pygame.display.flip()

    if service:
        service.stop()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
