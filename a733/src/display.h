#ifndef A733_DISPLAY_H
#define A733_DISPLAY_H

#include <stdint.h>

/* Inherited U-Boot/EDK2 v59 framebuffer: confirmed by real v3 stage0 photo. */
#define A733_FB_BASE 0xBBF11000ULL
#define A733_FB_WIDTH 1024
#define A733_FB_HEIGHT 600
#define A733_PORTRAIT_WIDTH 600
#define A733_PORTRAIT_HEIGHT 1024

enum display_rotation {
    DISPLAY_MONITOR_CLOCKWISE = 0,
    DISPLAY_MONITOR_COUNTERCLOCKWISE = 1,
};

void display_bind(volatile uint32_t *pixels, enum display_rotation rotation);
void display_pixel(int x, int y, uint32_t rgb);
void display_rect(int x, int y, int width, int height, uint32_t rgb);
void display_text(int x, int y, const char *message, uint32_t rgb, int scale);
void display_stage0_screen(uint64_t fdt_address, uint64_t current_el);
int display_iphone_width(void);

#endif
