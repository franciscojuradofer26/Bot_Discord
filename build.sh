#!/usr/bin/env bash

# 1. Instalar las librerías de Python
pip install -r requirements.txt

# 2. Descargar la versión estática de FFmpeg para Linux (~70MB)
echo "Descargando FFmpeg para Linux..."
curl -L -o ffmpeg-linux.tar.xz https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz

# 3. Descomprimir el archivo
tar -xf ffmpeg-linux.tar.xz

# 4. Mover el ejecutable a la carpeta principal y darle permisos para que el bot pueda usarlo
mv ffmpeg-*-static/ffmpeg ./ffmpeg
chmod +x ./ffmpeg

echo "FFmpeg instalado correctamente."