"""Refresh the PROPERTIES data array in index.html from live Hostex reservations.

Usage: HOSTEX_ACCESS_TOKEN=... python refresh_data.py
Does NOT include any guest names or other personal data in the output -- only
aggregated revenue totals, to keep this safe for the public dashboard.

Produces one combined 12-month (Ene-Dic) series per property instead of a
lump H1 total + monthly H2, so properties running since January show real
month-by-month figures across the whole year.
"""
import calendar
import datetime
import json
import os
import re
import sys

import requests

HOSTEX_BASE_URL = "https://api.hostex.io/v3"
TOKEN = os.environ.get("HOSTEX_ACCESS_TOKEN")
if not TOKEN:
    sys.exit("Set HOSTEX_ACCESS_TOKEN in the environment first.")

HEADERS = {"Hostex-Access-Token": TOKEN, "Content-Type": "application/json"}

# h2_targets = objetivos reales Jul-Dic del plan de revenue. Para Ene-Jun no
# hay objetivo mensual documentado, solo un target_annual -> se reparte a
# partes iguales entre los 6 meses como aproximacion (marcado en la nota).
PROPERTIES = [
    {"id": 12492685, "key": "stijn", "name": "House – Stijn", "location": "San Miguel de Salinas",
     "target_annual": 18000, "h2_targets": [2520, 2990, 1210, 1150, 850, 1660]},
    {"id": 12507366, "key": "carlos", "name": "Villa Carlos", "location": "Torrevieja",
     "target_annual": 26000, "h2_targets": [3500, 4000, 1800, 2100, 1550, 1700]},
    {"id": 12287282, "key": "alhama", "name": "Apt Noelia – Alhama", "location": "Alhama de Murcia",
     "target_annual": 14000, "h2_targets": [2700, 2400, 1500, 1200, 1050, 700]},
    {"id": 12506184, "key": "cantabria", "name": "Apt Cantabria – Noelia", "location": "San Vicente de la Barquera",
     "target_annual": 15000, "h2_targets": [2500, 4000, 1200, 900, 600, 800]},
    {"id": 12690818, "key": "jon", "name": "Apt Jon Wiggen", "location": "Mar Menor Golf Resort",
     "target_annual": 8000, "h2_targets": [1200, 3500, 900, 1100, 600, 900]},
]

YEAR = 2026
TODAY = datetime.date.today()


def sum_revenue(property_id, start, end):
    total = 0
    reservations = []
    offset = 0
    while True:
        resp = requests.get(
            f"{HOSTEX_BASE_URL}/reservations",
            headers=HEADERS,
            params={
                "property_id": property_id,
                "start_check_in_date": start,
                "end_check_in_date": end,
                "status": "accepted",
                "limit": 100,
                "offset": offset,
            },
            timeout=20,
        ).json()
        batch = (resp.get("data") or {}).get("reservations") or []
        reservations.extend(batch)
        if len(batch) < 100:
            break
        offset += 100
    for r in reservations:
        total += (r.get("rates") or {}).get("total_rate", {}).get("amount", 0) or 0
    return round(total)


def month_range(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day:02d}"


results = []
for p in PROPERTIES:
    monthly_confirmed = []
    for month in range(1, 13):
        start, end = month_range(YEAR, month)
        # Meses futuros sin ninguna reserva -> None (sin datos), no 0, para
        # no pintarlos como "cero ingresos" en el grafico.
        is_future_month = datetime.date(YEAR, month, 1) > TODAY
        amount = sum_revenue(p["id"], start, end)
        monthly_confirmed.append(None if (amount == 0 and is_future_month) else amount)
    h1_target_monthly = round(p["target_annual"] / 2 / 6)
    monthly_target = [h1_target_monthly] * 6 + p["h2_targets"]
    results.append({**p, "monthly_confirmed": monthly_confirmed, "monthly_target": monthly_target})
    print(f"{p['name']}: {monthly_confirmed}", file=sys.stderr)

# ── Regenerate the PROPERTIES block in index.html ───────────────────────────
with open("index.html", "r", encoding="utf-8") as f:
    html = f.read()

entries = []
for r in results:
    entries.append(
        "  {\n"
        f"    id: '{r['key']}',\n"
        f"    name: '{r['name']}',\n"
        f"    location: '{r['location']}',\n"
        f"    target_annual: {r['target_annual']},\n"
        f"    monthly_target: {json.dumps(r['monthly_target'])},\n"
        f"    monthly_confirmed: {json.dumps(r['monthly_confirmed'])},\n"
        "    note: 'Ene-Jun: objetivo mensual repartido a partes iguales del target anual (aproximado). Jul-Dic: objetivo real del plan de revenue.'\n"
        "  }"
    )
new_block = "const PROPERTIES = [\n" + ",\n".join(entries) + "\n];"

html = re.sub(r"const PROPERTIES = \[.*?\];", new_block, html, flags=re.DOTALL)

footer_note = f"Likha Homes Revenue System · Datos actualizados automaticamente desde Hostex el {datetime.date.today().isoformat()}"
html = re.sub(r"Likha Homes Revenue System.*?</footer>", footer_note + "</footer>", html, flags=re.DOTALL)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("index.html actualizado.", file=sys.stderr)
