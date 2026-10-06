from flask import Flask, render_template
from threading import Thread
import os

app = Flask(__name__)

# Ahora le decimos que cargue un archivo HTML en lugar de texto
@app.route('/')
def home():
    return render_template('index.html')

def run():
    puerto = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=puerto)

def keep_alive():
    t = Thread(target=run)
    t.start()