 
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <android/sensor.h>
#include <android/looper.h>
#include <time.h>

#define WINDOW_SIZE 300 // 300 точек = 1.5 секунды при 200 Гц

int main() {
    ASensorManager* sm = ASensorManager_getInstance();
    if (!sm) return 1;

    // 1. Ищем наши IMU датчики
    const ASensor* accel = ASensorManager_getDefaultSensor(sm, ASENSOR_TYPE_ACCELEROMETER);
    const ASensor* gyro = ASensorManager_getDefaultSensor(sm, ASENSOR_TYPE_GYROSCOPE);
    
    if (!accel || !gyro) {
        printf("Ошибка: IMU датчики не найдены.\n");
        return 1;
    }

    // 2. Ищем твой вендорский триггер dbtap (33171045)
    ASensorList sensor_list;
    int sensor_count = ASensorManager_getSensorList(sm, &sensor_list);
    const ASensor* tapSensor = NULL;

    for (int i = 0; i < sensor_count; i++) {
        if (ASensor_getType(sensor_list[i]) == 33171045) { 
            tapSensor = sensor_list[i];
            break;
        }
    }

    if (!tapSensor) {
        printf("Ошибка: Датчик dbtap (33171045) не найден.\n");
        return 1;
    }

    ALooper* looper = ALooper_prepare(ALOOPER_PREPARE_ALLOW_NON_CALLBACKS);
    ASensorEventQueue* queue = ASensorManager_createEventQueue(sm, looper, 1, NULL, NULL);

    // Включаем все три сенсора
    ASensorEventQueue_enableSensor(queue, tapSensor);
    ASensorEventQueue_enableSensor(queue, accel);
    ASensorEventQueue_enableSensor(queue, gyro);
    
    // Ставим рейты: Триггер просто слушаем, IMU ставим на 200 Гц (5000 мкс)
    ASensorEventQueue_setEventRate(queue, tapSensor, 10000); 
    ASensorEventQueue_setEventRate(queue, accel, 5000);
    ASensorEventQueue_setEventRate(queue, gyro, 5000);

    float last_gx = 0.0f, last_gy = 0.0f, last_gz = 0.0f;
    int imu_points_collected = 0;
    int is_recording = 0;

    printf("Демон запущен. Жду двойного тапа...\n");
    fflush(stdout);

    while (1) {
        int ident, events;
        void* data;
        
        while ((ident = ALooper_pollOnce(-1, NULL, &events, &data)) >= 0) {
            if (ident == 1) {
                ASensorEvent event;
                while (ASensorEventQueue_getEvents(queue, &event, 1) > 0) {
                    
                    // --- ОБРАБОТКА ТРИГГЕРА ---
                    if (event.type == 33171045) {
                        // Если мы уже пишем жест, игнорируем новые тапы
                        if (!is_recording) {
                            printf(">>> TRIGGER <<<\n");
                            fflush(stdout);
                            is_recording = 1;
                            imu_points_collected = 0;
                        }
                    } 
                    
                    // --- ОБРАБОТКА ГИРОСКОПА ---
                    else if (event.type == ASENSOR_TYPE_GYROSCOPE) {
                        last_gx = event.data[0];
                        last_gy = event.data[1];
                        last_gz = event.data[2];
                    } 
                    
                    // --- ОБРАБОТКА АКСЕЛЕРОМЕТРА (Печатаем только если is_recording == 1) ---
                    else if (event.type == ASENSOR_TYPE_ACCELEROMETER) {
                        if (is_recording) {
                            printf("%lld %.4f %.4f %.4f %.4f %.4f %.4f\n", 
                                   (long long)event.timestamp, 
                                   event.data[0], event.data[1], event.data[2], 
                                   last_gx, last_gy, last_gz);
                            fflush(stdout);
                            
                            imu_points_collected++;
                            // Как только собрали 300 точек, выключаем запись до следующего тапа
                            if (imu_points_collected >= WINDOW_SIZE) {
                                is_recording = 0;
                            }
                        }
                    }
                }
            }
        }
    }
    return 0;
}