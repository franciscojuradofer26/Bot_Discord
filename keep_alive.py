from flask import Flask
from threading import Thread
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "¡El motor del bot está encendido y listo para recibir comandos!"

def run():
    # En la nube usa el puerto de Render, en tu PC usa el 5000
    puerto = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=puerto)

def keep_alive():
    t = Thread(target=run)
    t.start()