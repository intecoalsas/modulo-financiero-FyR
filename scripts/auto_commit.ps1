# Auto-commit y push diario para modulo-financiero-FyR
# Se ejecuta cada dia a las 11:59 PM via Tarea Programada de Windows.
$repo = "C:\Users\ASUS\Documents\sistemas_informes_FyR"
Set-Location -LiteralPath $repo

# ¿Hay cambios?
$staged = git status --porcelain
if ([string]::IsNullOrWhiteSpace($staged)) {
    exit 0
}

# Agregar todos los cambios
git add -A

# Mensaje de commit con fecha
$fecha = Get-Date -Format "yyyy-MM-dd HH:mm"
git commit -m "auto: respaldo automatico $fecha"

# Subir al repositorio
git push origin main 2>&1 | Out-Null
