import subprocess, sys, collections, time, json, csv, os
import numpy as np
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '..', 'outputs'))
sys.path.append(OUTPUTS_DIR)

from model_math import predict

WEIGHTS_PATH = os.path.join(OUTPUTS_DIR, 'weights.npz')
BUTTONS_PATH = os.path.abspath(os.path.join(CURRENT_DIR, '..', 'datasets', 'buttons.json'))
HN_BANK_CSV = os.path.abspath(os.path.join(CURRENT_DIR, '..', 'datasets', 'dataset_HARD_NEGATIVES.csv'))
BIN_PATH = os.path.abspath(os.path.join(CURRENT_DIR, '..', 'daemon', 'sensor_daemon'))

os.makedirs(os.path.dirname(HN_BANK_CSV), exist_ok=True)

# --- НАСТРОЙКИ ---
CONF_THRESHOLD = 0.85  # Порог уверенности сети
AMP_THRESHOLD = 3.0    # Порог амплитуды (фильтр покоя)
STRIDE = 50            # Шаг скользящего окна
COOLDOWN_STEPS = 300   # Пауза после распознанного жеста

C_GREEN = '\033[92m'
C_RED = '\033[91m'
C_GRAY = '\033[90m'
C_RESET = '\033[0m'

try:
    w = dict(np.load(WEIGHTS_PATH))
except Exception as e:
    print(f"{C_RED}Error loading weights: {e}{C_RESET}")
    sys.exit(1)

def load_labels():
    labels = {0: "BACKGROUND"}
    if os.path.isfile(BUTTONS_PATH):
        try:
            with open(BUTTONS_PATH, 'r', encoding='utf-8') as f:
                custom = json.load(f)
                for k, v in custom.items():
                    if int(k) != 0:
                        labels[int(k)] = v.upper().strip()
        except Exception as e:
            print(f"{C_RED}Error reading {BUTTONS_PATH}: {e}{C_RESET}")
    return labels

def get_next_hn_id():
    if not os.path.exists(HN_BANK_CSV):
        return 90000
    try:
        with open(HN_BANK_CSV, 'r') as f:
            lines = f.readlines()[1:]
            if not lines:
                return 90000
            last_line = lines[-1].strip()
            return int(last_line.split(',')[-1]) + 1
    except Exception:
        return 90000

NEXT_HN_ID = get_next_hn_id()

def save_hard_negative(window_data):
    global NEXT_HN_ID
    file_exists = os.path.exists(HN_BANK_CSV)
    with open(HN_BANK_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['ax', 'ay', 'az', 'gx', 'gy', 'gz', 'label', 'gesture_id'])
        for row in window_data:
            writer.writerow([row[0], row[1], row[2], row[3], row[4], row[5], 0, NEXT_HN_ID])
    NEXT_HN_ID += 1

def main():
    labels = load_labels()
    buf = collections.deque(maxlen=300)
    
    last_match_window = None
    last_match_time = 0.0
    
    print(f"\n{C_GREEN}=== EDGE GESTURE AI ==={C_RESET}")
    print(f"Classes: {list(labels.values())}")
    print(f"Hard Negatives ID Starts At: {NEXT_HN_ID}")
    print("Waiting for movements... (Press VOL UP within 15s to save false positive)\n")
    
    p = subprocess.Popen(['su', '-c', BIN_PATH], stdout=subprocess.PIPE, text=True)
    step_counter, cooldown = 0, 0
    
    try:
        for line in iter(p.stdout.readline, ''):
            line = line.strip()
            if not line:
                continue
                
            if line == ">>> FALSE_POSITIVE <<<":
                if last_match_window is not None:
                    time_since_match = time.time() - last_match_time
                    if time_since_match <= 15.0:
                        save_hard_negative(last_match_window)
                        t_str = datetime.now().strftime("%H:%M:%S")
                        print(f"[{t_str}] {C_RED}► HARD NEGATIVE SAVED! (ID: {NEXT_HN_ID - 1}, delay: {time_since_match:.1f}s){C_RESET}")
                        last_match_window = None 
                    else:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {C_GRAY}► Слишком поздно (прошло {time_since_match:.1f}с). Игнорируем.{C_RESET}")
                        last_match_window = None
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {C_GRAY}► В кэше нет недавних распознанных жестов.{C_RESET}")
                continue

            parts = line.split()
            if len(parts) == 7:
                try:
                    buf.append(tuple(map(float, parts[1:7])))
                except ValueError:
                    continue
                    
            if cooldown > 0:
                cooldown -= 1
                continue
                
            if len(buf) == 300:
                step_counter += 1
                if step_counter >= STRIDE:
                    step_counter = 0
                    
                    data = np.array(buf)
                    fresh_acc = data[-STRIDE:, :3]
                    amplitudes = np.max(fresh_acc, axis=0) - np.min(fresh_acc, axis=0)
                    max_amp = np.max(amplitudes)
                    
                    if max_amp >= AMP_THRESHOLD:
                        start_time = time.time()
                        cls, conf = predict(buf, w)
                        inf_time = (time.time() - start_time) * 1000
                        t_str = datetime.now().strftime("%H:%M:%S")
                        
                        if cls != 0 and conf >= CONF_THRESHOLD:
                            g_name = labels.get(cls, f"UNK_{cls}")
                            print(f"[{t_str}] {C_GREEN}● {g_name:<10}{C_RESET} | Conf: {conf:.3f} | Amp: {max_amp:4.1f} | {inf_time:4.1f}ms")
                            
                            last_match_window = list(buf)
                            last_match_time = time.time()
                            
                            os.system(f'am broadcast --receiver-foreground -a edge.gesture.DETECTED -p com.arlosoft.macrodroid --es "name" "{g_name}" > /dev/null 2>&1')
                            cooldown = COOLDOWN_STEPS
                            buf.clear()
                        else:
                            reason = "BG" if cls == 0 else labels.get(cls, str(cls))
                            print(f"[{t_str}] {C_GRAY}○ {reason:<10}{C_RESET} | Conf: {conf:.3f} | Amp: {max_amp:4.1f} | {inf_time:4.1f}ms")
                            cooldown = STRIDE // 2

    except KeyboardInterrupt:
        print(f"\n{C_RED}[EXIT] Terminating...{C_RESET}")
    finally:
        p.terminate()
        subprocess.run(['su', '-c', 'killall sensor_daemon'], capture_output=True)

if __name__ == "__main__":
    main()