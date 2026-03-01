from flask import Flask
from threading import Thread
import logging

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)  # Suppress Flask request logs

@app.route('/')
def home():
    return "VoltLegal is running! ⚖️"

@app.route('/health')
def health():
    return "OK", 200

def run():
    app.run(host='0.0.0.0', port=7860)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
