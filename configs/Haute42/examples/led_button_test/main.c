/*
  Simple LED and button test program for the Haute42 board.

  - Blinks the board LED (BOARD_LEDS_PIN)
  - Reads a button (PIN_BUTTON_B1) and prints state over UART

  Notes:
  - If BOARD_LEDS_PIN / PIN_BUTTON_B1 are not defined by the build system,
    fallback values from BoardConfig.h are used (28 / 6).
*/

#include <stdio.h>
#include "pico/stdlib.h"
#include "hardware/gpio.h"

#ifndef BOARD_LEDS_PIN
#define BOARD_LEDS_PIN 28
#endif

#ifndef PIN_BUTTON_B1
#define PIN_BUTTON_B1 6
#endif

int main(void) {
    stdio_init_all();
    gpio_init(BOARD_LEDS_PIN);
    gpio_set_dir(BOARD_LEDS_PIN, GPIO_OUT);

    gpio_init(PIN_BUTTON_B1);
    gpio_set_dir(PIN_BUTTON_B1, GPIO_IN);
    gpio_pull_up(PIN_BUTTON_B1); // Assume button pulls to GND when pressed

    printf("Haute42 LED/Button test started. LED Pin: %d, Button Pin: %d\n", BOARD_LEDS_PIN, PIN_BUTTON_B1);

    bool led_state = false;
    uint32_t last_print = 0;

    while (true) {
        // Blink LED at 1 Hz
        led_state = !led_state;
        gpio_put(BOARD_LEDS_PIN, led_state);

        // Print button state periodically
        uint32_t now = to_ms_since_boot(get_absolute_time());
        if (now - last_print >= 250) {
            int button_val = gpio_get(PIN_BUTTON_B1);
            // Pull-up: 1 = released, 0 = pressed
            if (button_val == 0) {
                printf("Button pressed (PIN %d)\n", PIN_BUTTON_B1);
            } else {
                printf("Button released (PIN %d)\n", PIN_BUTTON_B1);
            }
            last_print = now;
        }

        sleep_ms(500);
    }

    return 0;
}
