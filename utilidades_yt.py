import os
import shutil
import yt_dlp

# Deno se instala en build.sh dentro de la carpeta del proyecto (.deno/bin/deno)
RUTA_DENO = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".deno", "bin", "deno")

# Si subes un cookies.txt como "Secret File" en Render, aparece aquí
RUTA_COOKIES_SECRETO = "/etc/secrets/cookies.txt"
# yt-dlp reescribe el archivo de cookies al usarlo, y /etc/secrets es de solo lectura,
# así que trabajamos con una copia
RUTA_COOKIES = "/tmp/cookies.txt"

# Pon la variable de entorno YTDLP_DEBUG=1 en Render para ver TODO lo que hace yt-dlp
MODO_DEBUG = os.getenv("YTDLP_DEBUG") == "1"


def _preparar_cookies():
    if os.path.exists(RUTA_COOKIES_SECRETO):
        try:
            shutil.copy(RUTA_COOKIES_SECRETO, RUTA_COOKIES)
            return True
        except Exception as e:
            print(f"⚠️ No he podido copiar las cookies: {e}")
    return False


HAY_COOKIES = _preparar_cookies()

# Diagnóstico al arrancar: aparece en los logs de Render
print("----------------------------------------")
print(f"🎬 yt-dlp versión: {yt_dlp.version.__version__}")
print(f"🦕 Deno: {'encontrado' if os.path.exists(RUTA_DENO) else 'NO encontrado'} ({RUTA_DENO})")
print(f"🍪 Cookies: {'cargadas' if HAY_COOKIES else 'no hay'}")
print(f"🐞 Modo debug yt-dlp: {'activado' if MODO_DEBUG else 'desactivado'}")
print("----------------------------------------")


def opciones_yt(**extra):
    """Opciones comunes de yt-dlp para todo el bot. Pasa claves extra para sobrescribir."""
    opciones = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': not MODO_DEBUG,
        'verbose': MODO_DEBUG,
        'no_warnings': False,
    }

    if os.path.exists(RUTA_DENO):
        opciones['js_runtimes'] = {'deno': {'path': RUTA_DENO}}

    if HAY_COOKIES:
        opciones['cookiefile'] = RUTA_COOKIES

    opciones.update(extra)
    return opciones
