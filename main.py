import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from keep_alive import keep_alive, cambiar_estado, actualizar_info

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

class MiBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        await self.load_extension('cogs.admin')
        await self.load_extension('cogs.musica')

    async def on_ready(self):
        cambiar_estado("encendido")
        actualizar_info(servidores=len(self.guilds))
        print("----------------------------------------")
        print(f'🟢 ¡Conectado exitosamente como {self.user}!')
        try:
            sincronizados = await self.tree.sync()
            print(f'🔄 Se han sincronizado {len(sincronizados)} comando(s) de barra.')
        except Exception as e:
            print(f'❌ Error al sincronizar comandos: {e}')
        print("----------------------------------------")

bot = MiBot()

# Manejador de errores global
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.CheckFailure):
        await interaction.response.send_message("❌ Alto ahí. No tienes permisos de administrador para usar este comando.", ephemeral=True)
    else:
        print(f"Error inesperado: {error}")

if __name__ == '__main__':
    if not TOKEN:
        print("⚠️ ERROR: No se ha encontrado el DISCORD_TOKEN en las variables de entorno.")
        cambiar_estado("error")
    else:
        keep_alive()
        try:
            bot.run(TOKEN)
        except Exception as e:
            print(f"Error fatal al arrancar bot de Discord: {e}")
            cambiar_estado("error")
