#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <pthread.h>
#include <fcntl.h>
#include <linux/input.h>
#include <android/sensor.h>
#include <android/looper.h>
#include <time.h>

#define WINDOW_SIZE 300
#define OFFSET 50
#define BUFFER_SIZE (WINDOW_SIZE + OFFSET) // 350 точек = 1.75 сек

volatile int trigger_flag = 0; // Флаг связи между потоками

float history[BUFFER_SIZE][6];
long long timestamps[BUFFER_SIZE];
int head = 0;
int is_buffer_full = 0; 
float last_gx = 0.0f, last_gy = 0.0f, last_gz = 0.0f;

// Поток, который слушает хардварную кнопку громкости
void* input_thread_func(void* arg) {
    int fd = open("/dev/input/event0", O_RDONLY);
    if (fd < 0) {
        printf("Ошибка: не могу открыть /dev/input/event0\n");
        return NULL;
    }
    
    struct input_event ev;
    while (read(fd, &ev, sizeof(ev)) > 0) {
        // ev.value == 1 означает DOWN (нажатие). 0 - отпускание.
        if (ev.type == EV_KEY && ev.code == KEY_VOLUMEDOWN && ev.value == 1) {
            trigger_flag = 1; // Сигнализируем основному потоку
        }
    }
    
    close(fd);
    return NULL;
}

int main() {
    ASensorManager* sm = ASensorManager_getInstance();
    if (!sm) return 1;

    const ASensor* accel = ASensorManager_getDefaultSensor(sm, ASENSOR_TYPE_ACCELEROMETER);
    const ASensor* gyro = ASensorManager_getDefaultSensor(sm, ASENSOR_TYPE_GYROSCOPE);
    
    if (!accel || !gyro) {
        printf("Ошибка: IMU не найдены.\n");
        return 1;
    }

    // Запускаем слушатель кнопки в отдельном потоке
    pthread_t tid;
    pthread_create(&tid, NULL, input_thread_func, NULL);

    ALooper* looper = ALooper_prepare(ALOOPER_PREPARE_ALLOW_NON_CALLBACKS);
    ASensorEventQueue* queue = ASensorManager_createEventQueue(sm, looper, 1, NULL, NULL);

    ASensorEventQueue_enableSensor(queue, accel);
    ASensorEventQueue_enableSensor(queue, gyro);
    
    ASensorEventQueue_setEventRate(queue, accel, 5000);
    ASensorEventQueue_setEventRate(queue, gyro, 5000);

    printf("Демон запущен (Vol Down Trigger). Жду жеста и клика...\n");
    fflush(stdout);

    while (1) {
        // Проверяем, не нажал ли второй поток кнопку
        if (trigger_flag) {
            if (!is_buffer_full) {
                printf("Слишком рано, буфер еще не накопил 1.75 сек.\n");
            } else {
                printf(">>> TRIGGER <<<\n");
                
                
                for (int i = 0; i < WINDOW_SIZE; i++) {
                    int idx = (head + i) % BUFFER_SIZE;
                    printf("%lld %.4f %.4f %.4f %.4f %.4f %.4f\n", 
                           timestamps[idx], 
                           history[idx][0], history[idx][1], history[idx][2], 
                           history[idx][3], history[idx][4], history[idx][5]);
                }
            }
            trigger_flag = 0;
            fflush(stdout);
        }

        int ident, events;
        void* data;
        
        while ((ident = ALooper_pollOnce(5, NULL, &events, &data)) >= 0) {
            if (ident == 1) {
                ASensorEvent event;
                while (ASensorEventQueue_getEvents(queue, &event, 1) > 0) {
                    
                    if (event.type == ASENSOR_TYPE_GYROSCOPE) {
                        last_gx = event.data[0];
                        last_gy = event.data[1];
                        last_gz = event.data[2];
                    } 
                    else if (event.type == ASENSOR_TYPE_ACCELEROMETER) {
                        history[head][0] = event.data[0];
                        history[head][1] = event.data[1];
                        history[head][2] = event.data[2];
                        history[head][3] = last_gx;
                        history[head][4] = last_gy;
                        history[head][5] = last_gz;
                        timestamps[head] = (long long)event.timestamp;
                        
                        head = (head + 1) % BUFFER_SIZE;
                        if (head == 0) is_buffer_full = 1;
                    }
                }
            }
        }
    }
    return 0;
}