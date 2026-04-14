"""Rules for WhatsApp funnel stages (no LLM) — shared by Postgres and SQLite paths."""

from __future__ import annotations

import re

# Whole message is basically trip length only (still collecting budget/pax).
_DURATION_ONLY = re.compile(
    r"^\s*("
    r"\d{1,2}\s*n/\d{1,2}\s*n"
    r"|\d{1,2}\s*n\b"
    r"|\d{1,2}\s*(?:night|nights|din|day|days)"
    r")\s*$",
    re.I,
)

# Inbound interactive: trip-length picks (not enough for proposal stage).
DURATION_BUTTON_IDS: frozenset[str] = frozenset(
    {"wm_dur_short", "wm_dur_mid", "wm_dur_long"}
)
# Budget band picks → advance to proposal.
BUDGET_BUTTON_IDS: frozenset[str] = frozenset(
    {"wm_bdg_u15", "wm_bdg_1530", "wm_bdg_30p"}
)

# WhatsApp interactive body + buttons (reply title max 20 chars).
TRIP_LENGTH_BODY = (
    "Got it \U0001f44d Varanasi circuit ke liye plan set karte hain. "
    "Pehle trip length chuno:"
)
TRIP_REPLY_BUTTONS: list[tuple[str, str]] = [
    ("wm_dur_short", "2N/3N"),
    ("wm_dur_mid", "3N/4N"),
    ("wm_dur_long", "5N+"),
]

BUDGET_ASK_BODY = (
    "Theek hai \U0001f60a Approx budget range chuno (per person / total baad mein fine-tune):"
)
BUDGET_REPLY_BUTTONS: list[tuple[str, str]] = [
    ("wm_bdg_u15", "Under 15k"),
    ("wm_bdg_1530", "15k - 30k"),
    ("wm_bdg_30p", "30k+"),
]


def qualification_satisfied(text: str, button_id: str | None = None) -> bool:
    """True when user likely answered budget / group size, not only nights."""
    if button_id:
        bid = button_id.strip()
        if bid in BUDGET_BUTTON_IDS:
            return True
        if bid in DURATION_BUTTON_IDS:
            return False

    t = (text or "").strip()
    if not t:
        return False
    if _DURATION_ONLY.match(t):
        return False
    tl = t.lower()
    if "\u20b9" in t:
        return True
    if re.search(r"\d", tl):
        return True
    if re.search(
        r"\b(log|logo|aadmi|jan|people|persons?|pax|budget|rupee|rs\.?)\b",
        tl,
    ):
        return True
    return False


PROPOSAL_REPLY = (
    "Perfect \U0001f44d Varanasi circuit ke liye yeh base flow suggest karta hoon:\n\n"
    "• Day 1: Ganga ghats + evening Ganga Aarti (Dashashwamedh)\n"
    "• Day 2: Kashi Vishwanath + old city lanes + local food\n"
    "• Day 3 (agar 3N ho): Sarnath half-day + relaxed ghats\n\n"
    "Dates bata do (approx month/week) — main pacing aur stays ke hisaab se refine kar dunga. "
    "Agar train/flight already book hai to wo bhi likh dena."
)


def followup_reply(main_whatsapp_e164: str) -> str:
    line = (main_whatsapp_e164 or "").strip() or "+918400437772"
    return (
        "Note kar liya \U0001f60a Team jaldi aapko options / costing share karegi isi chat par. "
        f"Agar urgent ho to seedha call/msg: {line} (WanderMate)."
    )
