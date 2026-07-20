"""Scheduled Modal job: refresh likha-dashboard/index.html from live Hostex
data once a day, and push the result straight to GitHub (no local machine
involved). Same PROPERTIES/monthly_target logic as refresh_data.py -- kept as
a second, duplicated copy on purpose (this repo's convention is single
self-contained scripts, like likha-guest-messaging/app.py) -- if the revenue
calculation changes, update BOTH files.

Setup (one-time):
1. modal secret create likha-github GITHUB_TOKEN=<fine-grained PAT, repo
   likha-dashboard, permission "Contents: Read and write">
   (create the token at https://github.com/settings/tokens)
2. modal deploy dashboard_refresh_modal.py
   (reuses the existing "likha-secrets" secret for HOSTEX_ACCESS_TOKEN, and
   for TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID to report failures)

Runs once every 24h (modal.Period(hours=24)). To trigger a run right now
without waiting for the schedule: modal run dashboard_refresh_modal.py
"""
import base64
import calendar
import datetime
import json
import os
import re
import sys

import modal

app = modal.App("likha-dashboard-refresh")
image = modal.Image.debian_slim().pip_install("requests")

GITHUB_REPO = "anderlasacatalan-hub/likha-dashboard"
GITHUB_BRANCH = "main"
GITHUB_FILE_PATH = "index.html"
HOSTEX_BASE_URL = "https://api.hostex.io/v3"

# Mismo PROPERTIES que refresh_data.py -- ver ese archivo para el comentario
# completo sobre el calculo de monthly_target y active_from_month.
PROPERTIES = [
    {"id": 12492685, "key": "stijn", "name": "House – Stijn", "location": "San Miguel de Salinas",
     "target_annual": 18000, "commission_pct": 20,
     "h2_targets": [2520, 2990, 1210, 1150, 850, 1660]},
    {"id": 12507366, "key": "carlos", "name": "Villa Carlos", "location": "Torrevieja",
     "target_annual": 26000, "commission_pct": 15,
     "h2_targets": [3500, 4000, 1800, 2100, 1550, 1700]},
    {"id": 12287282, "key": "alhama", "name": "Apt Noelia – Alhama", "location": "Alhama de Murcia",
     "target_annual": 14000, "commission_pct": 15,
     "h2_targets": [2700, 2400, 1500, 1200, 1050, 700]},
    {"id": 12506184, "key": "cantabria", "name": "Apt Cantabria – Noelia", "location": "San Vicente de la Barquera",
     "target_annual": 15000, "commission_pct": 15,
     "h2_targets": [2500, 4000, 1200, 900, 600, 800]},
    {"id": 12690818, "key": "jon", "name": "Apt Jon Wiggen", "location": "Mar Menor Golf Resort",
     "target_annual": 8000, "commission_pct": 15, "active_from_month": 6,
     "h2_targets": [1200, 3500, 900, 1100, 600, 900]},
]

YEAR = 2026
ALL_MONTHS_ES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

# Mismo MANUAL_ADJUSTMENTS que refresh_data.py -- ver ese archivo para el
# comentario completo. Reversible: borra la entrada para deshacer.
MANUAL_ADJUSTMENTS = [
    {
        "property_key": "jon", "month": 7, "amount_eur": 1780,
        "reason": (
            "Reserva Alex Tsioukaris (Hostex 0-HMTA5SB334-if3431krxv, check-in "
            "2026-07-16): Airbnb solo registra 323€ por las 2 noches gestionadas "
            "por la plataforma; el resto de la estancia se pago en efectivo fuera "
            "de Hostex (confirmado por Ander)."
        ),
        "added": "2026-07-20",
    },
]


def _sum_revenue(property_id, start, end, hostex_token):
    import requests

    headers = {"Hostex-Access-Token": hostex_token, "Content-Type": "application/json"}
    total = 0
    reservations = []
    offset = 0
    while True:
        resp = requests.get(
            f"{HOSTEX_BASE_URL}/reservations",
            headers=headers,
            params={
                "property_id": property_id,
                "start_check_in_date": start,
                "end_check_in_date": end,
                "status": "accepted",
                "limit": 100,
                "offset": offset,
            },
            timeout=20,
        )
        resp.raise_for_status()
        batch = (resp.json().get("data") or {}).get("reservations") or []
        reservations.extend(batch)
        if len(batch) < 100:
            break
        offset += 100
    for r in reservations:
        total += (r.get("rates") or {}).get("total_rate", {}).get("amount", 0) or 0
    return round(total)


def _month_range(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day:02d}"


def _regenerate_html(html, hostex_token, today):
    warnings = []
    results = []
    for p in PROPERTIES:
        active_from = p.get("active_from_month", 1)
        monthly_confirmed = []
        for month in range(1, 13):
            start, end = _month_range(YEAR, month)
            if month < active_from:
                monthly_confirmed.append(None)
                continue
            is_future_month = datetime.date(YEAR, month, 1) > today
            amount = _sum_revenue(p["id"], start, end, hostex_token)
            amount += sum(
                a["amount_eur"] for a in MANUAL_ADJUSTMENTS
                if a["property_key"] == p["key"] and a["month"] == month
            )
            monthly_confirmed.append(None if (amount == 0 and is_future_month) else amount)

        h1_months_active = max(0, 6 - (active_from - 1))
        h1_total = p["target_annual"] - sum(p["h2_targets"])
        if h1_total < 0:
            warnings.append(
                f"{p['name']}: h2_targets ({sum(p['h2_targets'])}) ya supera "
                f"target_annual ({p['target_annual']}) -- revisar con Ander."
            )
            h1_total = 0
        h1_target_monthly = round(h1_total / h1_months_active) if h1_months_active else 0
        monthly_target = (
            [None] * (active_from - 1)
            + [h1_target_monthly] * h1_months_active
            + p["h2_targets"]
        )
        results.append({**p, "monthly_confirmed": monthly_confirmed, "monthly_target": monthly_target})

    entries = []
    for r in results:
        # La explicacion generica del calculo de objetivo H1 vive UNA vez como
        # caption compartido en index.html (ver <p id="cards-methodology-note">),
        # no repetida literalmente en las 5 tarjetas -- mismo criterio que
        # refresh_data.py, aqui solo queda lo especifico de esta propiedad.
        note = (
            ""
            if r.get("active_from_month", 1) == 1 else
            f"Propiedad activa desde {ALL_MONTHS_ES[r['active_from_month'] - 1]} {YEAR} -- meses "
            "anteriores sin datos (no cuentan como objetivo perdido)."
        )
        prop_adjustments = [a for a in MANUAL_ADJUSTMENTS if a["property_key"] == r["key"]]
        if prop_adjustments:
            adj_total = sum(a["amount_eur"] for a in prop_adjustments)
            adj_note = f"Incluye {adj_total}€ de pago en efectivo fuera de plataforma, confirmado por Ander."
            note = f"{note} {adj_note}".strip()
        entries.append(
            "  {\n"
            f"    id: '{r['key']}',\n"
            f"    name: '{r['name']}',\n"
            f"    location: '{r['location']}',\n"
            f"    target_annual: {r['target_annual']},\n"
            f"    commission_pct: {r['commission_pct']},\n"
            f"    monthly_target: {json.dumps(r['monthly_target'])},\n"
            f"    monthly_confirmed: {json.dumps(r['monthly_confirmed'])},\n"
            f"    note: {json.dumps(note, ensure_ascii=False)}\n"
            "  }"
        )
    new_block = "const PROPERTIES = [\n" + ",\n".join(entries) + "\n];"
    html = re.sub(r"const PROPERTIES = \[.*?\];", new_block, html, flags=re.DOTALL)

    today_str = today.isoformat()
    today_es = f"{today.day} {ALL_MONTHS_ES[today.month - 1].lower()} {today.year}"
    footer_note = f"Likha Homes Revenue System · Datos actualizados automaticamente desde Hostex el {today_str}"
    html = re.sub(r"Likha Homes Revenue System.*?</footer>", footer_note + "</footer>", html, flags=re.DOTALL)
    html = re.sub(r'(<div class="update-badge">Actualizado: ).*?(</div>)', rf"\g<1>{today_es}\g<2>", html)

    return html, warnings


def _notify_telegram(text):
    import requests

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
    except Exception as e:
        print(f"ERROR adicional avisando por Telegram: {e}", file=sys.stderr)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("likha-secrets"), modal.Secret.from_name("likha-github")],
    schedule=modal.Period(hours=24),
)
def refresh_dashboard():
    import requests

    github_token = os.environ["GITHUB_TOKEN"]
    hostex_token = os.environ["HOSTEX_ACCESS_TOKEN"]
    gh_headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }

    try:
        get_resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}",
            headers=gh_headers,
            params={"ref": GITHUB_BRANCH},
            timeout=20,
        )
        get_resp.raise_for_status()
        file_data = get_resp.json()
        html = base64.b64decode(file_data["content"]).decode("utf-8")
        sha = file_data["sha"]

        today = datetime.date.today()
        new_html, warnings = _regenerate_html(html, hostex_token, today)

        if new_html == html:
            print("Sin cambios, no se hace commit.")
            return {"ok": True, "changed": False, "warnings": warnings}

        put_resp = requests.put(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}",
            headers=gh_headers,
            json={
                "message": f"chore: auto-refresh dashboard data {today.isoformat()}",
                "content": base64.b64encode(new_html.encode("utf-8")).decode("ascii"),
                "sha": sha,
                "branch": GITHUB_BRANCH,
            },
            timeout=20,
        )
        put_resp.raise_for_status()

        if warnings:
            _notify_telegram(
                "Dashboard actualizado, pero con avisos:\n" + "\n".join(warnings)
            )
        return {"ok": True, "changed": True, "warnings": warnings}
    except Exception as e:
        _notify_telegram(f"⚠️ Fallo al auto-refrescar el dashboard: {e}")
        print(f"ERROR: {e}", file=sys.stderr)
        return {"ok": False, "error": str(e)}


@app.local_entrypoint()
def main():
    result = refresh_dashboard.remote()
    print(json.dumps(result, indent=2, ensure_ascii=False))
