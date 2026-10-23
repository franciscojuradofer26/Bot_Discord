from flask import Flask, render_template, jsonify
from threading import Thread
import os

app = Flask(__name__)

# Variable global para que Flask y Discord se comuniquen
estado_bot = "iniciando"
info_bot = {
    "servidores": 0,
    "cancion_actual": None,
    "cola_longitud": 0,
    "en_voz": False
}

def cambiar_estado(nuevo_estado):
    global estado_bot
    estado_bot = nuevo_estado

def actualizar_info(servidores=None, cancion=None, cola_longitud=None, en_voz=None):
    global info_bot
    if servidores is not None:
        info_bot["servidores"] = servidores
    if cancion is not None:
        info_bot["cancion_actual"] = cancion
    if cola_longitud is not None:
        info_bot["cola_longitud"] = cola_longitud
    if en_voz is not None:
        info_bot["en_voz"] = en_voz

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/status')
def status():
    return jsonify({
        "estado": estado_bot,
        **info_bot
    })

def run():
    puerto = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=puerto)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()
