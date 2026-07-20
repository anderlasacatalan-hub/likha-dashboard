# Wrapper para el CLI de Modal en este proyecto.
#
# Por que existe: el perfil activo de Modal (`modal profile activate`) es una
# config GLOBAL del CLI (~/.modal.toml), no por carpeta. Si otra sesion trabaja
# en otro proyecto (ej. Micasamo -> perfil "ander-lasa") en este mismo
# ordenador, puede dejar el perfil global apuntando al workspace equivocado
# sin ningun aviso. La variable de entorno MODAL_PROFILE tiene prioridad sobre
# el perfil "activo" del archivo de config, asi que fijarla aqui garantiza el
# workspace correcto (anderlasacatalan) en cada comando, sin depender de que
# nadie se acuerde.
#
# Uso: igual que el CLI real, pero con .\modal.ps1 en vez de `modal` / `python -m modal`
#   .\modal.ps1 deploy dashboard_refresh_modal.py
#   .\modal.ps1 run dashboard_refresh_modal.py

$env:MODAL_PROFILE = "anderlasacatalan"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host "[modal.ps1] usando perfil MODAL_PROFILE=$env:MODAL_PROFILE" -ForegroundColor DarkGray

python -m modal @args
