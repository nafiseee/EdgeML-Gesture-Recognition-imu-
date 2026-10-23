import numpy as np

def relu(x): return np.maximum(0, x)
def softmax(x): 
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum(axis=0)

def conv1d(x, w_c, b_c, stride, pad):
    out_c, _, k = w_c.shape
    x_pad = np.pad(x, ((0,0), (pad, pad)), mode='constant')
    out_len = (x.shape[1] + 2*pad - k) // stride + 1
    out = np.zeros((out_c, out_len), dtype=np.float32)
    for i in range(out_len):
        out[:, i] = np.sum(w_c * x_pad[:, i*stride:i*stride+k], axis=(1,2)) + b_c
    return out

def batchnorm1d(x, w_bn, b_bn, mean, var, eps=1e-5):
    std = np.sqrt(var + eps)
    return ((x - mean[:, None]) / std[:, None]) * w_bn[:, None] + b_bn[:, None]

def maxpool1d(x, k, stride, pad=0):
    if pad > 0: x = np.pad(x, ((0,0), (pad, pad)), constant_values=-np.inf)
    out_len = (x.shape[1] - k) // stride + 1
    out = np.zeros((x.shape[0], out_len), dtype=np.float32)
    for i in range(out_len): out[:, i] = np.max(x[:, i*stride:i*stride+k], axis=1)
    return out

def predict(window, w):
    data = np.array(window, dtype=np.float32).T
    data -= np.mean(data[:, :10], axis=1, keepdims=True)
    x = (data - np.mean(data, axis=1, keepdims=True)) / (np.std(data, axis=1, keepdims=True) + 1e-6)
    # Слой 0: Conv1d
    x = conv1d(x, w['features.0.weight'], w['features.0.bias'], stride=3, pad=1)
    x = batchnorm1d(x, w['features.1.weight'], w['features.1.bias'], w['features.1.running_mean'], w['features.1.running_var'])
    x = relu(x)
    x = maxpool1d(x, k=2, stride=2, pad=0)
    # Слой 4: Conv1d
    x = conv1d(x, w['features.4.weight'], w['features.4.bias'], stride=2, pad=2)
    x = batchnorm1d(x, w['features.5.weight'], w['features.5.bias'], w['features.5.running_mean'], w['features.5.running_var'])
    x = relu(x)
    x = maxpool1d(x, k=2, stride=2, pad=0)
    # Слой 8: Conv1d
    x = conv1d(x, w['features.8.weight'], w['features.8.bias'], stride=2, pad=1)
    x = batchnorm1d(x, w['features.9.weight'], w['features.9.bias'], w['features.9.running_mean'], w['features.9.running_var'])
    x = relu(x)
    # Слой 11: Conv1d
    x = conv1d(x, w['features.11.weight'], w['features.11.bias'], stride=1, pad=1)
    x = batchnorm1d(x, w['features.12.weight'], w['features.12.bias'], w['features.12.running_mean'], w['features.12.running_var'])
    x = relu(x)

    # AdaptiveAvgPool1d(2) + Classifier
    x = np.mean(x.reshape(x.shape[0], 2, -1), axis=2).flatten()
    logits = np.dot(w['classifier.weight'], x) + w['classifier.bias']
    probs = softmax(logits)
    return np.argmax(probs), np.max(probs)
