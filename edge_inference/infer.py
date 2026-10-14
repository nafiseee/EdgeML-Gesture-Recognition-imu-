import subprocess, sys, collections
import numpy as np
import os
try:
    w = dict(np.load('weights.npz'))
except Exception as e:
    print(f"Error loading weights: {e}")
    sys.exit(1)

def relu(x): return np.maximum(0, x)

def softmax(x): 
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum(axis=0)

def conv1d(x, w_c, b_c, stride, pad):
    out_c, _, k = w_c.shape
    x_pad = np.pad(x, ((0,0), (pad, pad)), mode='constant')
    out_len = (x.shape[1] + 2*pad - k) // stride + 1
    out = np.zeros((out_c, out_len))
    for i in range(out_len):
        out[:, i] = np.sum(w_c * x_pad[:, i*stride:i*stride+k], axis=(1,2)) + b_c
    return out

def batchnorm1d(x, w_bn, b_bn, mean, var, eps=1e-5):
    std = np.sqrt(var + eps)
    return ((x - mean[:, None]) / std[:, None]) * w_bn[:, None] + b_bn[:, None]

def maxpool1d(x, k, stride):
    out_len = (x.shape[1] - k) // stride + 1
    out = np.zeros((x.shape[0], out_len))
    for i in range(out_len):
        out[:, i] = np.max(x[:, i*stride:i*stride+k], axis=1)
    return out

def predict(window):
    data = np.array(window, dtype=np.float32).T 
    data -= np.mean(data[:, :10], axis=1, keepdims=True)
    x = (data - np.mean(data, axis=1, keepdims=True)) / (np.std(data, axis=1, keepdims=True) + 1e-6)
    
    x = conv1d(x, w['features.0.weight'], w['features.0.bias'], 2, 7)
    x = batchnorm1d(x, w['features.1.weight'], w['features.1.bias'], w['features.1.running_mean'], w['features.1.running_var'])
    x = relu(x)
    x = maxpool1d(x, 2, 2) 
    
    x = conv1d(x, w['features.4.weight'], w['features.4.bias'], 2, 2)
    x = batchnorm1d(x, w['features.5.weight'], w['features.5.bias'], w['features.5.running_mean'], w['features.5.running_var'])
    x = relu(x)
    
    x = np.mean(x, axis=1)
    logits = np.dot(w['classifier.weight'], x) + w['classifier.bias'] 
    
    probs = softmax(logits)
    
    print(f"\n[DEBUG PROBS] Background:{probs[0]:.3f} | Class1:{probs[1]:.3f} | Class2:{probs[2]:.3f} | Class3:{probs[3]:.3f}")
    
    conf = np.max(probs)
    pred = np.argmax(probs)
    
    return pred, conf

    

def main():
    labels = {1: "TELEGRAM", 2: "SPOTIFY", 3: "CIRCLE"}
    buf = collections.deque(maxlen=300)
    
    print("[INIT] Starting sensor_daemon via root...")
    p = subprocess.Popen(['su', '-c', './sensor_daemon'], stdout=subprocess.PIPE, text=True)
    print("[WAIT] Ready. Perform gesture, THEN press volume down...\n")
    
    collecting = False
    
    try:
        for line in iter(p.stdout.readline, ''):
            line = line.strip()
            if not line: continue
            
            if line == ">>> TRIGGER <<<":
                print("\n[TRIGGER] Tap detected. Analyzing past 1.5s instantly...")
                buf.clear()
                collecting = True
                continue
                
            if collecting:
                parts = line.split()
                if len(parts) == 7:
                    try:
                        buf.append(tuple(map(float, parts[1:7])))
                    except ValueError:
                        pass
                        
                if len(buf) == 300:
                    collecting = False 
                    
                    cls, conf = predict(buf)
                    if cls != 0:
                        gesture_name = labels[cls]
                        print(f"[MATCH] >> {gesture_name} << (Conf: {conf:.3f})\n")
                        
                        os.system("su -c 'input keyevent 24' > /dev/null 2>&1")
                        
                        # 2. Выполняем макрос
                        os.system(f'am broadcast -a edge.gesture.DETECTED -p com.arlosoft.macrodroid --es "name" "{gesture_name}" > /dev/null 2>&1')
                    else:
                        print(f"[IGNORE] Background (Conf: {conf:.3f})\n")
                        os.system("su -c 'input keyevent 24' > /dev/null 2>&1")
                    
    except KeyboardInterrupt:
        print("\n[EXIT] Terminating...")
    finally:
        p.terminate()
        subprocess.run(['su', '-c', 'killall sensor_daemon'], capture_output=True)
if __name__ == "__main__":
    main()