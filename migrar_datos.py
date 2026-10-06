import sqlite3
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# 1. Conectar a local y nube
sqlite_conn = sqlite3.connect('biblioteca.db')
sqlite_cursor = sqlite_conn.cursor()

pg_conn = psycopg2.connect(os.getenv("DATABASE_URL"))
pg_conn.autocommit = True
pg_cursor = pg_conn.cursor()

# 2. Crear la tabla en PostgreSQL con la misma estructura que tenías
pg_cursor.execute("""
    CREATE TABLE IF NOT EXISTS canciones (
        enlace TEXT PRIMARY KEY,
        nombre TEXT,
        artista TEXT
    )
""")

# 3. Extraer y migrar datos
sqlite_cursor.execute("SELECT enlace, nombre, artista FROM canciones")
filas = sqlite_cursor.fetchall()

exitos = 0
for fila in filas:
    try:
        # En PostgreSQL se usa %s en lugar de ?
        pg_cursor.execute("INSERT INTO canciones (enlace, nombre, artista) VALUES (%s, %s, %s)", fila)
        exitos += 1
    except psycopg2.IntegrityError:
        pass # Ignora si por algún motivo ya estuviera registrada

print(f"✅ ¡Migración completada! Se han movido {exitos} canciones a la nube.")

sqlite_conn.close()
pg_conn.close()