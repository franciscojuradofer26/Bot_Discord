import discord
import random
import os
import re
import json
import urllib.request
import asyncio
import yt_dlp
from ytmusicapi import YTMusic
from dotenv import load_dotenv
import imageio_ffmpeg
from discord.ext import commands, tasks
from discord import app_commands

from utilidades_yt import opciones_yt, opciones_yt_fallback
from keep_alive import actualizar_info
from db import buscar_canciones

load_dotenv()
ytmusic = YTMusic()

# ffmpeg viene dentro del paquete imageio-ffmpeg (sirve en Windows y en Linux/Render)
ruta_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()


def obtener_video_id(url_o_id: str) -> str | None:
    """Extrae el ID de 11 caracteres de YouTube de cualquier formato de URL o texto plano."""
    if not url_o_id:
        return None
    texto = url_o_id.strip()
    if re.fullmatch(r'[\w-]{11}', texto):
        return texto
    patron = r'(?:v=|\/shorts\/|\/youtu\.be\/|youtu\.be\/|\/v\/|\/embed\/|\/live\/|[?&]v=)([\w-]{11})'
    match = re.search(patron, texto)
    if match:
        return match.group(1)
    return None


def extraer_video_id(url_o_id: str) -> str:
    """Función de compatibilidad que retorna el ID o un fragmento limpio."""
    vid = obtener_video_id(url_o_id)
    return vid if vid else (url_o_id[:100] if url_o_id else "")


async def resolver_cancion(entrada: str) -> tuple[str, str | None]:
    """
    Convierte cualquier tipo de entrada (enlace de YouTube, Spotify, ID o texto de búsqueda)
    en una URL válida y reproducible por yt-dlp.
    Retorna (url_para_ytdlp, titulo_sugerido_o_none).
    """
    entrada = entrada.strip()

    # 1. Enlace de Spotify: resolvemos el título mediante Spotify oEmbed (sin requerir credenciales complejas)
    if 'open.spotify.com/track/' in entrada:
        try:
            req = urllib.request.Request(
                f'https://open.spotify.com/oembed?url={entrada}',
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            def _consultar_spotify():
                with urllib.request.urlopen(req, timeout=3) as r:
                    return json.loads(r.read().decode())
            datos_spotify = await asyncio.to_thread(_consultar_spotify)
            titulo_spotify = datos_spotify.get('title')
            if titulo_spotify:
                entrada = titulo_spotify
        except Exception as e:
            print(f"Aviso: no se pudo resolver enlace de Spotify por oEmbed: {e}")

    # 2. Si ya es un ID de 11 caracteres directo
    vid = obtener_video_id(entrada)
    if vid and not entrada.startswith(('http://', 'https://')):
        return f"https://www.youtube.com/watch?v={vid}", None

    # 3. Si es una URL completa
    if entrada.startswith(('http://', 'https://')):
        # Si es de YouTube, limpiamos parámetros innecesarios dejando una URL canónica
        if vid:
            return f"https://www.youtube.com/watch?v={vid}", None
        # Si es otro enlace directo (Soundcloud, audio web, etc.), lo dejamos pasar tal cual
        return entrada, None

    # 4. Si es texto de búsqueda (ej: "Bad Bunny Moscow Mule")
    # Buscamos primero en YT Music (rápido y con la mejor versión oficial)
    try:
        def _buscar_ytm():
            return ytmusic.search(entrada, filter="songs", limit=1)
        resultados_ytm = await asyncio.to_thread(_buscar_ytm)
        if resultados_ytm and resultados_ytm[0].get('videoId'):
            video_id_ytm = resultados_ytm[0]['videoId']
            artistas = resultados_ytm[0].get('artists') or [{'name': ''}]
            nombre = resultados_ytm[0].get('title', '')
            artista_nom = artistas[0].get('name', '')
            titulo_completo = f"{nombre} - {artista_nom}".strip(" -")
            return f"https://www.youtube.com/watch?v={video_id_ytm}", titulo_completo
    except Exception as e:
        print(f"Aviso: búsqueda en YT Music falló ({e}), recurriendo a ytsearch")

    # Fallback si YT Music no devolvió resultados: búsqueda de yt-dlp
    return f"ytsearch1:{entrada}", None


def crear_embed(info, titulo, cabecera):
    thumbnail = info.get('thumbnail')
    duracion = info.get('duration') or 0
    minutos, segundos = divmod(duracion, 60)
    texto_duracion = f"{int(minutos)}:{int(segundos):02d}" if duracion else "Desconocida / Directo"

    embed = discord.Embed(title=cabecera, description=f"**{titulo}**", color=discord.Color.purple())
    if thumbnail:
        embed.set_image(url=thumbnail)
    embed.add_field(name="⏳ Duración", value=texto_duracion)
    return embed


def obtener_url_stream(info):
    """Extrae la URL de streaming directo del audio seleccionando el formato adecuado."""
    if not info:
        return None
    if info.get('url'):
        return info['url']
    formatos = info.get('formats') or []
    for f in reversed(formatos):
        if f.get('acodec') != 'none' and f.get('url'):
            return f['url']
    return None


def crear_fuente_audio(info):
    url_stream = obtener_url_stream(info)
    if not url_stream:
        raise ValueError("No se pudo obtener el enlace de streaming de audio.")
    headers = info.get('http_headers', {})
    user_agent = headers.get('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
    opciones_ffmpeg = {
        'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -user_agent "{user_agent}"',
        'options': '-vn'
    }
    return discord.FFmpegPCMAudio(url_stream, executable=ruta_ffmpeg, **opciones_ffmpeg)


async def extraer_info(url):
    """Extrae los metadatos y stream de audio con yt-dlp, con estrategia optimizada y respaldo multicliente."""
    def extraer():
        try:
            with yt_dlp.YoutubeDL(opciones_yt()) as ydl:
                datos = ydl.extract_info(url, download=False)
                if datos and 'entries' in datos:
                    entradas = [e for e in datos['entries'] if e]
                    if entradas:
                        return entradas[0]
                return datos
        except Exception as e_primero:
            print(f"⚠️ Aviso: Extracción principal falló ({e_primero}). Intentando estrategia de respaldo...")
            try:
                with yt_dlp.YoutubeDL(opciones_yt_fallback()) as ydl:
                    datos = ydl.extract_info(url, download=False)
                    if datos and 'entries' in datos:
                        entradas = [e for e in datos['entries'] if e]
                        if entradas:
                            return entradas[0]
                    return datos
            except Exception as e_segundo:
                print(f"⚠️ Aviso: Extracción de respaldo también falló ({e_segundo})")
                raise e_primero
    return await asyncio.to_thread(extraer)


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
        if vc and (vc.is_playing() or vc.is_paused()):
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
        self.auto_keepalive_render.start()

    def cog_unload(self):
        self.control_inactividad.cancel()
        self.auto_keepalive_render.cancel()

    def _al_terminar(self, guild_id, vc, canal_texto):
        def despues_de_reproducir(error):
            if error:
                print(f"Error FFmpeg: {error}")
            coro = self.reproducir_siguiente(guild_id, vc, canal_texto)
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
        return despues_de_reproducir

    async def reproducir_siguiente(self, guild_id, vc, canal_texto):
        while guild_id in self.colas and len(self.colas[guild_id]) > 0:
            if not vc.is_connected():
                actualizar_info(cancion=None, cola_longitud=0, en_voz=False)
                return
            siguiente_cancion = self.colas[guild_id].pop(0)
            titulo = siguiente_cancion['titulo']
            try:
                info = await extraer_info(siguiente_cancion['url'])
                fuente_audio = crear_fuente_audio(info)
                vc.play(fuente_audio, after=self._al_terminar(guild_id, vc, canal_texto))
                
                # Actualizamos estado web
                actualizar_info(
                    cancion=titulo,
                    cola_longitud=len(self.colas.get(guild_id, [])),
                    en_voz=True
                )
                
                await canal_texto.send(embed=crear_embed(info, titulo, "💿 Sonando ahora"), view=ReproductorView())
                return
            except Exception as e:
                error_msg = str(e)
                print(f"Error extrayendo audio en cola ({titulo}): {error_msg}")
                try:
                    if "Sign in to confirm you're not a bot" in error_msg or "confirm you're not a bot" in error_msg:
                        await canal_texto.send(
                            "⚠️ **YouTube ha bloqueado la petición (Detección Anti-Bot en la nube).**\n"
                            "Configura tus cookies de YouTube (`cookies.txt` o variable `YOUTUBE_COOKIES`) en Render para identificarte como usuario real."
                        )
                    else:
                        await canal_texto.send(f"⚠️ No he podido reproducir **{titulo}**, paso a la siguiente.")
                except Exception:
                    pass

        # Si ya no quedan canciones en la cola
        actualizar_info(cancion=None, cola_longitud=0, en_voz=vc.is_connected() if vc else False)

    async def sugerencias_canciones(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        try:
            if not current.strip():
                return []
            opciones = []

            # 1. Búsqueda en PostgreSQL (con reconexión automática)
            filas_db = buscar_canciones(current, limite=10)
            for fila in filas_db:
                nombre_db, artista_db, enlace_db = fila
                texto_visual = f"💾 {nombre_db} - {artista_db}"
                id_limpia = extraer_video_id(enlace_db)
                if id_limpia:
                    opciones.append(app_commands.Choice(name=texto_visual[:100], value=id_limpia))

            if len(opciones) >= 25:
                return opciones[:25]

            # 2. Búsqueda en YouTube Music
            try:
                limite_restante = 25 - len(opciones)
                resultados_yt = await asyncio.wait_for(
                    asyncio.to_thread(ytmusic.search, current, filter="songs", limit=limite_restante),
                    timeout=1.2
                )
                for res in resultados_yt:
                    artistas = res.get('artists') or [{'name': 'Desconocido'}]
                    texto_yt = f"🎵 {res['title']} - {artistas[0]['name']}"
                    video_id_yt = res.get('videoId', '')
                    if video_id_yt:
                        opciones.append(app_commands.Choice(name=texto_yt[:100], value=str(video_id_yt)))
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                print(f"⚠️ Error YT Music: {e}")

            return opciones[:25]
        except Exception:
            return []

    async def _reproducir_o_encolar(self, interaction: discord.Interaction, cancion: str, al_principio: bool):
        """Lógica común de /play y /playnext."""
        await interaction.response.defer()
        if not interaction.user.voice:
            await interaction.followup.send("❌ ¡Tienes que meterte en un canal de voz primero!")
            return

        canal_voz = interaction.user.voice.channel

        try:
            vc = interaction.guild.voice_client
            if not vc:
                vc = await canal_voz.connect()
            elif vc.channel != canal_voz:
                await vc.move_to(canal_voz)

            # Normalizamos y resolvemos la URL o búsqueda
            url_reproducible, titulo_previo = await resolver_cancion(cancion)
            info = await extraer_info(url_reproducible)
            titulo = titulo_previo or info.get('title', 'Canción desconocida')

            guild_id = interaction.guild.id
            if guild_id not in self.colas:
                self.colas[guild_id] = []

            if vc.is_playing() or vc.is_paused():
                entrada = {'url': url_reproducible, 'titulo': titulo}
                if al_principio:
                    self.colas[guild_id].insert(0, entrada)
                    await interaction.followup.send(f"🚀 **Pase VIP:** Añadida a la cola para sonar **justo después** de la actual:\n**{titulo}**")
                else:
                    self.colas[guild_id].append(entrada)
                    await interaction.followup.send(f"📝 Añadida a la cola: **{titulo}** (Posición: {len(self.colas[guild_id])})")
                
                actualizar_info(cola_longitud=len(self.colas[guild_id]), en_voz=True)
            else:
                fuente_audio = crear_fuente_audio(info)
                vc.play(fuente_audio, after=self._al_terminar(guild_id, vc, interaction.channel))
                actualizar_info(cancion=titulo, cola_longitud=len(self.colas.get(guild_id, [])), en_voz=True)
                await interaction.followup.send(embed=crear_embed(info, titulo, "💿 Poniendo temazo"), view=ReproductorView())

        except Exception as e:
            error_msg = str(e)
            print(f"Error en play/playnext: {error_msg}")
            es_bot_error = any(frase in error_msg.lower() for frase in [
                "confirm you're not a bot",
                "confirm you’re not a bot",
                "sign in to confirm",
                "not a bot",
                "too many requests"
            ])
            if es_bot_error:
                await interaction.followup.send(
                    "⚠️ **YouTube ha bloqueado la conexión desde el servidor (Detección Anti-Bot).**\n"
                    "Los servidores de Render están en AWS y YouTube pide autenticación de usuario real.\n"
                    "👉 **Solución:** Sube tus cookies de YouTube con la sesión iniciada en tu cuenta (`cookies.txt` o variable `YOUTUBE_COOKIES`) en Render."
                )
            else:
                await interaction.followup.send(f"❌ Ocurrió un error: {error_msg[:1800]}")

    @app_commands.command(name="play", description="Busca y reproduce música de YT Music o enlace")
    @app_commands.autocomplete(cancion=sugerencias_canciones)
    async def play(self, interaction: discord.Interaction, cancion: str):
        await self._reproducir_o_encolar(interaction, cancion, al_principio=False)

    @app_commands.command(name="playnext", description="Pone una canción la primera de la cola (Pase VIP)")
    @app_commands.autocomplete(cancion=sugerencias_canciones)
    async def playnext(self, interaction: discord.Interaction, cancion: str):
        await self._reproducir_o_encolar(interaction, cancion, al_principio=True)

    @app_commands.command(name="queue", description="Muestra las próximas canciones en la lista de espera")
    async def queue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id not in self.colas or len(self.colas[guild_id]) == 0:
            await interaction.response.send_message("📭 La cola está vacía ahora mismo.")
            return

        lista = self.colas[guild_id]
        texto = "📋 **Lista de Reproducción Actual:**\n\n"
        for i, cancion in enumerate(lista[:15]):
            texto += f"**{i+1}.** {cancion['titulo']}\n"
        if len(lista) > 15:
            texto += f"\n*... y {len(lista) - 15} canciones más esperando.*"
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
            if guild_id not in self.colas:
                self.colas[guild_id] = []

            palabras_prohibidas = ['live', 'en vivo', 'superbowl', 'super bowl', 'show', 'performance', 'concierto', 'concert', 'mix']
            canciones_filtradas = 0

            for res in resultados:
                titulo_cancion = res.get('title', '').lower()
                es_directo = any(palabra in titulo_cancion for palabra in palabras_prohibidas)
                duracion = res.get('duration_seconds') or 0
                es_muy_larga = duracion > 600

                video_id = res.get('videoId')
                if video_id and not es_directo and not es_muy_larga:
                    url_video = f"https://www.youtube.com/watch?v={video_id}"
                    artistas = res.get('artists') or [{'name': 'Desconocido'}]
                    titulo = f"{res['title']} - {artistas[0]['name']}"
                    self.colas[guild_id].append({'url': url_video, 'titulo': titulo})
                    canciones_filtradas += 1

            await interaction.followup.send(f"📻 **¡Modo Radio YT Activado!** He filtrado y añadido **{canciones_filtradas}** temazos basados en: *{criterios}*")

            vc = interaction.guild.voice_client
            if not vc:
                vc = await canal_voz.connect()
            if vc and not vc.is_playing() and not vc.is_paused():
                await self.reproducir_siguiente(guild_id, vc, interaction.channel)

        except Exception as e:
            print(f"Error en radio: {e}")
            await interaction.followup.send(f"❌ Ocurrió un error sintonizando la radio: {str(e)[:1800]}")

    @app_commands.command(name="playlist", description="Carga una lista de reproducción entera de YouTube")
    @app_commands.describe(enlace="El enlace de la playlist de YouTube")
    async def playlist(self, interaction: discord.Interaction, enlace: str):
        await interaction.response.defer()
        if not interaction.user.voice:
            await interaction.followup.send("❌ ¡Tienes que meterte en un canal de voz primero!")
            return

        canal_voz = interaction.user.voice.channel

        try:
            def extraer_pl():
                with yt_dlp.YoutubeDL(opciones_yt(extract_flat='in_playlist', noplaylist=False)) as ydl:
                    return ydl.extract_info(enlace, download=False)

            info = await asyncio.to_thread(extraer_pl)
            if 'entries' not in info:
                await interaction.followup.send("❌ Eso no parece ser una playlist válida.")
                return

            canciones = [c for c in info['entries'] if c]
            if not canciones:
                await interaction.followup.send("❌ La playlist está vacía o es privada.")
                return

            guild_id = interaction.guild.id
            if guild_id not in self.colas:
                self.colas[guild_id] = []

            for cancion in canciones:
                url_video = cancion.get('url') or cancion.get('id')
                if url_video and not url_video.startswith('http'):
                    url_video = f"https://www.youtube.com/watch?v={url_video}"
                if url_video:
                    self.colas[guild_id].append({'url': url_video, 'titulo': cancion.get('title', 'Canción de la playlist')})

            await interaction.followup.send(f"📚 ¡Éxito! Se han añadido **{len(canciones)}** canciones a la cola.")

            vc = interaction.guild.voice_client
            if not vc:
                vc = await canal_voz.connect()
            if vc and not vc.is_playing() and not vc.is_paused():
                await self.reproducir_siguiente(guild_id, vc, interaction.channel)

        except Exception as e:
            print(f"Error en playlist: {e}")
            await interaction.followup.send(f"❌ Ocurrió un error leyendo la playlist: {str(e)[:1800]}")

    @app_commands.command(name="clear", description="Vacía toda la lista de canciones en espera")
    async def clear(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.colas and len(self.colas[guild_id]) > 0:
            cantidad = len(self.colas[guild_id])
            self.colas[guild_id].clear()
            actualizar_info(cola_longitud=0)
            await interaction.response.send_message(f"🗑️ Se han eliminado **{cantidad}** canciones de la cola. La canción actual seguirá sonando.")
        else:
            await interaction.response.send_message("📭 La cola ya está vacía.", ephemeral=True)

    @app_commands.command(name="stop", description="Detiene la música por completo sin salirse del canal")
    async def stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        guild_id = interaction.guild.id

        if vc and (vc.is_playing() or vc.is_paused()):
            if guild_id in self.colas:
                self.colas[guild_id].clear()
            vc.stop()
            actualizar_info(cancion=None, cola_longitud=0)
            await interaction.response.send_message("🛑 Música detenida por completo. La cola ha sido vaciada.")
        else:
            await interaction.response.send_message("❌ No estoy reproduciendo nada ahora mismo.", ephemeral=True)

    @app_commands.command(name="leave", description="Echa al bot del canal de voz")
    async def leave(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc:
            guild_id = interaction.guild.id
            if guild_id in self.colas:
                self.colas[guild_id].clear()
            await vc.disconnect()
            actualizar_info(cancion=None, cola_longitud=0, en_voz=False)
            await interaction.response.send_message("👋 ¡Me piro, adiós!")
        else:
            await interaction.response.send_message("❌ No estoy en ningún canal de voz.")

    @tasks.loop(minutes=1.0)
    async def control_inactividad(self):
        for vc in list(self.bot.voice_clients):
            guild_id = vc.guild.id
            if vc.is_playing() or vc.is_paused():
                self.temporizadores[guild_id] = 0
            else:
                self.temporizadores[guild_id] = self.temporizadores.get(guild_id, 0) + 1
                if self.temporizadores[guild_id] >= 10:
                    try:
                        await vc.channel.send("💤 Llevo 10 minutos sin hacer nada. ¡Me salgo para ahorrar energía!")
                    except Exception:
                        pass
                    if guild_id in self.colas:
                        self.colas[guild_id].clear()
                    await vc.disconnect()
                    self.temporizadores[guild_id] = 0
                    actualizar_info(cancion=None, cola_longitud=0, en_voz=False)

    @tasks.loop(minutes=5.0)
    async def auto_keepalive_render(self):
        """Si el bot está reproduciendo música en Render, se auto-hace ping cada 5 min para que el servidor no se duerma."""
        url_base = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("APP_URL")
        if not url_base:
            return

        hay_audio_activo = any(vc.is_playing() or vc.is_paused() for vc in self.bot.voice_clients)
        if hay_audio_activo:
            def _ping():
                try:
                    url_ping = f"{url_base.rstrip('/')}/status"
                    req = urllib.request.Request(url_ping, headers={'User-Agent': 'RenderKeepAlive/1.0'})
                    with urllib.request.urlopen(req, timeout=5) as r:
                        r.read()
                except Exception as e:
                    print(f"⚠️ Error en ping keepalive de Render: {e}")
            await asyncio.to_thread(_ping)

    @control_inactividad.before_loop
    async def antes_de_inactividad(self):
        await self.bot.wait_until_ready()

    @auto_keepalive_render.before_loop
    async def antes_de_keepalive(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Musica(bot))
