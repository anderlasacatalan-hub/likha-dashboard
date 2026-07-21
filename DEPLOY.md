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
3. `.\modal.ps1 deploy dashboard_refresh_modal.py`.

**Para lanzar una ejecución ahora mismo sin esperar al cron:**
```powershell
cd C:\Users\ander\Projects\likha-dashboard
.\modal.ps1 run dashboard_refresh_modal.py
```

**Usa siempre `.\modal.ps1`** en vez de `modal` / `python -m modal` directamente — es un wrapper
de este repo que fija `MODAL_PROFILE=anderlasacatalan` en cada comando (el perfil activo de Modal
es una config global del CLI, no por carpeta, y otra sesión trabajando en otro proyecto en esta
misma máquina puede dejarlo apuntando al workspace equivocado sin avisar).

**Si falla:** avisa por Telegram (mismo bot que guest-messaging) y no toca
nada en GitHub. `refresh_data.py` (el script manual) y
`dashboard_refresh_modal.py` (el automático) tienen la MISMA lógica de
cálculo duplicada a propósito — si cambias el cálculo de `monthly_target` o
`active_from_month` en uno, replica el cambio en el otro.

## Ajustes manuales de ingresos (2026-07-20, retirado 2026-07-21)

Hostex solo sabe de lo que pasa por la plataforma. Cuando hay un pago real
que Hostex nunca va a ver (ej. efectivo fuera de plataforma), la primera
versión de esto fue un parche de código: una entrada en `MANUAL_ADJUSTMENTS`
en `refresh_data.py`/`dashboard_refresh_modal.py` que sumaba el importe a
mano sin tocar Hostex.

**Caso que lo originó:** Jon Wiggen, julio 2026, +1.780€ — reserva de Alex
Tsioukaris (Hostex `0-HMTA5SB334-if3431krxv`, check-in 16 jul): Airbnb solo
registra 323€ por 2 noches, el resto de la estancia se pagó en efectivo
fuera de la plataforma (confirmado por Ander).

**Resuelto de raíz el 2026-07-21:** en vez de mantener el parche, se creó la
reserva real en Hostex (`5-6BQG8SJ3O`, canal "Booking Site", método "Cash",
1.780€, 18 jul → 5 ago, remark con el enlace a la reserva Airbnb original) y
se retiró `MANUAL_ADJUSTMENTS` de ambos archivos — Hostex vuelve a ser la
única fuente de verdad, `sum_revenue()` ya recoge el importe solo. Cifra
mensual de Jon Wiggen sin cambios (julio sigue en 2.843€), solo cambió de
dónde sale el número.

**Nota para el futuro:** si vuelve a pasar algo similar (pago fuera de
plataforma), preferir crear la reserva manual directamente en Hostex sobre
reintroducir `MANUAL_ADJUSTMENTS` — evita duplicar lógica y mantiene un solo
sitio con la verdad. El patrón `MANUAL_ADJUSTMENTS` se deja documentado aquí
por si algún día hace falta (p.ej. si la API de Hostex no permite crear la
reserva por algún motivo), no porque siga en uso.
