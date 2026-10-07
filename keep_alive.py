from flask import Flask, render_template, jsonify
from threading import Thread
import os

app = Flask(__name__)

# Variable global para que Flask y Discord se comuniquen
estado_bot = "iniciando" 

# Función para que main.py pueda cambiar el estado
def cambiar_estado(nuevo_estado):
    global estado_bot
    estado_bot = nuevo_estado

@app.route('/')
def home():
    return render_template('index.html')

# NUEVA RUTA: La web preguntará aquí cómo está el bot
@app.route('/status')
def status():
    return jsonify({"estado": estado_bot})

def run():
    puerto = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=puerto)

def keep_alive():
    t = Thread(target=run)
    t.start()