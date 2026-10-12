#!/usr/bin/env bash
# Si algún paso falla, el build se para y Render te avisa
set -e

# 1. Instalar las librerías de Python
# (ffmpeg ya viene incluido en el paquete imageio-ffmpeg, no hace falta descargarlo)
pip install --no-cache-dir -U -r requirements.txt

# 2. Instalar Deno (motor de JavaScript que yt-dlp necesita para YouTube)
#    Se instala dentro de la carpeta del proyecto para que siga disponible al arrancar el bot
echo "Instalando Deno..."
curl -fsSL https://deno.land/install.sh | DENO_INSTALL="$(pwd)/.deno" sh -s -- -y
./.deno/bin/deno --version

echo "Build completado correctamente."
