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
2. modal secret create likha-kb-read LIKHA_KB_GITHUB_TOKEN=<fine-grained PAT,
   repo likha-hostex-mcp, permission "Contents: Read-only"> -- lee comision,
   limpieza y targets en vivo del KB en vez de tenerlos hardcodeados aqui
   (ver PROPERTIES_META / fetch_kb_property_data).
3. modal deploy dashboard_refresh_modal.py
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
image = modal.Image.debian_slim().pip_install("requests", "pyyaml")

GITHUB_REPO = "anderlasacatalan-hub/likha-dashboard"
GITHUB_BRANCH = "main"
GITHUB_FILE_PATH = "index.html"
HOSTEX_BASE_URL = "https://api.hostex.io/v3"
KB_REPO = "anderlasacatalan-hub/likha-hostex-mcp"
H2_MONTHS = ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12"]

# Solo identidad/metadatos de cada propiedad -- comision, limpieza y targets
# YA NO se hardcodean aqui (2026-07-27): se leen en vivo de likha-hostex-mcp
# (ver fetch_kb_property_data), mismo criterio que refresh_data.py.
PROPERTIES_META = [
    {"id": 12492685, "key": "stijn", "kb_key": "stijn", "name": "House – Stijn", "location": "San Miguel de Salinas"},
    {"id": 12507366, "key": "carlos", "kb_key": "carlos", "name": "Villa Carlos", "location": "Torrevieja"},
    {"id": 12287282, "key": "alhama", "kb_key": "noelia_alhama", "name": "Apt Noelia – Alhama", "location": "Alhama de Murcia"},
    {"id": 12506184, "key": "cantabria", "kb_key": "noelia_cantabria", "name": "Apt Cantabria – Noelia", "location": "San Vicente de la Barquera"},
    {"id": 12690818, "key": "jon", "kb_key": "jon_wiggen", "name": "Apt Jon Wiggen", "location": "Mar Menor Golf Resort", "active_from_month": 6},
]

YEAR = 2026


def _request_with_retry(fn, attempts=3, base_delay=2):
    """Reintenta fn() (una llamada que ya hace requests.get/put(...) +
    .raise_for_status()) ante fallos TRANSITORIOS -- 5xx, timeout, error de
    conexion -- con backoff 2s/4s/8s. NUNCA reintenta un 4xx (error real del
    cliente, un reintento no lo arregla).

    Bug real 2026-08-17: un 503 puntual de GitHub (incidente Critical
    confirmado en githubstatus.com, 13:40-16:59 UTC) tumbo el refresh diario
    entero sin ningun reintento -- dejaba el dashboard desactualizado 24h
    completas por un blip de minutos. No paso nada grave esa vez porque el
    proximo cron (24h despues) ya caia con GitHub recuperado, pero el riesgo
    era real, no teorico."""
    import time
    import requests

    last_exc = None
    for attempt in range(attempts):
        try:
            return fn()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status is not None and status < 500:
                raise
            last_exc = e
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
        if attempt < attempts - 1:
            time.sleep(base_delay * (2 ** attempt))
    raise last_exc
ALL_MONTHS_ES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']


def _fetch_kb_property_data(kb_github_token):
    import requests
    import yaml

    headers = {"Authorization": f"Bearer {kb_github_token}", "Accept": "application/vnd.github.raw+json"}

    def fetch_file(path):
        def _do():
            resp = requests.get(
                f"https://api.github.com/repos/{KB_REPO}/contents/{path}",
                headers=headers,
                timeout=20,
            )
            resp.raise_for_status()
            return resp
        return _request_with_retry(_do).text

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
        # target_annual viene de desglose_mensual (no de targets_anuales_2026.realista_eur) --
        # ver comentario completo en refresh_data.py::fetch_kb_property_data.
        by_id[meta["id"]]["target_annual"] = revenue_plan["desglose_mensual"][kb_key]["total_anual_target"]
        target_eur_mes = revenue_plan["desglose_mensual"][kb_key]["target_eur_mes"]
        by_id[meta["id"]]["h2_targets"] = [target_eur_mes[m]["target"] for m in H2_MONTHS]

    return by_id


def _month_detail(property_id, start, end, hostex_token):
    import requests

    # platform_net = payment.total_amount -- ver comentario completo en
    # refresh_data.py::month_detail sobre por que este campo (no total_rate)
    # es la base correcta para la comision de Likha.
    headers = {"Hostex-Access-Token": hostex_token, "Content-Type": "application/json"}
    gross = 0
    platform_net = 0
    stays = 0
    pet_stays = 0
    reservations = []
    offset = 0
    while True:
        def _do(offset=offset):
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
            return resp
        resp = _request_with_retry(_do)
        batch = (resp.json().get("data") or {}).get("reservations") or []
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


def _month_range(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day:02d}"


def _regenerate_html(html, hostex_token, kb_github_token, today):
    warnings = []
    results = []
    kb_data = _fetch_kb_property_data(kb_github_token)
    properties = [{**meta, **kb_data[meta["id"]]} for meta in PROPERTIES_META]

    for p in properties:
        active_from = p.get("active_from_month", 1)
        cleaning_fee = p.get("cleaning_fee_eur", 0)
        cleaning_fee_pet = p.get("cleaning_fee_pet_eur", cleaning_fee)
        monthly_confirmed = []
        monthly_commissionable = []
        for month in range(1, 13):
            start, end = _month_range(YEAR, month)
            if month < active_from:
                monthly_confirmed.append(None)
                monthly_commissionable.append(None)
                continue
            is_future_month = datetime.date(YEAR, month, 1) > today
            detail = _month_detail(p["id"], start, end, hostex_token)
            amount = detail["gross"]
            monthly_confirmed.append(None if (amount == 0 and is_future_month) else amount)

            non_pet_stays = detail["stays"] - detail["pet_stays"]
            cleaning_deduction = non_pet_stays * cleaning_fee + detail["pet_stays"] * cleaning_fee_pet
            commissionable = max(0, detail["platform_net"] - cleaning_deduction)
            monthly_commissionable.append(None if (amount == 0 and is_future_month) else round(commissionable))

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
        results.append({
            **p,
            "monthly_confirmed": monthly_confirmed,
            "monthly_commissionable": monthly_commissionable,
            "monthly_target": monthly_target,
        })

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
    secrets=[
        modal.Secret.from_name("likha-secrets"),
        modal.Secret.from_name("likha-github"),
        modal.Secret.from_name("likha-kb-read"),
    ],
    schedule=modal.Period(hours=24),
)
def refresh_dashboard():
    import requests

    github_token = os.environ["GITHUB_TOKEN"]
    hostex_token = os.environ["HOSTEX_ACCESS_TOKEN"]
    kb_github_token = os.environ["LIKHA_KB_GITHUB_TOKEN"]
    gh_headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }

    try:
        def _get_current():
            resp = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}",
                headers=gh_headers,
                params={"ref": GITHUB_BRANCH},
                timeout=20,
            )
            resp.raise_for_status()
            return resp
        get_resp = _request_with_retry(_get_current)
        file_data = get_resp.json()
        html = base64.b64decode(file_data["content"]).decode("utf-8")
        sha = file_data["sha"]

        today = datetime.date.today()
        new_html, warnings = _regenerate_html(html, hostex_token, kb_github_token, today)

        if new_html == html:
            print("Sin cambios, no se hace commit.")
            return {"ok": True, "changed": False, "warnings": warnings}

        def _put_updated():
            resp = requests.put(
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
            resp.raise_for_status()
            return resp
        _request_with_retry(_put_updated)

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
