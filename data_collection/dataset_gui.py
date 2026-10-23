import json
import subprocess
import time
import csv
import os
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
current_gesture_id = 0

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.abspath(os.path.join(CURRENT_DIR, '..', 'datasets', 'dataset.csv'))
BUTTONS_FILE = os.path.abspath(os.path.join(CURRENT_DIR, '..', 'datasets', 'buttons.json'))
BIN_PATH = os.path.abspath(os.path.join(CURRENT_DIR, '..', 'daemon', 'sensor_daemon'))

os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)

default_buttons = {
    "0": "Background"
}

# Загружаем кастомные кнопки  из файла
def load_buttons():
    buttons = default_buttons.copy()
    if os.path.isfile(BUTTONS_FILE):
        try:
            with open(BUTTONS_FILE, 'r', encoding='utf-8') as f:
                custom = json.load(f)
                buttons.update(custom)
        except Exception as e:
            print(f"[WARN] Ошибка чтения {BUTTONS_FILE}: {e}")
    else:
        print(f"[WARN] Файл {BUTTONS_FILE} не найден. Используется только фон.")
    return buttons

# Инициализация id жестов из csv
if os.path.isfile(CSV_FILE):
    with open(CSV_FILE, 'r') as f:
        reader = csv.reader(f)
        next(reader, None)
        max_id = 0
        for row in reader:
            if len(row) >= 8:
                try:
                    gid = int(float(row[7]))
                    if gid > max_id:
                        max_id = gid
                except ValueError:
                    pass
        current_gesture_id = max_id

HTML_UI = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background: #111; color: white; font-family: sans-serif; text-align: center; padding-top: 10px; margin: 0; }
        .btn { width: 90%; height: 50px; font-size: 16px; margin: 5px; border-radius: 12px; border: none; font-weight: bold; cursor: pointer; }
        .btn-record { background: #3498db; color: white; }
        .btn-save { background: #1e90ff; color: white; width: 40%; }
        .btn-cancel { background: #ff6b81; color: white; width: 40%; }
        
        #status { font-size: 18px; margin: 10px; color: #eccc68; min-height: 25px; }
        #review-panel { display: none; margin-top: 10px; padding: 10px; background: #222; border-radius: 15px; }
        #controls { display: block; }
        .panel { margin: 15px auto; padding: 15px; background: #222; border-radius: 12px; width: 90%; }
        
        .stats-box { font-size: 14px; text-align: left; background: #333; padding: 10px; border-radius: 8px; font-family: monospace; }
        canvas { max-width: 100%; height: 250px !important; }
    </style>
</head>
<body>
    <h2>6DoF Collector</h2>
    <div id="status">Ready.</div>
    
    <div id="controls">
        <div class="panel">
            <h3 style="margin-top:0;">Record Data</h3>
            <div id="buttons-container">
                
            </div>
        </div>

        <div class="panel">
            <h3 style="margin-top:0;">Dataset Stats</h3>
            <div class="stats-box" id="stats-box">Loading...</div>
        </div>
    </div>

    <div id="review-panel">
        <canvas id="chart"></canvas>
        <br>
        <button class="btn btn-cancel" onclick="cancel()">Cancel</button>
        <button class="btn btn-save" onclick="save()">Save Data</button>
    </div>

    <script>
        let currentData = null;
        let chartInstance = null;
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

        window.onload = () => {
            fetchButtons();
            fetchStats();
        };

        function fetchButtons() {
            fetch('/buttons')
                .then(r => r.json())
                .then(buttons => {
                    const container = document.getElementById('buttons-container');
                    container.innerHTML = '';
                    for (const [id, name] of Object.entries(buttons)) {
                        let btn = document.createElement('button');
                        btn.className = 'btn btn-record';
                        btn.innerText = `${name} (${id})`;
                        btn.onclick = () => record(id);
                        container.appendChild(btn);
                    }
                });
        }

        function fetchStats() {
            fetch('/stats')
                .then(r => r.json())
                .then(stats => {
                    const box = document.getElementById('stats-box');
                    if (Object.keys(stats).length === 0) {
                        box.innerHTML = "Dataset is empty.";
                        return;
                    }
                    let html = "";
                    let total = 0;
                    for (const [name, count] of Object.entries(stats)) {
                        html += `• ${name}: <b>${count}</b> samples<br>`;
                        total += count;
                    }
                    html += `<hr style="border-color:#555">Total samples: <b>${total}</b>`;
                    box.innerHTML = html;
                });
        }

        function beep(freq, duration) {
            if (audioCtx.state === 'suspended') audioCtx.resume();
            let oscillator = audioCtx.createOscillator();
            let gainNode = audioCtx.createGain();
            oscillator.type = 'sine'; 
            oscillator.frequency.value = freq;
            gainNode.gain.setValueAtTime(1, audioCtx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration / 1000);
            oscillator.connect(gainNode);
            gainNode.connect(audioCtx.destination);
            oscillator.start();
            setTimeout(() => { oscillator.stop(); }, duration);
        }

        function record(label) {
            if (audioCtx.state === 'suspended') audioCtx.resume();
            let status = document.getElementById('status');
            document.getElementById('controls').style.display = 'none';
            document.getElementById('review-panel').style.display = 'none';
            status.innerText = 'Preparing... recording in 1 sec...';
            
            setTimeout(() => {
                beep(400, 150);
                status.innerText = 'Recording 1.5s! MOVE NOW!';
                
                fetch('/record/' + label)
                    .then(response => response.json())
                    .then(data => {
                        beep(800, 100);
                        setTimeout(() => beep(800, 100), 150);
                        
                        if(data.length === 0) {
                            status.innerText = 'Error: No data from sensor!';
                            document.getElementById('controls').style.display = 'block';
                            return;
                        }
                        currentData = data;
                        status.innerText = `Received ${data.length} points. Save?`;
                        document.getElementById('review-panel').style.display = 'block';
                        drawChart(data);
                    })
                    .catch(err => {
                        status.innerText = 'Error: Connection failed!';
                        document.getElementById('controls').style.display = 'block';
                    });
            }, 1000);
        }

        function save() {
            fetch('/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(currentData)
            }).then(response => response.text())
            .then(text => {
                document.getElementById('status').innerText = text;
                resetUI();
                fetchStats(); 
            });
        }

        function cancel() {
            document.getElementById('status').innerText = 'Cancelled. Ready.';
            resetUI();
        }

        function resetUI() {
            document.getElementById('review-panel').style.display = 'none';
            document.getElementById('controls').style.display = 'block';
            currentData = null;
        }

        function drawChart(data) {
            let ctx = document.getElementById('chart').getContext('2d');
            if(chartInstance) chartInstance.destroy();
            let labels = Array.from({length: data.length}, (_, i) => i);
            chartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        { label: 'Acc X', data: data.map(d => d.ax), borderColor: '#ff4757', borderWidth: 2, pointRadius: 0 },
                        { label: 'Acc Y', data: data.map(d => d.ay), borderColor: '#2ed573', borderWidth: 2, pointRadius: 0 },
                        { label: 'Acc Z', data: data.map(d => d.az), borderColor: '#1e90ff', borderWidth: 2, pointRadius: 0 },
                        { label: 'Gyr X', data: data.map(d => d.gx), borderColor: '#ff4757', borderWidth: 1, borderDash: [5, 5], pointRadius: 0 },
                        { label: 'Gyr Y', data: data.map(d => d.gy), borderColor: '#2ed573', borderWidth: 1, borderDash: [5, 5], pointRadius: 0 },
                        { label: 'Gyr Z', data: data.map(d => d.gz), borderColor: '#1e90ff', borderWidth: 1, borderDash: [5, 5], pointRadius: 0 }
                    ]
                },
                options: { animation: false, scales: { x: { display: false } } }
            });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return HTML_UI

@app.route('/buttons')
def get_buttons():
    return jsonify(load_buttons())

@app.route('/stats')
def get_stats():
    if not os.path.isfile(CSV_FILE):
        return jsonify({})
        
    stats = {}
    buttons = load_buttons()
    
    with open(CSV_FILE, 'r') as f:
        reader = csv.DictReader(f)
        tracker = {}
        for row in reader:
            lbl = row['label']
            gid = row['gesture_id']
            if lbl not in tracker:
                tracker[lbl] = set()
            tracker[lbl].add(gid)
            
    for lbl, gids in tracker.items():
        name = buttons.get(lbl, f"Unknown ({lbl})")
        stats[f"{name} [{lbl}]"] = len(gids)
        
    return jsonify(stats)

@app.route('/record/<int:label>')
def record_gesture(label):
    process = subprocess.Popen(
        ['su', '-c', BIN_PATH], 
        stdout=subprocess.PIPE, text=True
    )

    collected_points = []
    try:
        for line in iter(process.stdout.readline, ''):
            parts = line.split()
            if len(parts) == 7:
                try:
                    collected_points.append({
                        'ax': float(parts[1]), 'ay': float(parts[2]), 'az': float(parts[3]),
                        'gx': float(parts[4]), 'gy': float(parts[5]), 'gz': float(parts[6]),
                        'label': label
                    })
                except ValueError:
                    pass

            if len(collected_points) >= 300: 
                break
    finally:
        process.terminate()
        subprocess.run(['su', '-c', 'killall sensor_daemon'], capture_output=True)

    return jsonify(collected_points)

@app.route('/save', methods=['POST'])
def save_data():
    global current_gesture_id
    current_gesture_id += 1

    data = request.json
    if not data:
        return "Error: No data", 400

    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['ax', 'ay', 'az', 'gx', 'gy', 'gz', 'label', 'gesture_id'])
        for p in data:
            writer.writerow([p['ax'], p['ay'], p['az'], p['gx'], p['gy'], p['gz'], p['label'], current_gesture_id])

    return f"Gesture #{current_gesture_id} saved!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)