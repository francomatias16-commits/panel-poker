#!/bin/sh
# Inicia el panel de estudio (necesita Python 3.11 o mas nuevo)
exec python3 "$(dirname "$0")/iniciar.py" "$@"
