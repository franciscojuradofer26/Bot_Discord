import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import re
import yt_dlp

# Configuración de la BBDD para este módulo
conexion = sqlite3.connect('biblioteca.db')
cursor = conexion.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS canciones (
        enlace TEXT PRIMARY KEY,
        nombre TEXT,
        artista TEXT
    )
''')
conexion.commit()

ADMIN_IDS = [1014250698612944976,1140072371500363887,472140234822516743,
            806948074287136820,1345376311283159052,1016855844312326194,
            825133272617975829,1383012295600504966,1118290829304406141,
            1135693655353610321,956949020318785576,797108474805878784,
            882671505056628776]

def es_admin():
    def predicate(interaction: discord.Interaction):
        return interaction.user.id in ADMIN_IDS
    return app_commands.check(predicate)

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="register", description="Registra una canción custom en la base de datos")
    @app_commands.describe(
        nombre="Ej: Columbia",
        artista="Ej: Quevedo",
        enlace="El enlace completo de YouTube"
    )
    @es_admin()
    async def register(self, interaction: discord.Interaction, nombre: str, artista: str, enlace: str):
        await interaction.response.defer(ephemeral=True)

        patron_yt = r'^(https?\:\/\/)?(www\.|music\.)?(youtube\.com|youtu\.be)\/.*$'
        if not re.match(patron_yt, enlace):
            await interaction.followup.send("❌ **Error:** El enlace no tiene un formato válido de YouTube.")
            return

        opciones_prueba = {
            'quiet': True, 
            'simulate': True, 
            'noplaylist': True,
            'extractor_args': {'youtube': ['player_client=android']}
        }
        try:
            with yt_dlp.YoutubeDL(opciones_prueba) as ydl:
                ydl.extract_info(enlace, download=False)
        except Exception:
            await interaction.followup.send("❌ **Error:** El enlace tiene formato válido, pero YouTube lo ha borrado, es privado o está bloqueado.")
            return

        try:
            cursor.execute("INSERT INTO canciones (enlace, nombre, artista) VALUES (?, ?, ?)", (enlace, nombre, artista))
            conexion.commit()
            await interaction.followup.send(f"✅ ¡Éxito! **{nombre}** de **{artista}** guardada en tu base de datos.")
        except sqlite3.IntegrityError:
            await interaction.followup.send("⚠️ Esa canción (enlace) ya estaba registrada.")

# Función obligatoria para que main.py pueda cargar este archivo
async def setup(bot):
    await bot.add_cog(Admin(bot))