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
# hay objetivo mensual documentado, solo un target_annual -> el objetivo H1 se
# calcula como (target_annual - suma(h2_targets)) / 6, para que los 12 meses
# sumen exactamente target_annual (antes se hacia target_annual/2/6, que
# ademas de la mitad anual sumaba los h2_targets reales encima, superando el
# target anual hasta en un 52%).
# commission_pct = % de comision de Likha sobre el neto de la plataforma.
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
     "target_annual": 8200, "commission_pct": 15, "active_from_month": 6,
     "h2_targets": [1200, 3500, 900, 1100, 600, 900]},
]

# NOTA (2026-07-21): target_annual de Jon Wiggen corregido de 8000 a 8200,
# aplicando la misma regla que las otras 4 propiedades: target_annual debe
# ser >= la suma de h2_targets, porque el objetivo de H1 se calcula como el
# resto (target_annual - h2_targets) repartido entre los meses de H1 ya
# activos. Para las demas propiedades (activas desde enero) esto sale solo
# porque tienen medio anyo real que planificar; Jon Wiggen (activo desde
# junio) no tiene H1 real -- su "H1" es solo junio, con target 0 por diseño
# (revenue_plan_2026.yaml ya lo fijaba asi: "Pre-launch"/"Launch Jun15, sin
# check-ins"). Los 8000 anteriores eran una estimacion redonda de la fase de
# planificacion (26-jun-2026) que nunca se reconcilio con el desglose mensual
# real (h2_targets suma 8200) -- mismo dia, misma sesion, sin fuente
# independiente. 8200 = 0 (jun) + 8200 (jul-dic), consistente con el resto
# del portfolio. Sigue sin haber confirmacion del propietario sobre el
# objetivo real (ver project_objectives.yaml, objetivos_por_propietario ->
# jon_wiggen -- "pendiente de confirmar", igual que stijn y noelia).

YEAR = 2026  # Ano de negocio de este dashboard (targets/h2_targets son especificos de 2026).
TODAY = datetime.date.today()
if TODAY.year != YEAR:
    # No se auto-avanza YEAR porque target_annual/h2_targets son cifras del
    # plan de negocio de un ano concreto -- avanzar solo el numero sin
    # actualizar esas cifras generaria datos con sentido pero incorrectos,
    # peor que un aviso claro de que hace falta revisión humana.
    print(
        f"AVISO: hoy ({TODAY.isoformat()}) ya no es del ano {YEAR} configurado en este script. "
        "Actualiza YEAR, target_annual y h2_targets de cada propiedad para el nuevo ano antes "
        "de seguir usando este refresco automatico.",
        file=sys.stderr,
    )
ALL_MONTHS_ES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']


def sum_revenue(property_id, start, end):
    # Deja que un fallo real de la API (red, 401, 5xx) reviente aqui en vez
    # de devolver 0 silenciosamente -- antes un error de Hostex se veia
    # identico a "sin reservas ese mes", que es exactamente el dato que este
    # dashboard existe para reportar bien.
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
        )
        resp.raise_for_status()
        body = resp.json()
        batch = (body.get("data") or {}).get("reservations") or []
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
    active_from = p.get("active_from_month", 1)
    monthly_confirmed = []
    for month in range(1, 13):
        start, end = month_range(YEAR, month)
        if month < active_from:
            # La propiedad todavia no existia -> sin datos, no "cero ingresos".
            monthly_confirmed.append(None)
            continue
        # Meses futuros sin ninguna reserva -> None (sin datos), no 0, para
        # no pintarlos como "cero ingresos" en el grafico.
        is_future_month = datetime.date(YEAR, month, 1) > TODAY
        amount = sum_revenue(p["id"], start, end)
        monthly_confirmed.append(None if (amount == 0 and is_future_month) else amount)

    # Objetivo H1 = lo que falta del target anual tras restar los h2_targets
    # reales, repartido entre los meses de H1 en los que la propiedad ya
    # existia (antes se hacia target_annual/2/6, que sumaba MAS los
    # h2_targets encima del target anual en vez de restarlos).
    h1_months_active = max(0, 6 - (active_from - 1))
    h1_total = p["target_annual"] - sum(p["h2_targets"])
    if h1_total < 0:
        print(
            f"AVISO {p['name']}: h2_targets ({sum(p['h2_targets'])}) ya supera "
            f"target_annual ({p['target_annual']}) -- revisar target_annual con Ander.",
            file=sys.stderr,
        )
        h1_total = 0
    h1_target_monthly = round(h1_total / h1_months_active) if h1_months_active else 0
    monthly_target = (
        [None] * (active_from - 1)
        + [h1_target_monthly] * h1_months_active
        + p["h2_targets"]
    )

    results.append({**p, "monthly_confirmed": monthly_confirmed, "monthly_target": monthly_target})
    print(f"{p['name']}: {monthly_confirmed}", file=sys.stderr)

# ── Regenerate the PROPERTIES block in index.html ───────────────────────────
with open("index.html", "r", encoding="utf-8") as f:
    html = f.read()

entries = []
for r in results:
    # La explicacion generica del calculo de objetivo H1 vive UNA vez como
    # caption compartido en index.html (ver <p id="cards-methodology-note">),
    # no repetida literalmente en las 5 tarjetas -- aqui solo queda lo que es
    # especifico de esta propiedad (si aplica).
    note = (
        ""
        if r.get("active_from_month", 1) == 1 else
        f"Propiedad activa desde {ALL_MONTHS_ES[r['active_from_month'] - 1]} {YEAR} -- meses "
        "anteriores sin datos (no cuentan como objetivo perdido)."
    )
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

today_str = datetime.date.today().isoformat()
today_es = f"{TODAY.day} {ALL_MONTHS_ES[TODAY.month - 1].lower()} {TODAY.year}"
footer_note = f"Likha Homes Revenue System · Datos actualizados automaticamente desde Hostex el {today_str}"
html = re.sub(r"Likha Homes Revenue System.*?</footer>", footer_note + "</footer>", html, flags=re.DOTALL)
html = re.sub(r'(<div class="update-badge">Actualizado: ).*?(</div>)', rf"\g<1>{today_es}\g<2>", html)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("index.html actualizado.", file=sys.stderr)
