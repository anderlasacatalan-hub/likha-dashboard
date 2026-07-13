# Likha Homes Revenue Dashboard — Deploy to GitHub Pages

Repo local listo en: `C:\Users\ASUS\likha-dashboard\`  
Commit inicial: `3c4dbd9 feat: launch Likha Homes Revenue Dashboard 2026`

---

## Pasos para publicar (5 minutos)

### 1. Crear repo en GitHub

Ir a: https://github.com/new

- **Repository name:** `likha-dashboard`
- **Visibility:** Public (requerido para GitHub Pages gratis)
- **NO** marcar "Add README", "Add .gitignore", ni nada más
- Clic en **"Create repository"**

### 2. Conectar repo local y hacer push

Abrir PowerShell en `C:\Users\ASUS\likha-dashboard\` y ejecutar:

```powershell
cd C:\Users\ASUS\likha-dashboard

# Reemplaza TU_USERNAME con tu usuario de GitHub
git remote add origin https://github.com/TU_USERNAME/likha-dashboard.git

git push -u origin main
```

GitHub pedirá credenciales la primera vez — usa tu usuario y un Personal Access Token (no la contraseña).

### 3. Activar GitHub Pages

En el repo recién creado en GitHub:

1. Ir a **Settings** → **Pages** (columna izquierda)
2. En "Branch": seleccionar **main** → carpeta **/ (root)**
3. Clic en **Save**

GitHub tarda ~2 minutos en publicar.

### 4. URL del dashboard

```
https://TU_USERNAME.github.io/likha-dashboard
```

---

## Actualizar datos manualmente

Los datos vienen del array `PROPERTIES` en `index.html`, regenerado por `refresh_data.py`.
Para forzar una actualización manual desde tu ordenador:

```powershell
cd C:\Users\ander\Projects\likha-dashboard
$env:PYTHONIOENCODING="utf-8"; $env:PYTHONUTF8="1"
$env:HOSTEX_ACCESS_TOKEN = (Get-Content .env | Select-String HOSTEX_ACCESS_TOKEN).ToString().Split('=')[1]
python refresh_data.py
git add index.html
git commit -m "feat: update revenue data YYYY-MM-DD"
git push
```

GitHub Pages se actualiza automáticamente en ~1 minuto.

---

## Automatización (2026-07-13): refresco diario sin intervención manual

`dashboard_refresh_modal.py` es una app de Modal con una función programada
(`modal.Period(hours=24)`) que hace exactamente lo mismo que el paso manual de
arriba, pero sola: llama a Hostex, recalcula `PROPERTIES` y sube el `index.html`
actualizado directamente a GitHub vía la API de contenidos (sin pasar por tu
ordenador ni por `git push`).

**Setup (una sola vez, ya hecho):**
1. Secret de Modal `likha-github` con `GITHUB_TOKEN` — fine-grained PAT,
   repositorio `likha-dashboard`, permiso "Contents: Read and write", sin
   expiración. Creado en `github.com/settings/tokens`.
2. Reutiliza el secret `likha-secrets` (perfil `anderlasacatalan`, el mismo de
   `likha-guest-messaging`) para `HOSTEX_ACCESS_TOKEN` y, si algo falla o hay
   avisos (p.ej. el de Jon Wiggen, ver `refresh_data.py`), para avisar por
   Telegram con `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`.
3. `modal deploy dashboard_refresh_modal.py`.

**Para lanzar una ejecución ahora mismo sin esperar al cron:**
```powershell
cd C:\Users\ander\Projects\likha-dashboard
$env:PYTHONIOENCODING="utf-8"; $env:PYTHONUTF8="1"
python -m modal run dashboard_refresh_modal.py
```

**Si falla:** avisa por Telegram (mismo bot que guest-messaging) y no toca
nada en GitHub. `refresh_data.py` (el script manual) y
`dashboard_refresh_modal.py` (el automático) tienen la MISMA lógica de
cálculo duplicada a propósito — si cambias el cálculo de `monthly_target` o
`active_from_month` en uno, replica el cambio en el otro.
