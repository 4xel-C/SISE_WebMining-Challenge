"""
agent/ui/home.py — Home window (pygame, dark theme).

Deux modes sélectionnables par toggle :

  Mode de base  → profil utilisateur + capture annotée ou ML-only.
                  Retourne {"mode":"base", "user":str, "activity":str|None, "labelled":bool}

  Mode Sentinel → observation pure, pas de capture, accès à l'interface web.
                  Retourne {"mode":"sentinel", "user":None, "activity":None, "labelled":False}

Retourne None si l'utilisateur ferme / annule.
"""

from __future__ import annotations

from typing import Optional

import pygame

ACTIVITIES = ("coding", "writing", "gaming")
MODES = ("base", "sentinel")

# ── Palette ───────────────────────────────────────────────────────────────────
BG = (13, 17, 23)
CARD = (22, 27, 34)
BORDER = (48, 54, 61)
FG = (201, 209, 217)
FG_DIM = (139, 148, 158)
ACCENT = (88, 166, 255)  # blue  — mode base
SENTINEL = (188, 140, 255)  # purple — mode sentinel
BTN = (31, 111, 235)
BTN_HOV = (56, 139, 253)
BTN_S = (100, 60, 200)  # sentinel confirm
BTN_S_HOV = (130, 85, 230)
INPUT_BG = (33, 38, 45)
RED = (248, 81, 73)
WHITE = (255, 255, 255)

ACTIVITY_COLORS: dict[str, tuple] = {
    "coding": (88, 166, 255),
    "writing": (63, 185, 80),
    "gaming": (210, 168, 255),
}

# ── Geometry ──────────────────────────────────────────────────────────────────
W = 400
PAD = 24
CARD_X = PAD - 2
CARD_W = W - (PAD - 2) * 2
INPUT_H = 34
CHECK_SIZE = 15
RADIO_STEP = 28
BTN_H = 34
BTN_CONFIRM = 130
BTN_CANCEL = 80

_LBL_PADY = 14
_LBL_H = 16
_INPUT_PADY = 4
_SEC_GAP = 18
_TOGGLE_H = 32
_TOGGLE_PAD = 12


# ── Layout helper ─────────────────────────────────────────────────────────────


def _layout(mode: str, labelled: bool) -> dict:
    """Returns absolute Y coordinates and window height for the current state."""
    card_y = 86
    toggle_y = card_y + _TOGGLE_PAD
    content_y = toggle_y + _TOGGLE_H + _TOGGLE_PAD

    if mode == "sentinel":
        desc_top = content_y + 6
        card_bottom = desc_top + 58 + _LBL_PADY
        out = dict(toggle_y=toggle_y, desc_top=desc_top)
    else:
        lbl_user_y = content_y
        input_y = lbl_user_y + _LBL_H + _INPUT_PADY
        check_y = input_y + INPUT_H + _SEC_GAP
        if labelled:
            lbl_act_y = check_y + CHECK_SIZE + _SEC_GAP
            radio_y_base = lbl_act_y + _LBL_H + 6
            card_bottom = radio_y_base + len(ACTIVITIES) * RADIO_STEP + _LBL_PADY
        else:
            lbl_act_y = check_y
            radio_y_base = check_y
            card_bottom = check_y + CHECK_SIZE + _SEC_GAP
        out = dict(
            toggle_y=toggle_y,
            lbl_user_y=lbl_user_y,
            input_y=input_y,
            check_y=check_y,
            lbl_act_y=lbl_act_y,
            radio_y_base=radio_y_base,
        )

    btn_y = card_bottom + 12
    window_h = btn_y + BTN_H + PAD
    out.update(
        card_y=card_y, card_h=card_bottom - card_y, btn_y=btn_y, window_h=window_h
    )
    return out


# ── Drawing helpers ───────────────────────────────────────────────────────────


def _rrect(
    surf: pygame.Surface,
    color: tuple,
    rect,
    radius: int = 6,
    border: int = 0,
    border_color: tuple | None = None,
) -> None:
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, color, r, border_radius=radius)
    if border and border_color:
        pygame.draw.rect(surf, border_color, r, width=border, border_radius=radius)


def _text(surf, s: str, font, color: tuple, x: int, y: int) -> pygame.Rect:
    t = font.render(s, True, color)
    surf.blit(t, (x, y))
    return t.get_rect(topleft=(x, y))


def _text_wrap(
    surf, lines: list[str], font, color: tuple, x: int, y: int, line_h: int
) -> None:
    for i, line in enumerate(lines):
        _text(surf, line, font, color, x, y + i * line_h)


# ── Entry point ───────────────────────────────────────────────────────────────


def ask_profile(
    initial_user: str = "anonymous",
    initial_activity: str = "coding",
    initial_labelled: bool = True,
    initial_mode: str = "base",
) -> Optional[dict]:
    """
    Blocks until the user confirms or closes.
    Returns a profile dict or None.
    """
    import ctypes
    import os

    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

    # DPI-aware → évite le flou sur Windows à 125 %+
    try:
        ctypes.windll.shcore.SetProcessDpiAwarenessContext(-4)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    if not pygame.get_init():
        pygame.init()

    # ── State ─────────────────────────────────────────────────────────────────
    mode = initial_mode if initial_mode in MODES else "base"
    user_text = "" if initial_user == "anonymous" else initial_user
    cursor_pos = len(user_text)
    labelled = initial_labelled
    activity = initial_activity if initial_activity in ACTIVITIES else ACTIVITIES[0]
    input_error = False
    prev_key = (mode, labelled)

    cursor_vis = True
    cursor_ms = 0
    result: dict | None = None
    running = True

    lay = _layout(mode, labelled)
    screen = pygame.display.set_mode((W, lay["window_h"]))
    pygame.display.set_caption("KeySentinel")

    # Icône de la fenêtre
    import pathlib

    _ico = pathlib.Path(__file__).parent.parent / "assets" / "keysentinel.ico"
    if _ico.exists():
        try:
            pygame.display.set_icon(pygame.image.load(str(_ico)))
        except Exception:
            pass

    # ── Fonts ─────────────────────────────────────────────────────────────────
    def _f(sz: int, bold: bool = False) -> pygame.font.Font:
        return pygame.font.SysFont("Segoe UI", sz, bold=bold)

    f_title = _f(16, bold=True)
    f_sub = _f(9)
    f_lbl = _f(9, bold=True)
    f_input = _f(11)
    f_radio = _f(10)
    f_btn = _f(10, bold=True)
    f_check = _f(10)
    f_toggle = _f(9, bold=True)
    f_desc = _f(9)

    pygame.key.set_repeat(400, 40)
    clock = pygame.time.Clock()

    while running:
        dt = clock.tick(60)
        cursor_ms += dt
        if cursor_ms >= 530:
            cursor_vis = not cursor_vis
            cursor_ms = 0

        # Resize if mode or labelled changed (au cas où prev frame l'a changé)
        cur_key = (mode, labelled)
        if cur_key != prev_key:
            lay = _layout(mode, labelled)
            screen = pygame.display.set_mode((W, lay["window_h"]))
            prev_key = cur_key

        # Rects pré-events (pour collision dans les events de ce frame)
        _toggle_y_pre = lay["toggle_y"]
        _btn_y_pre = lay["btn_y"]
        _pw = (CARD_W - 32 - 4) // 2
        _px0 = CARD_X + 16
        pill0 = pygame.Rect(_px0, _toggle_y_pre, _pw, _TOGGLE_H)
        pill1 = pygame.Rect(_px0 + _pw + 4, _toggle_y_pre, _pw, _TOGGLE_H)
        confirm_rect = pygame.Rect(
            W - PAD - BTN_CONFIRM, _btn_y_pre, BTN_CONFIRM, BTN_H
        )
        cancel_rect = pygame.Rect(
            W - PAD - BTN_CONFIRM - BTN_CANCEL - 8, _btn_y_pre, BTN_CANCEL, BTN_H
        )

        mx, my = pygame.mouse.get_pos()

        # ── Events ────────────────────────────────────────────────────────────
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if mode == "sentinel":
                        result = _build_sentinel()
                        running = False
                    elif user_text.strip():
                        result = _build_base(user_text, activity, labelled)
                        running = False
                    else:
                        input_error = True
                elif mode == "base":
                    if ev.key == pygame.K_BACKSPACE:
                        if cursor_pos > 0:
                            user_text = (
                                user_text[: cursor_pos - 1] + user_text[cursor_pos:]
                            )
                            cursor_pos -= 1
                            input_error = False
                    elif ev.key == pygame.K_DELETE:
                        user_text = user_text[:cursor_pos] + user_text[cursor_pos + 1 :]
                    elif ev.key == pygame.K_LEFT:
                        cursor_pos = max(0, cursor_pos - 1)
                    elif ev.key == pygame.K_RIGHT:
                        cursor_pos = min(len(user_text), cursor_pos + 1)
                    elif ev.key == pygame.K_HOME:
                        cursor_pos = 0
                    elif ev.key == pygame.K_END:
                        cursor_pos = len(user_text)

            elif ev.type == pygame.TEXTINPUT and mode == "base":
                user_text = user_text[:cursor_pos] + ev.text + user_text[cursor_pos:]
                cursor_pos += len(ev.text)
                input_error = False
                cursor_vis = True
                cursor_ms = 0

            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                pos = ev.pos

                # Mode toggle pills
                if pill0.collidepoint(pos):
                    mode = "base"
                elif pill1.collidepoint(pos):
                    mode = "sentinel"

                if mode == "base":
                    lay2 = _layout("base", labelled)
                    check_y = lay2["check_y"]
                    check_area = pygame.Rect(
                        CARD_X + 16, check_y, CARD_W - 32, CHECK_SIZE + 6
                    )
                    radio_y_base = lay2["radio_y_base"]

                    if check_area.collidepoint(pos):
                        labelled = not labelled

                    if labelled:
                        for i, act in enumerate(ACTIVITIES):
                            ry = radio_y_base + i * RADIO_STEP
                            row = pygame.Rect(CARD_X + 16, ry, CARD_W - 32, RADIO_STEP)
                            if row.collidepoint(pos):
                                activity = act

                if confirm_rect.collidepoint(pos):
                    if mode == "sentinel":
                        result = _build_sentinel()
                        running = False
                    elif user_text.strip():
                        result = _build_base(user_text, activity, labelled)
                        running = False
                    else:
                        input_error = True
                if cancel_rect.collidepoint(pos):
                    running = False

        # Recalcule lay + rects après events (mode/labelled peuvent avoir changé)
        cur_key = (mode, labelled)
        if cur_key != prev_key:
            lay = _layout(mode, labelled)
            screen = pygame.display.set_mode((W, lay["window_h"]))
            prev_key = cur_key
        else:
            lay = _layout(mode, labelled)

        # Rects frais pour le draw
        card_rect = pygame.Rect(CARD_X, lay["card_y"], CARD_W, lay["card_h"])
        toggle_y = lay["toggle_y"]
        btn_y = lay["btn_y"]
        confirm_rect = pygame.Rect(W - PAD - BTN_CONFIRM, btn_y, BTN_CONFIRM, BTN_H)
        cancel_rect = pygame.Rect(
            W - PAD - BTN_CONFIRM - BTN_CANCEL - 8, btn_y, BTN_CANCEL, BTN_H
        )
        _pw2 = (CARD_W - 32 - 4) // 2
        _px02 = CARD_X + 16
        pill0 = pygame.Rect(_px02, toggle_y, _pw2, _TOGGLE_H)
        pill1 = pygame.Rect(_px02 + _pw2 + 4, toggle_y, _pw2, _TOGGLE_H)
        mx, my = pygame.mouse.get_pos()

        # ── Draw ──────────────────────────────────────────────────────────────
        screen.fill(BG)
        accent = SENTINEL if mode == "sentinel" else ACCENT

        # Header
        _text(screen, "KeySentinel", f_title, accent, PAD, 18)
        sub = (
            "Mode observation — aucune capture."
            if mode == "sentinel"
            else "Configure ton profil de capture."
        )
        _text(screen, sub, f_sub, FG_DIM, PAD, 42)

        # Card
        _rrect(screen, CARD, card_rect, radius=8, border=1, border_color=BORDER)

        # ── Mode toggle ───────────────────────────────────────────────────────
        pill_bg = pygame.Rect(CARD_X + 16, toggle_y, CARD_W - 32, _TOGGLE_H)
        _rrect(screen, INPUT_BG, pill_bg, radius=6, border=1, border_color=BORDER)

        for pill, label, m in [
            (pill0, "Mode de base", "base"),
            (pill1, "Mode Sentinel", "sentinel"),
        ]:
            active = mode == m
            hov = (not active) and pill.collidepoint(mx, my)
            if active:
                bg = BTN_S if m == "sentinel" else BTN
                _rrect(screen, bg, pill, radius=5)
            elif hov:
                _rrect(
                    screen, tuple(min(255, c + 18) for c in INPUT_BG), pill, radius=5
                )
            lc = WHITE if active else (FG if hov else FG_DIM)
            tw, th = f_toggle.size(label)
            _text(
                screen,
                label,
                f_toggle,
                lc,
                pill.centerx - tw // 2,
                pill.centery - th // 2,
            )

        # ── Mode de base ──────────────────────────────────────────────────────
        if mode == "base":
            lbl_user_y = lay["lbl_user_y"]
            input_y = lay["input_y"]
            check_y = lay["check_y"]
            lbl_act_y = lay["lbl_act_y"]
            radio_y_base = lay["radio_y_base"]
            input_rect = pygame.Rect(CARD_X + 16, input_y, CARD_W - 32, INPUT_H)
            check_box = pygame.Rect(CARD_X + 16, check_y, CHECK_SIZE, CHECK_SIZE)

            _text(screen, "UTILISATEUR", f_lbl, FG_DIM, CARD_X + 16, lbl_user_y)
            border_col = RED if input_error else ACCENT
            _rrect(
                screen,
                INPUT_BG,
                input_rect,
                radius=5,
                border=1,
                border_color=border_col,
            )

            avail_w = input_rect.width - 16
            cursor_px = f_input.size(user_text[:cursor_pos])[0]
            text_off = max(0, cursor_px - avail_w)
            text_surf = f_input.render(user_text, True, FG)
            ty = input_rect.y + (INPUT_H - text_surf.get_height()) // 2
            clip = pygame.Rect(input_rect.x + 8, input_rect.y + 1, avail_w, INPUT_H - 2)
            screen.set_clip(clip)
            screen.blit(text_surf, (input_rect.x + 8 - text_off, ty))
            if cursor_vis:
                cx = input_rect.x + 8 + cursor_px - text_off
                pygame.draw.line(
                    screen,
                    FG,
                    (cx, input_rect.y + 6),
                    (cx, input_rect.y + INPUT_H - 6),
                    1,
                )
            screen.set_clip(None)

            check_col = ACCENT if labelled else BORDER
            _rrect(
                screen, INPUT_BG, check_box, radius=3, border=1, border_color=check_col
            )
            if labelled:
                cx2, cy2 = check_box.centerx, check_box.centery
                pygame.draw.lines(
                    screen,
                    ACCENT,
                    False,
                    [(cx2 - 4, cy2), (cx2 - 1, cy2 + 3), (cx2 + 5, cy2 - 4)],
                    2,
                )
            lbl_col = FG if labelled else FG_DIM
            _text(
                screen,
                "Labéliser les données",
                f_check,
                lbl_col,
                check_box.right + 10,
                check_y,
            )

            if labelled:
                _text(screen, "ACTIVITÉ", f_lbl, FG_DIM, CARD_X + 16, lbl_act_y)
                for i, act in enumerate(ACTIVITIES):
                    ry = radio_y_base + i * RADIO_STEP
                    selected = act == activity
                    col = ACTIVITY_COLORS.get(act, FG)
                    hov_row = pygame.Rect(
                        CARD_X + 16, ry, CARD_W - 32, RADIO_STEP - 2
                    ).collidepoint(mx, my)
                    if hov_row and not selected:
                        _rrect(
                            screen,
                            tuple(min(255, c + 10) for c in CARD),
                            (CARD_X + 14, ry - 1, CARD_W - 28, RADIO_STEP - 2),
                            radius=4,
                        )
                    cc = (CARD_X + 16 + 7, ry + RADIO_STEP // 2 - 1)
                    pygame.draw.circle(screen, col if selected else BORDER, cc, 7, 1)
                    if selected:
                        pygame.draw.circle(screen, col, cc, 4)
                    text_col = col if selected else (FG if hov_row else FG_DIM)
                    _text(
                        screen, act.capitalize(), f_radio, text_col, cc[0] + 14, ry + 6
                    )

        # ── Mode Sentinel ─────────────────────────────────────────────────────
        else:
            _text_wrap(
                screen,
                [
                    "Aucun enregistrement. Accède à l'interface web",
                    "pour visualiser les métriques, sessions et",
                    "prédictions ML de tous les utilisateurs.",
                ],
                f_desc,
                FG_DIM,
                CARD_X + 16,
                lay["desc_top"],
                18,
            )

        # ── Buttons ───────────────────────────────────────────────────────────
        cncl_hov = cancel_rect.collidepoint(mx, my)
        cncl_bg = tuple(min(255, c + 20) for c in INPUT_BG) if cncl_hov else INPUT_BG
        _rrect(screen, cncl_bg, cancel_rect, radius=5, border=1, border_color=BORDER)
        cw, ch = f_btn.size("Annuler")
        _text(
            screen,
            "Annuler",
            f_btn,
            FG_DIM,
            cancel_rect.centerx - cw // 2,
            cancel_rect.centery - ch // 2,
        )

        conf_hov = confirm_rect.collidepoint(mx, my)
        if mode == "sentinel":
            conf_bg = BTN_S_HOV if conf_hov else BTN_S
            conf_lbl = "Accéder →"
        else:
            conf_bg = BTN_HOV if conf_hov else BTN
            conf_lbl = "Confirmer →"
        _rrect(screen, conf_bg, confirm_rect, radius=5)
        cw2, ch2 = f_btn.size(conf_lbl)
        _text(
            screen,
            conf_lbl,
            f_btn,
            WHITE,
            confirm_rect.centerx - cw2 // 2,
            confirm_rect.centery - ch2 // 2,
        )

        pygame.display.flip()

    pygame.quit()
    return result


# ── Result builders ───────────────────────────────────────────────────────────


def _build_base(user_text: str, activity: str, labelled: bool) -> dict:
    return {
        "mode": "base",
        "user": user_text.strip(),
        "activity": activity if labelled else None,
        "labelled": labelled,
    }


def _build_sentinel() -> dict:
    return {
        "mode": "sentinel",
        "user": None,
        "activity": None,
        "labelled": False,
    }
