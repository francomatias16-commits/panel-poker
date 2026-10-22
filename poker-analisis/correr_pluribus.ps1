# Corre la validacion temporal y la carga a Supabase con el dataset PHH de Pluribus.
# Uso (PowerShell, desde la carpeta del proyecto):
#   .\correr_pluribus.ps1            -> validacion temporal + carga en modo --simular (no toca la base)
#   .\correr_pluribus.ps1 -Cargar    -> ademas, sube las manos a Supabase (pide DATABASE_URL y POKER_SAL)
#   .\correr_pluribus.ps1 -Recalibrar -SoloValidar  -> solo validacion temporal con recalibracion
#   -Datos <carpeta>  -> reutiliza un dataset ya descargado (la carpeta que contiene data\pluribus)
# Requiere Python 3 y Git. Si PowerShell bloquea el script:
#   Set-ExecutionPolicy -Scope Process Bypass
param([switch]$Cargar, [switch]$Recalibrar, [switch]$SoloValidar, [int]$Pliegues = 5, [string]$Datos = "")

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { throw "No encuentro Python 3." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "No encuentro Git." }

$dataset = if ($Datos) { $Datos } else { Join-Path $PSScriptRoot "datos\phh-dataset" }
$pluribus = Join-Path $dataset "data\pluribus"
if (-not (Test-Path $pluribus)) {
    Write-Host "Clonando el dataset PHH (una sola vez)..."
    git clone --depth 1 https://github.com/uoftcprg/phh-dataset.git $dataset
}
if (-not (Test-Path $pluribus)) { throw "No aparecio la carpeta data\pluribus en el dataset." }

Write-Host "`n== Validacion temporal con datos reales =="
if ($Recalibrar) { & $py scripts/validar_temporal.py $pluribus $Pliegues --recalibrar } else { & $py scripts/validar_temporal.py $pluribus $Pliegues }
if ($SoloValidar) { return }

Write-Host "`n== Carga en modo simulacion =="
& $py scripts/cargar_supabase.py --formato phh --ruta $pluribus --fuente pluribus --licencia "CC BY 4.0" --simular

if ($Cargar) {
    & $py -m pip install "psycopg[binary]"
    $url = Read-Host "DATABASE_URL (Supabase > Settings > Database)" -AsSecureString
    $sal = Read-Host "POKER_SAL (siempre la misma; guardala en un gestor de contrasenas)" -AsSecureString
    $env:DATABASE_URL = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($url))
    $env:POKER_SAL = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sal))
    try {
        Write-Host "`n== Carga real a Supabase =="
        & $py scripts/cargar_supabase.py --formato phh --ruta $pluribus --fuente pluribus --licencia "CC BY 4.0"
    } finally {
        Remove-Item Env:\DATABASE_URL, Env:\POKER_SAL -ErrorAction SilentlyContinue
    }
}
