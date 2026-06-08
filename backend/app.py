import os
from flask import Flask, request, jsonify
from flask_cors import CORS
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, '..', 'frontend')

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
CORS(app)
@app.route('/')
def index():
    return app.send_static_file('home.html')

@app.route('/<path:path>')
def static_files(path):
    return app.send_static_file(path)

@app.route('/api/add', methods=['POST'])
def add_numbers():
    data = request.get_json() or {}

    
    num1 = data.get('number1', 0)
    num2 = data.get('number2', 0)

    result = num1 + num2

    return jsonify({'answer': result})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
