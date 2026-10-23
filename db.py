import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

_conexion = None

def obtener_conexion():
    """Obtiene una conexión activa a PostgreSQL, reconectando automáticamente si es necesario."""
    global _conexion
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None

    # Intentamos comprobar si la conexión sigue viva
    if _conexion is not None and _conexion.closed == 0:
        try:
            with _conexion.cursor() as cur:
                cur.execute("SELECT 1;")
            return _conexion
        except Exception:
            try:
                _conexion.close()
            except Exception:
                pass
            _conexion = None

    # Reconexión
    try:
        _conexion = psycopg2.connect(db_url)
        _conexion.autocommit = True
        return _conexion
    except Exception as e:
        print(f"⚠️ Error conectando a PostgreSQL: {e}")
        _conexion = None
        return None

def inicializar_db():
    """Crea la tabla de canciones si no existe."""
    conn = obtener_conexion()
    if not conn:
        return
    try:
        with conn.cursor() as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS canciones (
                    enlace TEXT PRIMARY KEY,
                    nombre TEXT,
                    artista TEXT
                )
            ''')
    except Exception as e:
        print(f"⚠️ Error inicializando tabla canciones: {e}")

def buscar_canciones(termino: str, limite: int = 25):
    """Busca canciones registradas por nombre o artista."""
    conn = obtener_conexion()
    if not conn:
        return []
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT nombre, artista, enlace FROM canciones WHERE nombre ILIKE %s OR artista ILIKE %s LIMIT %s",
                (f"%{termino}%", f"%{termino}%", limite)
            )
            return cursor.fetchall()
    except Exception as e:
        print(f"⚠️ Error buscando canciones en BBDD: {e}")
        return []

def registrar_cancion(enlace: str, nombre: str, artista: str):
    """Registra una canción custom en la base de datos."""
    conn = obtener_conexion()
    if not conn:
        raise RuntimeError("No hay conexión con la base de datos PostgreSQL.")
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO canciones (enlace, nombre, artista) VALUES (%s, %s, %s)",
            (enlace, nombre, artista)
        )
