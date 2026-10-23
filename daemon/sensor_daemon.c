#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <pthread.h>
#include <fcntl.h>
#include <linux/input.h>
#include <android/sensor.h>
#include <android/looper.h>
#include <poll.h>

// Поток, который сканирует ВСЕ события и ловит KEY_VOLUMEUP (115)
void* input_thread_func(void* arg) {
    struct pollfd fds[20];
    int num_fds = 0;
    char path[64];
    
    // Подключаемся ко всем доступным каналам ввода (от event0 до event19)
    for (int i = 0; i < 20; i++) {
        snprintf(path, sizeof(path), "/dev/input/event%d", i);
        // O_NONBLOCK обязателен, чтобы один молчащий канал не подвесил чтение остальных
        int fd = open(path, O_RDONLY | O_NONBLOCK);
        if (fd >= 0) {
            fds[num_fds].fd = fd;
            fds[num_fds].events = POLLIN;
            num_fds++;
        }
    }

    if (num_fds == 0) return NULL;

    struct input_event ev;
    while (1) {
        // Ждем активности на любом из каналов
        if (poll(fds, num_fds, -1) > 0) {
            for (int i = 0; i < num_fds; i++) {
                if (fds[i].revents & POLLIN) {
                    while (read(fds[i].fd, &ev, sizeof(ev)) > 0) {
                        // type 1 (EV_KEY), code 115 (VOL UP), value 1 (Нажатие)
                        if (ev.type == 1 && ev.code == 115 && ev.value == 1) {
                            printf(">>> FALSE_POSITIVE <<<\n");
                            fflush(stdout);
                        }
                    }
                }
            }
        }
    }
    return NULL;
}

int main() {
    ASensorManager* sm = ASensorManager_getInstance();
    if (!sm) return 1;

    const ASensor* accel = ASensorManager_getDefaultSensor(sm, ASENSOR_TYPE_ACCELEROMETER);
    const ASensor* gyro = ASensorManager_getDefaultSensor(sm, ASENSOR_TYPE_GYROSCOPE);
    if (!accel || !gyro) return 1;

    // Запускаем универсальный слушатель кнопок
    pthread_t tid;
    pthread_create(&tid, NULL, input_thread_func, NULL);

    ALooper* looper = ALooper_prepare(ALOOPER_PREPARE_ALLOW_NON_CALLBACKS);
    ASensorEventQueue* queue = ASensorManager_createEventQueue(sm, looper, 1, NULL, NULL);

    ASensorEventQueue_enableSensor(queue, accel);
    ASensorEventQueue_enableSensor(queue, gyro);
    
    ASensorEventQueue_setEventRate(queue, accel, 5000); // 200 Гц
    ASensorEventQueue_setEventRate(queue, gyro, 5000);

    float last_gx = 0.0f, last_gy = 0.0f, last_gz = 0.0f;
    printf(">>> START <<<\n");
    fflush(stdout);

    while (1) {
        int ident, events;
        void* data;
        while ((ident = ALooper_pollOnce(-1, NULL, &events, &data)) >= 0) {
            if (ident == 1) {
                ASensorEvent event;
                while (ASensorEventQueue_getEvents(queue, &event, 1) > 0) {
                    if (event.type == ASENSOR_TYPE_GYROSCOPE) {
                        last_gx = event.data[0];
                        last_gy = event.data[1];
                        last_gz = event.data[2];
                    } 
                    else if (event.type == ASENSOR_TYPE_ACCELEROMETER) {
                        printf("%lld %.4f %.4f %.4f %.4f %.4f %.4f\n", 
                               (long long)event.timestamp, 
                               event.data[0], event.data[1], event.data[2], 
                               last_gx, last_gy, last_gz);
                        fflush(stdout);
                    }
                }
            }
        }
    }
    return 0;
}