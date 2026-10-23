import os
import shutil
import yt_dlp
import sys
import base64

# Evita fallos de codificación con emojis en consolas de Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Deno se instala en build.sh dentro de la carpeta del proyecto (.deno/bin/deno)
RUTA_DENO_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".deno", "bin", "deno")

# Rutas para cookies de YouTube
RUTA_COOKIES_SECRETO = "/etc/secrets/cookies.txt"
RUTA_COOKIES_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
RUTA_COOKIES_TEMP = "/tmp/cookies.txt" if os.name != 'nt' else os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_cookies.txt")

# Modo debug con YTDLP_DEBUG=1
MODO_DEBUG = os.getenv("YTDLP_DEBUG") == "1"


def _preparar_cookies():
    """
    Prepara el archivo de cookies para yt-dlp buscando en:
    1. Variable de entorno YOUTUBE_COOKIES o COOKIES_DATA (texto o base64).
    2. Secret File de Render (/etc/secrets/cookies.txt).
    3. Archivo local cookies.txt (para pruebas en tu PC).
    """
    # 1. Variable de entorno (muy cómodo en Render)
    env_cookies = os.getenv("YOUTUBE_COOKIES") or os.getenv("COOKIES_DATA")
    if env_cookies and env_cookies.strip():
        try:
            contenido = env_cookies.strip()
            # Si viene en base64, lo decodificamos
            if not contenido.startswith("# Netscape") and "\t" not in contenido:
                try:
                    contenido = base64.b64decode(contenido).decode('utf-8')
                except Exception:
                    pass
            with open(RUTA_COOKIES_TEMP, "w", encoding="utf-8") as f:
                f.write(contenido)
            return RUTA_COOKIES_TEMP
        except Exception as e:
            print(f"⚠️ Error cargando cookies desde variable de entorno: {e}")

    # 2. Secret File de Render (/etc/secrets/cookies.txt)
    if os.path.exists(RUTA_COOKIES_SECRETO):
        try:
            shutil.copy(RUTA_COOKIES_SECRETO, RUTA_COOKIES_TEMP)
            return RUTA_COOKIES_TEMP
        except Exception as e:
            print(f"⚠️ No se pudo copiar cookies de Render: {e}")

    # 3. Archivo cookies.txt local para desarrollo en PC
    elif os.path.exists(RUTA_COOKIES_LOCAL):
        try:
            shutil.copy(RUTA_COOKIES_LOCAL, RUTA_COOKIES_TEMP)
            return RUTA_COOKIES_TEMP
        except Exception as e:
            print(f"⚠️ No se pudo copiar cookies locales: {e}")

    return None


ARCHIVO_COOKIES = _preparar_cookies()
HAY_COOKIES = ARCHIVO_COOKIES is not None


def _detectar_js_runtime():
    """Detecta un runtime de JS (Deno o Node) para que yt-dlp descifre las firmas de YouTube."""
    # 1. Deno descargado por build.sh
    if os.path.exists(RUTA_DENO_LOCAL):
        return 'deno', RUTA_DENO_LOCAL
    # 2. Deno en PATH
    deno_sistema = shutil.which("deno")
    if deno_sistema:
        return 'deno', deno_sistema
    # 3. Node en PATH
    node_sistema = shutil.which("node") or shutil.which("nodejs")
    if node_sistema:
        return 'node', node_sistema
    return None, None


JS_TIPO, JS_PATH = _detectar_js_runtime()

# Diagnóstico de arranque en los logs
print("----------------------------------------")
print(f"🎬 yt-dlp versión: {yt_dlp.version.__version__}")
if JS_TIPO and JS_PATH:
    print(f"🦕 JS Runtime ({JS_TIPO}): encontrado ({JS_PATH})")
else:
    print("⚠️ JS Runtime: NO encontrado (YouTube podría requerir Deno o Node)")
print(f"🍪 Cookies: {'cargadas (' + ARCHIVO_COOKIES + ')' if HAY_COOKIES else 'no hay (recomendadas para servidores en la nube)'}")
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
        'default_search': 'ytsearch',
        'remote_components': ['ejs:github'],
    }

    if JS_TIPO and JS_PATH:
        opciones['js_runtimes'] = {JS_TIPO: {'path': JS_PATH}}

    if HAY_COOKIES and ARCHIVO_COOKIES:
        opciones['cookiefile'] = ARCHIVO_COOKIES

    opciones.update(extra)
    return opciones
