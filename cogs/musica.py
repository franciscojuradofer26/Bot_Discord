import discord
import random
import os
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import psycopg2
import re
import yt_dlp
from ytmusicapi import YTMusic
from dotenv import load_dotenv

load_dotenv()
ytmusic = YTMusic()

# Conexión PostgreSQL
conexion = psycopg2.connect(os.getenv("DATABASE_URL"))
conexion.autocommit = True
cursor = conexion.cursor()

def extraer_video_id(url_o_id):
    if not url_o_id: return ""
    match = re.search(r'(?:v=|\/shorts\/|\/youtu\.be\/|\/v\/|\/embed\/|&v=)([\w-]{11})', url_o_id)
    if match: return match.group(1)
    return url_o_id[:100]

# =========================================================
# INTERFAZ DE BOTONES (UI)
# =========================================================
class ReproductorView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Pausar", style=discord.ButtonStyle.primary, emoji="⏸️")
    async def boton_pausa(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Canción pausada.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No hay nada sonando ahora mismo.", ephemeral=True)

    @discord.ui.button(label="Reanudar", style=discord.ButtonStyle.success, emoji="▶️")
    async def boton_reanudar(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Canción reanudada.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ La música no estaba pausada.", ephemeral=True)

    @discord.ui.button(label="Saltar", style=discord.ButtonStyle.danger, emoji="⏭️")
    async def boton_saltar(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop() 
            await interaction.response.send_message("⏭️ Canción saltada. Cargando la siguiente...", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No hay nada sonando para saltar.", ephemeral=True)

# =========================================================
# MOTOR PRINCIPAL DE MÚSICA
# =========================================================
class Musica(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.temporizadores = {} 
        self.colas = {} 
        self.control_inactividad.start() 

    async def reproducir_siguiente(self, guild_id, vc, canal_texto):
        if guild_id in self.colas and len(self.colas[guild_id]) > 0:
            siguiente_cancion = self.colas[guild_id].pop(0) 
            url_youtube = siguiente_cancion['url']
            titulo = siguiente_cancion['titulo']
            opciones_ydl = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'no_warnings': True}
            
            try:
                def extraer():
                    with yt_dlp.YoutubeDL(opciones_ydl) as ydl:
                        return ydl.extract_info(url_youtube, download=False)
                
                info = await asyncio.to_thread(extraer)
                url_audio = info['url']

                # --- CREAR LA TARJETA VISUAL (EMBED) ---
                thumbnail = info.get('thumbnail')
                duracion = info.get('duration', 0)
                minutos, segundos = divmod(duracion, 60)
                texto_duracion = f"{int(minutos)}:{int(segundos):02d}" if duracion else "Desconocida / Directo"

                embed = discord.Embed(title="💿 Sonando ahora", description=f"**{titulo}**", color=discord.Color.purple())
                if thumbnail:
                    embed.set_image(url=thumbnail)
                embed.add_field(name="⏳ Duración", value=texto_duracion)
                # ---------------------------------------

                headers = info.get('http_headers', {})
                user_agent = headers.get('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')

                opciones_ffmpeg = {
                    'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -user_agent "{user_agent}"', 
                    'options': '-vn'
                }
                fuente_audio = discord.FFmpegPCMAudio(url_audio, executable="./ffmpeg.exe", **opciones_ffmpeg)

                def despues_de_reproducir(error):
                    if error: print(f"Error FFmpeg: {error}")
                    coro = self.reproducir_siguiente(guild_id, vc, canal_texto)
                    asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

                vc.play(fuente_audio, after=despues_de_reproducir)
                
                # Enviamos el embed en lugar del texto simple, ¡y le pegamos los botones!
                await canal_texto.send(embed=embed, view=ReproductorView())
                
            except Exception as e:
                print(f"Error extrayendo audio en cola: {e}")
                await self.reproducir_siguiente(guild_id, vc, canal_texto)

    async def sugerencias_canciones(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        try:
            if not current.strip(): return []
            opciones = []
            try:
                cursor.execute("SELECT nombre, artista, enlace FROM canciones WHERE nombre ILIKE %s OR artista ILIKE %s", (f"%{current}%", f"%{current}%"))
                for fila in cursor.fetchall():
                    nombre_db, artista_db, enlace_db = fila
                    texto_visual = f"💾 {nombre_db} - {artista_db}"
                    id_limpia = extraer_video_id(enlace_db)
                    if id_limpia: opciones.append(app_commands.Choice(name=texto_visual[:100], value=id_limpia))
            except Exception as e: print(f"⚠️ Error BBDD: {e}")

            if len(opciones) >= 25: return opciones[:25]

            try:
                limite_restante = 25 - len(opciones)
                resultados_yt = await asyncio.wait_for(
                    asyncio.to_thread(ytmusic.search, current, filter="songs", limit=limite_restante), timeout=1.0)
                for res in resultados_yt:
                    texto_yt = f"🎵 {res['title']} - {res['artists'][0]['name']}"
                    video_id_yt = res.get('videoId', '')
                    if video_id_yt: opciones.append(app_commands.Choice(name=texto_yt[:100], value=str(video_id_yt)))
            except asyncio.TimeoutError: pass
            except Exception as e: print(f"⚠️ Error YT Music: {e}")

            return opciones[:25]
        except Exception: return []

    @app_commands.command(name="play", description="Busca y reproduce música de YT Music")
    @app_commands.autocomplete(cancion=sugerencias_canciones)
    async def play(self, interaction: discord.Interaction, cancion: str):
        await interaction.response.defer()
        if not interaction.user.voice:
            await interaction.followup.send("❌ ¡Tienes que meterte en un canal de voz primero!")
            return

        canal_voz = interaction.user.voice.channel
        url_youtube = f"https://www.youtube.com/watch?v={cancion}"
        opciones_ydl = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'no_warnings': True}

        try:
            vc = interaction.guild.voice_client
            if not vc: vc = await canal_voz.connect()
            else: await vc.move_to(canal_voz)

            def extraer():
                with yt_dlp.YoutubeDL(opciones_ydl) as ydl: 
                    return ydl.extract_info(url_youtube, download=False)
            
            info = await asyncio.to_thread(extraer)
            url_audio = info['url']
            titulo = info.get('title', 'Canción desconocida')

            headers = info.get('http_headers', {})
            user_agent = headers.get('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')

            guild_id = interaction.guild.id
            if guild_id not in self.colas: self.colas[guild_id] = []

            if vc.is_playing() or vc.is_paused():
                self.colas[guild_id].append({'url': url_youtube, 'titulo': titulo})
                await interaction.followup.send(f"📝 Añadida a la cola: **{titulo}** (Posición: {len(self.colas[guild_id])})")
            else:
                # --- CREAR LA TARJETA VISUAL (EMBED) ---
                thumbnail = info.get('thumbnail')
                duracion = info.get('duration', 0)
                minutos, segundos = divmod(duracion, 60)
                texto_duracion = f"{int(minutos)}:{int(segundos):02d}" if duracion else "Desconocida / Directo"

                embed = discord.Embed(title="💿 Poniendo temazo", description=f"**{titulo}**", color=discord.Color.purple())
                if thumbnail:
                    embed.set_image(url=thumbnail)
                embed.add_field(name="⏳ Duración", value=texto_duracion)
                # ---------------------------------------

                opciones_ffmpeg = {
                    'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -user_agent "{user_agent}"', 
                    'options': '-vn'
                }
                fuente_audio = discord.FFmpegPCMAudio(url_audio, executable="./ffmpeg.exe", **opciones_ffmpeg)
                canal_texto = interaction.channel

                def despues_de_reproducir(error):
                    coro = self.reproducir_siguiente(guild_id, vc, canal_texto)
                    asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

                vc.play(fuente_audio, after=despues_de_reproducir)
                
                # Usamos el followup con el embed
                await interaction.followup.send(embed=embed, view=ReproductorView())

        except Exception as e:
            await interaction.followup.send(f"❌ Ocurrió un error: {e}")

    @app_commands.command(name="queue", description="Muestra las próximas canciones en la lista de espera")
    async def queue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id not in self.colas or len(self.colas[guild_id]) == 0:
            await interaction.response.send_message("📭 La cola está vacía ahora mismo.")
            return

        lista = self.colas[guild_id]
        texto = "📋 **Lista de Reproducción Actual:**\n\n"
        for i, cancion in enumerate(lista[:15]): texto += f"**{i+1}.** {cancion['titulo']}\n"
        if len(lista) > 15: texto += f"\n*... y {len(lista) - 15} canciones más esperando.*"
        await interaction.response.send_message(texto)

    @app_commands.command(name="radio", description="Genera una radio aleatoria basada en YouTube Music")
    @app_commands.describe(criterios="Ej: Bad Bunny, Eladio Carrion")
    async def radio(self, interaction: discord.Interaction, criterios: str):
        await interaction.response.defer()
        if not interaction.user.voice:
            await interaction.followup.send("❌ ¡Tienes que meterte en un canal de voz primero!")
            return

        canal_voz = interaction.user.voice.channel
        try:
            resultados = await asyncio.to_thread(ytmusic.search, criterios, filter="songs", limit=50)
            if not resultados:
                await interaction.followup.send("❌ No he encontrado canciones para esos artistas.")
                return

            random.shuffle(resultados) 
            guild_id = interaction.guild.id
            if guild_id not in self.colas: self.colas[guild_id] = []

            palabras_prohibidas = ['live', 'en vivo', 'superbowl', 'super bowl', 'show', 'performance', 'concierto', 'concert', 'mix']
            canciones_filtradas = 0
            
            for res in resultados:
                titulo_cancion = res.get('title', '').lower()
                es_directo = any(palabra in titulo_cancion for palabra in palabras_prohibidas)
                duracion = res.get('duration_seconds', 0)
                es_muy_larga = duracion > 600 

                video_id = res.get('videoId')
                if video_id and not es_directo and not es_muy_larga:
                    url_video = f"https://www.youtube.com/watch?v={video_id}"
                    titulo = f"{res['title']} - {res['artists'][0]['name']}"
                    self.colas[guild_id].append({'url': url_video, 'titulo': titulo})
                    canciones_filtradas += 1

            await interaction.followup.send(f"📻 **¡Modo Radio YT Activado!** He filtrado y añadido **{canciones_filtradas}** temazos basados en: *{criterios}*")

            vc = interaction.guild.voice_client 
            if not vc: vc = await canal_voz.connect()
            if vc and not vc.is_playing() and not vc.is_paused():
                await self.reproducir_siguiente(guild_id, vc, interaction.channel)

        except Exception as e:
            await interaction.followup.send(f"❌ Ocurrió un error sintonizando la radio: {e}")

    @app_commands.command(name="playlist", description="Carga una lista de reproducción entera de YouTube")
    @app_commands.describe(enlace="El enlace de la playlist de YouTube")
    async def playlist(self, interaction: discord.Interaction, enlace: str):
        await interaction.response.defer()
        if not interaction.user.voice:
            await interaction.followup.send("❌ ¡Tienes que meterte en un canal de voz primero!")
            return

        canal_voz = interaction.user.voice.channel
        opciones_playlist = {'extract_flat': 'in_playlist', 'quiet': True, 'no_warnings': True}

        try:
            def extraer_pl():
                with yt_dlp.YoutubeDL(opciones_playlist) as ydl: return ydl.extract_info(enlace, download=False)
            
            info = await asyncio.to_thread(extraer_pl)
            if 'entries' not in info:
                await interaction.followup.send("❌ Eso no parece ser una playlist válida.")
                return
                
            canciones = list(info['entries'])
            if not canciones:
                await interaction.followup.send("❌ La playlist está vacía o es privada.")
                return

            guild_id = interaction.guild.id
            if guild_id not in self.colas: self.colas[guild_id] = []

            for cancion in canciones:
                url_video = cancion.get('url')
                if url_video and not url_video.startswith('http'): url_video = f"https://www.youtube.com/watch?v={url_video}"
                self.colas[guild_id].append({'url': url_video, 'titulo': cancion.get('title', 'Canción de la playlist')})

            await interaction.followup.send(f"📚 ¡Éxito! Se han añadido **{len(canciones)}** canciones a la cola.")

            vc = interaction.guild.voice_client 
            if not vc: vc = await canal_voz.connect()
            if vc and not vc.is_playing() and not vc.is_paused():
                await self.reproducir_siguiente(guild_id, vc, interaction.channel)

        except Exception as e:
            await interaction.followup.send(f"❌ Ocurrió un error leyendo la playlist: {e}")

    @app_commands.command(name="playnext", description="Pone una canción la primera de la cola (Pase VIP)")
    @app_commands.autocomplete(cancion=sugerencias_canciones)
    async def playnext(self, interaction: discord.Interaction, cancion: str):
        await interaction.response.defer()
        if not interaction.user.voice:
            await interaction.followup.send("❌ ¡Tienes que meterte en un canal de voz primero!")
            return

        canal_voz = interaction.user.voice.channel
        url_youtube = f"https://www.youtube.com/watch?v={cancion}"
        
        opciones_ydl = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'no_warnings': True}

        try:
            vc = interaction.guild.voice_client
            if not vc: vc = await canal_voz.connect()
            else: await vc.move_to(canal_voz)

            def extraer():
                with yt_dlp.YoutubeDL(opciones_ydl) as ydl: 
                    return ydl.extract_info(url_youtube, download=False)
            
            info = await asyncio.to_thread(extraer)
            url_audio = info['url']
            titulo = info.get('title', 'Canción desconocida')

            headers = info.get('http_headers', {})
            user_agent = headers.get('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')

            guild_id = interaction.guild.id
            if guild_id not in self.colas: self.colas[guild_id] = []

            if vc.is_playing() or vc.is_paused():
                # --- LA MAGIA DEL PLAYNEXT ---
                # En lugar de .append() (que lo manda al final), usamos .insert(0)
                # Esto empuja la canción a la primera posición de la lista de espera
                self.colas[guild_id].insert(0, {'url': url_youtube, 'titulo': titulo})
                
                await interaction.followup.send(f"🚀 **Pase VIP:** Añadida a la cola para sonar **justo después** de la actual:\n**{titulo}**")
            else:
                # --- CREAR LA TARJETA VISUAL (EMBED) ---
                thumbnail = info.get('thumbnail')
                duracion = info.get('duration', 0)
                minutos, segundos = divmod(duracion, 60)
                texto_duracion = f"{int(minutos)}:{int(segundos):02d}" if duracion else "Desconocida / Directo"

                embed = discord.Embed(title="💿 Poniendo temazo", description=f"**{titulo}**", color=discord.Color.purple())
                if thumbnail:
                    embed.set_image(url=thumbnail)
                embed.add_field(name="⏳ Duración", value=texto_duracion)
                # ---------------------------------------

                opciones_ffmpeg = {
                    'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -user_agent "{user_agent}"', 
                    'options': '-vn'
                }
                fuente_audio = discord.FFmpegPCMAudio(url_audio, executable="./ffmpeg.exe", **opciones_ffmpeg)
                canal_texto = interaction.channel

                def despues_de_reproducir(error):
                    coro = self.reproducir_siguiente(guild_id, vc, canal_texto)
                    asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

                vc.play(fuente_audio, after=despues_de_reproducir)
                await interaction.followup.send(embed=embed, view=ReproductorView())

        except Exception as e:
            await interaction.followup.send(f"❌ Ocurrió un error: {e}")

    @app_commands.command(name="clear", description="Vacía toda la lista de canciones en espera")
    async def clear(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        
        if guild_id in self.colas and len(self.colas[guild_id]) > 0:
            cantidad = len(self.colas[guild_id])
            self.colas[guild_id].clear() # Borramos todo lo que hay en la lista
            await interaction.response.send_message(f"🗑️ Se han eliminado **{cantidad}** canciones de la cola. La canción actual seguirá sonando.")
        else:
            await interaction.response.send_message("📭 La cola ya está vacía.", ephemeral=True)

    @app_commands.command(name="stop", description="Detiene la música por completo sin salirse del canal")
    async def stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        guild_id = interaction.guild.id
        
        if vc and (vc.is_playing() or vc.is_paused()):
            # 1. Vaciamos la cola PRIMERO para que no salte a la siguiente
            if guild_id in self.colas:
                self.colas[guild_id].clear()
            
            # 2. Cortamos el audio actual
            vc.stop()
            await interaction.response.send_message("🛑 Música detenida por completo. La cola ha sido vaciada.")
        else:
            await interaction.response.send_message("❌ No estoy reproduciendo nada ahora mismo.", ephemeral=True)

    @app_commands.command(name="leave", description="Echa al bot del canal de voz")
    async def leave(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
            await interaction.response.send_message("👋 ¡Me piro, adiós!")
        else:
            await interaction.response.send_message("❌ No estoy en ningún canal de voz.")

    @tasks.loop(minutes=1.0) 
    async def control_inactividad(self):
        for vc in self.bot.voice_clients:
            guild_id = vc.guild.id
            if vc.is_playing() or vc.is_paused():
                self.temporizadores[guild_id] = 0
            else:
                self.temporizadores[guild_id] = self.temporizadores.get(guild_id, 0) + 1
                if self.temporizadores[guild_id] >= 10:
                    try: await vc.channel.send("💤 Llevo 10 minutos sin hacer nada. ¡Me salgo para ahorrar energía!")
                    except Exception: pass 
                    await vc.disconnect()
                    self.temporizadores[guild_id] = 0 

async def setup(bot):
    await bot.add_cog(Musica(bot))