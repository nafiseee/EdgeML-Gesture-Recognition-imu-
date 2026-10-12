import json
import subprocess
import time
import csv
import os
from flask import Flask, request, jsonify

app = Flask(__name__)
current_gesture_id = 0
CSV_FILE = 'dataset.csv'

if os.path.isfile(CSV_FILE):
    with open(CSV_FILE, 'r') as f:
        lines = f.readlines()[1:] 
        if lines:
            last_line = lines[-1].strip().split(',')
            if len(last_line) >= 8:
                current_gesture_id = int(last_line[7])

HTML_UI = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background: #111; color: white; font-family: sans-serif; text-align: center; padding-top: 10px; margin: 0; }
        .btn { width: 90%; height: 60px; font-size: 18px; margin: 6px; border-radius: 12px; border: none; font-weight: bold; }
        .btn-tg { background: #3498db; color: white; }
        .btn-sp { background: #1db954; color: white; }
        .btn-cr { background: #f39c12; color: white; }
        .btn-noise { background: #576574; color: white; }
        .btn-save { background: #1e90ff; color: white; width: 40%; }
        .btn-cancel { background: #ff6b81; color: white; width: 40%; }
        
        #status { font-size: 18px; margin: 15px; color: #eccc68; min-height: 25px; }
        #review-panel { display: none; margin-top: 15px; padding: 10px; background: #222; border-radius: 15px; }
        #controls { display: block; }
        canvas { max-width: 100%; height: 300px !important; }
    </style>
</head>
<body>
    <h2>Сборщик жестов 6DoF (Acc + Gyro)</h2>
    <div id="status">Нажми кнопку. Начнётся запись:</div>
    
    <div id="controls">
        <button class="btn btn-tg" onclick="record(1)">(Telegram)</button>
        <button class="btn btn-sp" onclick="record(2)">(Spotify)</button>
        <button class="btn btn-cr" onclick="record(3)">(Circle)</button>
        <button class="btn btn-noise" onclick="record(0)">Шум (noise)</button>
    </div>

    <div id="review-panel">
        <canvas id="chart"></canvas>
        <br>
        <button class="btn btn-cancel" onclick="cancel()">Отменить запись</button>
        <button class="btn btn-save" onclick="save()">Сохранить жест</button>
    </div>

    <script>
        let currentData = null;
        let chartInstance = null;
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

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
            status.innerText = 'Приготовься... запись через 1 секунду...';
            
            setTimeout(() => {
                beep(400, 150);
                status.innerText = 'Записываю 1.5 секунды! Двигай рукой!';
                
                fetch('/record/' + label)
                    .then(response => response.json())
                    .then(data => {
                        beep(800, 100);
                        setTimeout(() => beep(800, 100), 150);
                        
                        if(data.length === 0) {
                            status.innerText = 'Ошибка: не удалось получить данные с датчиков!';
                            document.getElementById('controls').style.display = 'block';
                            return;
                        }
                        currentData = data;
                        status.innerText = `Получено ${data.length} точек. Сохранить?`;
                        document.getElementById('review-panel').style.display = 'block';
                        drawChart(data);
                    })
                    .catch(err => {
                        status.innerText = 'Ошибка соединения с сервером!';
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
            });
        }

        function cancel() {
            document.getElementById('status').innerText = 'Отменено. Нажми кнопку заново.';
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

@app.route('/record/<int:label>')
def record_gesture(label):
    bin_path = "/data/data/com.termux/files/home/imu_stream"
    
    process = subprocess.Popen(
        ['su', '-c', bin_path], 
        stdout=subprocess.PIPE, text=True
    )
    
    collected_points = []
    try:
        for line in iter(process.stdout.readline, ''):
            parts = line.split()
            # Ожидаем 7 значений: TS, AX, AY, AZ, GX, GY, GZ
            if len(parts) == 7:
                try:
                    collected_points.append({
                        'ax': float(parts[1]), 'ay': float(parts[2]), 'az': float(parts[3]),
                        'gx': float(parts[4]), 'gy': float(parts[5]), 'gz': float(parts[6]),
                        'label': label
                    })
                except ValueError:
                    pass
                    
            if len(collected_points) >= 300: # 1.5 секунды при ~200 Гц
                break
    finally:
        process.terminate()
        subprocess.run(['su', '-c', 'killall imu_stream'], capture_output=True)
        
    return jsonify(collected_points)

@app.route('/save', methods=['POST'])
def save_data():
    global current_gesture_id
    current_gesture_id += 1
    
    data = request.json
    if not data:
        return "Ошибка: нет данных", 400
        
    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['ax', 'ay', 'az', 'gx', 'gy', 'gz', 'label', 'gesture_id'])
        for p in data:
            writer.writerow([p['ax'], p['ay'], p['az'], p['gx'], p['gy'], p['gz'], p['label'], current_gesture_id])
            
    return f"Жест #{current_gesture_id} сохранён (6DoF)!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)