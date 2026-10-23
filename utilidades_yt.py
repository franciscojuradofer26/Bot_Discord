import os
import shutil
import yt_dlp
import sys
import base64
import re
import http.cookiejar

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

MODO_DEBUG = os.getenv("YTDLP_DEBUG") == "1"


def _sanitizar_texto_cookies(texto_bruto: str) -> str:
    """
    Repara el formato Netscape si el navegador o Render convirtieron los tabuladores (\t) en espacios.
    Cada línea válida de cookies requiere exactamente 7 campos separados por tabuladores.
    """
    lineas_limpias = ['# Netscape HTTP Cookie File']
    for linea in texto_bruto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith('#'):
            continue
        partes = re.split(r'\s+', linea)
        if len(partes) >= 7:
            # Los primeros 6 campos están limpios, el valor puede contener espacios
            lineas_limpias.append('\t'.join(partes[:6] + [' '.join(partes[6:])]))
        elif '\t' in linea:
            lineas_limpias.append(linea)
    return '\n'.join(lineas_limpias) + '\n'


def _validar_cookies(ruta_archivo: str) -> tuple[int, bool]:
    """Comprueba si el archivo contiene cookies válidas y si incluye sesión de usuario de YouTube."""
    cj = http.cookiejar.MozillaCookieJar()
    try:
        cj.load(ruta_archivo, ignore_discard=True, ignore_expires=True)
        conteo = len(cj)
        nombres = {c.name for c in cj}
        # YouTube exige LOGIN_INFO o algún SAPISID para considerar la sesión como autenticada
        tiene_sesion = 'LOGIN_INFO' in nombres or any('SAPISID' in n for n in nombres)
        return conteo, tiene_sesion
    except Exception as e:
        print(f"⚠️ Error al parsear archivo de cookies: {e}")
        return 0, False


def _preparar_cookies():
    """Busca, sanitiza y valida las cookies de YouTube."""
    # 1. Variable de entorno
    env_cookies = os.getenv("YOUTUBE_COOKIES") or os.getenv("COOKIES_DATA")
    if env_cookies and env_cookies.strip():
        try:
            contenido = env_cookies.strip()
            if not contenido.startswith("# Netscape") and "\t" not in contenido:
                try:
                    contenido = base64.b64decode(contenido).decode('utf-8')
                except Exception:
                    pass
            contenido_reparado = _sanitizar_texto_cookies(contenido)
            with open(RUTA_COOKIES_TEMP, "w", encoding="utf-8") as f:
                f.write(contenido_reparado)
            return RUTA_COOKIES_TEMP
        except Exception as e:
            print(f"⚠️ Error procesando YOUTUBE_COOKIES: {e}")

    # 2. Secret File de Render (/etc/secrets/cookies.txt)
    if os.path.exists(RUTA_COOKIES_SECRETO):
        try:
            with open(RUTA_COOKIES_SECRETO, "r", encoding="utf-8", errors="ignore") as f:
                contenido_reparado = _sanitizar_texto_cookies(f.read())
            with open(RUTA_COOKIES_TEMP, "w", encoding="utf-8") as f:
                f.write(contenido_reparado)
            return RUTA_COOKIES_TEMP
        except Exception as e:
            print(f"⚠️ Error leyendo /etc/secrets/cookies.txt: {e}")

    # 3. Archivo cookies.txt local
    elif os.path.exists(RUTA_COOKIES_LOCAL):
        try:
            with open(RUTA_COOKIES_LOCAL, "r", encoding="utf-8", errors="ignore") as f:
                contenido_reparado = _sanitizar_texto_cookies(f.read())
            with open(RUTA_COOKIES_TEMP, "w", encoding="utf-8") as f:
                f.write(contenido_reparado)
            return RUTA_COOKIES_TEMP
        except Exception as e:
            print(f"⚠️ Error leyendo cookies locales: {e}")

    return None


ARCHIVO_COOKIES = _preparar_cookies()
TOTAL_COOKIES, SESION_VALIDA = _validar_cookies(ARCHIVO_COOKIES) if ARCHIVO_COOKIES else (0, False)
HAY_COOKIES = ARCHIVO_COOKIES is not None and TOTAL_COOKIES > 0


def _detectar_js_runtime():
    """Detecta un runtime de JS (Deno o Node) para que yt-dlp descifre las firmas de YouTube."""
    if os.path.exists(RUTA_DENO_LOCAL):
        return 'deno', RUTA_DENO_LOCAL
    deno_sistema = shutil.which("deno")
    if deno_sistema:
        return 'deno', deno_sistema
    node_sistema = shutil.which("node") or shutil.which("nodejs")
    if node_sistema:
        return 'node', node_sistema
    return None, None


JS_TIPO, JS_PATH = _detectar_js_runtime()

# Diagnóstico claro en los logs de Render
print("----------------------------------------")
print(f"🎬 yt-dlp versión: {yt_dlp.version.__version__}")
if JS_TIPO and JS_PATH:
    print(f"🦕 JS Runtime ({JS_TIPO}): encontrado ({JS_PATH})")
else:
    print("⚠️ JS Runtime: NO encontrado")

if HAY_COOKIES and SESION_VALIDA:
    print(f"🍪 Cookies: ¡Sesión activa detectada! ({TOTAL_COOKIES} cookies cargadas)")
elif HAY_COOKIES and not SESION_VALIDA:
    print(f"⚠️ Cookies: Se cargaron {TOTAL_COOKIES} cookies pero NO contienen sesión activa de YouTube (falta LOGIN_INFO / SAPISID).")
else:
    print("ℹ️ Cookies: No hay cookies activas. Operando en modo móvil anónimo (Android).")

print(f"🐞 Modo debug yt-dlp: {'activado' if MODO_DEBUG else 'desactivado'}")
print("----------------------------------------")


def opciones_yt(**extra):
    """
    Opciones de yt-dlp optimizadas dinámicamente según si hay sesión iniciada o modo anónimo.
    """
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

    # Si hay cookies con sesión válida de YouTube, usamos clientes de navegador autenticados
    if HAY_COOKIES and SESION_VALIDA and ARCHIVO_COOKIES:
        opciones['cookiefile'] = ARCHIVO_COOKIES
        opciones['extractor_args'] = {
            'youtube': {
                'player_client': ['web_embedded', 'tv_downgraded', 'web', 'android']
            }
        }
    else:
        # Si NO hay cookies o son anónimas, usamos el cliente Android que elude el muro anti-bot de escritorio
        opciones['extractor_args'] = {
            'youtube': {
                'player_client': ['android', 'android_vr'],
                'player_skip': ['webpage']
            }
        }

    opciones.update(extra)
    return opciones


def opciones_yt_fallback(**extra):
    """Estrategia de respaldo en caso de fallo del método principal."""
    opciones = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': not MODO_DEBUG,
        'verbose': MODO_DEBUG,
        'no_warnings': False,
        'default_search': 'ytsearch',
        'remote_components': ['ejs:github'],
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'visionos', 'web']
            }
        }
    }

    if JS_TIPO and JS_PATH:
        opciones['js_runtimes'] = {JS_TIPO: {'path': JS_PATH}}

    if HAY_COOKIES and SESION_VALIDA and ARCHIVO_COOKIES:
        opciones['cookiefile'] = ARCHIVO_COOKIES

    opciones.update(extra)
    return opciones
