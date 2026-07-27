"""Refresh the PROPERTIES data array in index.html from live Hostex reservations.

Usage: HOSTEX_ACCESS_TOKEN=... LIKHA_KB_GITHUB_TOKEN=... python refresh_data.py
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
import yaml

HOSTEX_BASE_URL = "https://api.hostex.io/v3"
TOKEN = os.environ.get("HOSTEX_ACCESS_TOKEN")
if not TOKEN:
    sys.exit("Set HOSTEX_ACCESS_TOKEN in the environment first.")
KB_TOKEN = os.environ.get("LIKHA_KB_GITHUB_TOKEN")
if not KB_TOKEN:
    sys.exit("Set LIKHA_KB_GITHUB_TOKEN in the environment first (fine-grained PAT, read-only, Contents, repo likha-hostex-mcp).")

HEADERS = {"Hostex-Access-Token": TOKEN, "Content-Type": "application/json"}

# Solo identidad/metadatos de cada propiedad -- comision, limpieza y targets
# YA NO se hardcodean aqui (2026-07-27): se leen en vivo de likha-hostex-mcp
# (ver fetch_kb_property_data) para que no haya dos copias que desincronizar.
# "key" (dashboard) <-> nombre de propiedad en revenue_plan_2026.yaml.
PROPERTIES_META = [
    {"id": 12492685, "key": "stijn", "kb_key": "stijn", "name": "House – Stijn", "location": "San Miguel de Salinas"},
    {"id": 12507366, "key": "carlos", "kb_key": "carlos", "name": "Villa Carlos", "location": "Torrevieja"},
    {"id": 12287282, "key": "alhama", "kb_key": "noelia_alhama", "name": "Apt Noelia – Alhama", "location": "Alhama de Murcia"},
    {"id": 12506184, "key": "cantabria", "kb_key": "noelia_cantabria", "name": "Apt Cantabria – Noelia", "location": "San Vicente de la Barquera"},
    {"id": 12690818, "key": "jon", "kb_key": "jon_wiggen", "name": "Apt Jon Wiggen", "location": "Mar Menor Golf Resort", "active_from_month": 6},
]

KB_REPO = "anderlasacatalan-hub/likha-hostex-mcp"
H2_MONTHS = ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12"]


def fetch_kb_property_data(github_token):
    # Comision, limpieza y targets viven en likha-hostex-mcp (repo privado) --
    # se leen aqui en vivo en vez de copiarlos a mano, para que un cambio ahi
    # (ej. Ander confirma una comision nueva) se refleje solo, sin tener que
    # acordarse de tocar tambien este script. Ver likha_cleaning_fee_eur en
    # likha-owner-constraints.json y modelo_comision en revenue_plan_2026.yaml.
    headers = {"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github.raw+json"}

    def fetch_file(path):
        resp = requests.get(
            f"https://api.github.com/repos/{KB_REPO}/contents/{path}",
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.text

    constraints = json.loads(fetch_file("likha-owner-constraints.json"))
    revenue_plan = yaml.safe_load(fetch_file("likha-rm-knowledge/plans/revenue_plan_2026.yaml"))

    by_id = {}
    for prop in constraints["properties"]:
        c = prop["constraints"]
        by_id[prop["hostex_property_id"]] = {
            "commission_pct": c["likha_management_commission_percent"],
            "cleaning_fee_eur": c.get("likha_cleaning_fee_eur", 0),
            "cleaning_fee_pet_eur": c.get("likha_cleaning_fee_pet_eur", c.get("likha_cleaning_fee_eur", 0)),
        }

    for meta in PROPERTIES_META:
        kb_key = meta["kb_key"]
        # target_annual viene de desglose_mensual (no de targets_anuales_2026.realista_eur):
        # detectado 2026-07-27 que para Alhama esos dos campos estaban desincronizados
        # (17000 vs 14000, tras una revision a la baja que solo se aplico en un sitio) --
        # desglose_mensual.total_anual_target es el que de verdad usan los targets
        # mensuales reales (h2_targets), asi que es la fuente correcta aqui.
        by_id[meta["id"]]["target_annual"] = revenue_plan["desglose_mensual"][kb_key]["total_anual_target"]
        target_eur_mes = revenue_plan["desglose_mensual"][kb_key]["target_eur_mes"]
        by_id[meta["id"]]["h2_targets"] = [target_eur_mes[m]["target"] for m in H2_MONTHS]

    return by_id


kb_data = fetch_kb_property_data(KB_TOKEN)
PROPERTIES = [{**meta, **kb_data[meta["id"]]} for meta in PROPERTIES_META]

# NOTA (2026-07-21): target_annual de Jon Wiggen corregido de 8000 a 8200,
# aplicando la misma regla que las otras 4 propiedades: target_annual debe
# ser >= la suma de h2_targets, porque el objetivo de H1 se calcula como el
# resto (target_annual - h2_targets) repartido entre los meses de H1 ya
# activos. Para las demas propiedades (activas desde enero) esto sale solo
# porque tienen medio anyo real que planificar; Jon Wiggen (activo desde
# junio) no tiene H1 real -- su "H1" es solo junio, con target 0 por diseño
# (revenue_plan_2026.yaml ya lo fijaba asi: "Pre-launch"/"Launch Jun15, sin
# check-ins"). Este numero ahora viene directo de revenue_plan_2026.yaml, ya
# no se puede desincronizar entre los dos archivos como paso esa vez.

YEAR = 2026  # Ano de negocio de este dashboard (targets/h2_targets son especificos de 2026).
TODAY = datetime.date.today()
if TODAY.year != YEAR:
    # No se auto-avanza YEAR porque target_annual/h2_targets son cifras del
    # plan de negocio de un ano concreto -- avanzar solo el numero sin
    # actualizar esas cifras generaria datos con sentido pero incorrectos,
    # peor que un aviso claro de que hace falta revisión humana.
    print(
        f"AVISO: hoy ({TODAY.isoformat()}) ya no es del ano {YEAR} configurado en este script. "
        "Actualiza YEAR en este script y el ano del plan de revenue en likha-hostex-mcp antes "
        "de seguir usando este refresco automatico.",
        file=sys.stderr,
    )
ALL_MONTHS_ES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']


def month_detail(property_id, start, end):
    # Deja que un fallo real de la API (red, 401, 5xx) reviente aqui en vez
    # de devolver 0 silenciosamente -- antes un error de Hostex se veia
    # identico a "sin reservas ese mes", que es exactamente el dato que este
    # dashboard existe para reportar bien.
    #
    # platform_net = payment.total_amount (lo que realmente cobra el
    # propietario tras la comision de la plataforma). Verificado 2026-07-27
    # contra 21 reservas reales (Airbnb y Booking.com, Stijn y Carlos):
    # total_rate - total_commission == payment.total_amount en el 100% de
    # los casos -- es el dato fiable que faltaba para calcular la comision
    # de Likha segun la formula real (modelo_comision), no total_rate bruto.
    gross = 0
    platform_net = 0
    stays = 0
    pet_stays = 0
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
        gross += (r.get("rates") or {}).get("total_rate", {}).get("amount", 0) or 0
        platform_net += (r.get("payment") or {}).get("total_amount", 0) or 0
        stays += 1
        details = (r.get("rates") or {}).get("details") or []
        if any(d.get("type") == "PET_FEE" for d in details):
            pet_stays += 1
    return {
        "gross": round(gross),
        "platform_net": round(platform_net),
        "stays": stays,
        "pet_stays": pet_stays,
    }


def month_range(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day:02d}"


results = []
for p in PROPERTIES:
    active_from = p.get("active_from_month", 1)
    cleaning_fee = p.get("cleaning_fee_eur", 0)
    cleaning_fee_pet = p.get("cleaning_fee_pet_eur", cleaning_fee)
    monthly_confirmed = []
    monthly_commissionable = []
    for month in range(1, 13):
        start, end = month_range(YEAR, month)
        if month < active_from:
            # La propiedad todavia no existia -> sin datos, no "cero ingresos".
            monthly_confirmed.append(None)
            monthly_commissionable.append(None)
            continue
        # Meses futuros sin ninguna reserva -> None (sin datos), no 0, para
        # no pintarlos como "cero ingresos" en el grafico.
        is_future_month = datetime.date(YEAR, month, 1) > TODAY
        detail = month_detail(p["id"], start, end)
        amount = detail["gross"]
        monthly_confirmed.append(None if (amount == 0 and is_future_month) else amount)

        non_pet_stays = detail["stays"] - detail["pet_stays"]
        cleaning_deduction = non_pet_stays * cleaning_fee + detail["pet_stays"] * cleaning_fee_pet
        commissionable = max(0, detail["platform_net"] - cleaning_deduction)
        monthly_commissionable.append(None if (amount == 0 and is_future_month) else round(commissionable))

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

    results.append({
        **p,
        "monthly_confirmed": monthly_confirmed,
        "monthly_commissionable": monthly_commissionable,
        "monthly_target": monthly_target,
    })
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
        f"    monthly_commissionable: {json.dumps(r['monthly_commissionable'])},\n"
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
