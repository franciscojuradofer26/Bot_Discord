import os

# Deno se instala en build.sh dentro de la carpeta del proyecto (.deno/bin/deno)
RUTA_DENO = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".deno", "bin", "deno")

# Si subes un cookies.txt como "Secret File" en Render, aparece aquí
RUTA_COOKIES = "/etc/secrets/cookies.txt"


def opciones_yt(**extra):
    """Opciones comunes de yt-dlp para todo el bot. Pasa claves extra para sobrescribir."""
    opciones = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        # Dejamos los avisos activados para verlos en los logs de Render
        'no_warnings': False,
    }

    if os.path.exists(RUTA_DENO):
        opciones['js_runtimes'] = {'deno': {'path': RUTA_DENO}}

    if os.path.exists(RUTA_COOKIES):
        opciones['cookiefile'] = RUTA_COOKIES

    opciones.update(extra)
    return opciones
