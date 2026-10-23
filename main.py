import discord
from discord.ext import commands
import os
import asyncio
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

def crear_bot():
    bot = MiBot()

    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        if isinstance(error, discord.app_commands.CheckFailure):
            await interaction.response.send_message("❌ Alto ahí. No tienes permisos de administrador para usar este comando.", ephemeral=True)
        else:
            print(f"Error inesperado en comando: {error}")

    return bot

async def main():
    if not TOKEN:
        print("⚠️ ERROR: No se ha encontrado el DISCORD_TOKEN en las variables de entorno.")
        cambiar_estado("error")
        # Mantenemos el proceso vivo para que Render no haga bucle de reinicios agresivos
        while True:
            await asyncio.sleep(3600)

    keep_alive()

    reintentos_429 = 0
    while True:
        bot = crear_bot()
        try:
            cambiar_estado("iniciando")
            async with bot:
                await bot.start(TOKEN)
                reintentos_429 = 0
        except discord.errors.HTTPException as e:
            if e.status == 429:
                reintentos_429 += 1
                # Espera exponencial: 60s, 120s, 240s... máximo 10 minutos
                tiempo_espera = min(60 * (2 ** (reintentos_429 - 1)), 600)
                cambiar_estado("ratelimit")
                print(f"⚠️ Rate limit 429 de Discord (Cloudflare). Pausando {tiempo_espera}s para permitir enfriamiento de la IP...")
                await asyncio.sleep(tiempo_espera)
            else:
                cambiar_estado("error")
                print(f"Error HTTP de Discord ({e.status}): {e}")
                await asyncio.sleep(20)
        except Exception as e:
            cambiar_estado("error")
            print(f"Error en bot de Discord: {e}")
            await asyncio.sleep(20)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot apagado manualmente.")
