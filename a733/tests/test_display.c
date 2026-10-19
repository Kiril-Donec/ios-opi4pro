#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "display.h"

static uint32_t pixels[A733_FB_WIDTH * A733_FB_HEIGHT];

int main(void)
{
    display_bind(pixels, DISPLAY_MONITOR_CLOCKWISE);
    display_pixel(0, 0, 0x112233);
    assert(pixels[599 * 1024] == 0x112233);
    display_pixel(599, 1023, 0x445566);
    assert(pixels[1023] == 0x445566);

    memset(pixels, 0, sizeof(pixels));
    display_bind(pixels, DISPLAY_MONITOR_COUNTERCLOCKWISE);
    display_pixel(0, 0, 0xAABBCC);
    assert(pixels[1023] == 0xAABBCC);
    display_pixel(599, 1023, 0xDDEEFF);
    assert(pixels[599 * 1024] == 0xDDEEFF);

    assert(display_iphone_width() == 473);
    memset(pixels, 0, sizeof(pixels));
    display_bind(pixels, DISPLAY_MONITOR_CLOCKWISE);
    display_stage0_screen(0x43000000, 2);
    /* Left side bar is black; center top bar must be green. */
    const int left = (A733_PORTRAIT_WIDTH - display_iphone_width()) / 2;
    assert(pixels[599 * 1024] == 0);
    assert(pixels[(599 - left) * 1024] == 0x74E39B);
    puts("display rotation, 1125:2436 fit, stage0 drawing: PASS");
    return 0;
}
