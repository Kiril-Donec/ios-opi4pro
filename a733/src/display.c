#include "display.h"
#include "font.h"

/* RGB hex is stored as little-endian B,G,R,X (UEFI BGRA8888). */
static volatile uint32_t *g_framebuffer;
static enum display_rotation g_rotation;

void display_bind(volatile uint32_t *pixels, enum display_rotation rotation)
{
    g_framebuffer = pixels;
    g_rotation = rotation;
}

void display_pixel(int x, int y, uint32_t rgb)
{
    if (!g_framebuffer || x < 0 || x >= A733_PORTRAIT_WIDTH ||
        y < 0 || y >= A733_PORTRAIT_HEIGHT)
        return;

    /* The physical LCD stays 1024x600. Only pixels rotate, not HDMI timing. */
    int phys_x, phys_y;
    if (g_rotation == DISPLAY_MONITOR_CLOCKWISE) {
        phys_x = y;
        phys_y = A733_PORTRAIT_WIDTH - 1 - x;
    } else {
        phys_x = A733_PORTRAIT_HEIGHT - 1 - y;
        phys_y = x;
    }
    g_framebuffer[phys_y * A733_FB_WIDTH + phys_x] = rgb;
}

void display_rect(int x, int y, int width, int height, uint32_t rgb)
{
    for (int row = 0; row < height; ++row)
        for (int col = 0; col < width; ++col)
            display_pixel(x + col, y + row, rgb);
}

static void display_char(int x, int y, char ch, uint32_t rgb, int scale)
{
    if (ch < 32 || ch > 126)
        ch = '?';
    const unsigned char *glyph = font8x16[ch - 32];
    for (int gy = 0; gy < 16; ++gy)
        for (int gx = 0; gx < 8; ++gx)
            if (glyph[gy] & (0x80u >> gx))
                display_rect(x + gx * scale, y + gy * scale,
                             scale, scale, rgb);
}

void display_text(int x, int y, const char *message, uint32_t rgb, int scale)
{
    if (scale < 1 || scale > 4)
        return;
    for (; *message; ++message, x += 8 * scale)
        display_char(x, y, *message, rgb, scale);
}

int display_iphone_width(void)
{
    /* iPhone X userland: 1125x2436, scaled to 1024 portrait pixels high. */
    return (A733_PORTRAIT_HEIGHT * 1125 + 1218) / 2436;
}

static void display_hex(int x, int y, uint64_t value)
{
    const char digits[] = "0123456789ABCDEF";
    char buf[17];
    for (int i = 0; i < 16; ++i)
        buf[i] = digits[(value >> (60 - i * 4)) & 15];
    buf[16] = 0;
    display_text(x, y, buf, 0xD6E2F2, 1);
}

void display_stage0_screen(uint64_t fdt_address, uint64_t current_el)
{
    const uint32_t bg = 0x000000;
    const uint32_t panel = 0x101726;
    const uint32_t green = 0x74E39B;
    const uint32_t white = 0xEDF2F7;
    const uint32_t muted = 0x9AACBF;
    const int width = display_iphone_width();
    const int left = (A733_PORTRAIT_WIDTH - width) / 2;

    display_rect(0, 0, A733_PORTRAIT_WIDTH, A733_PORTRAIT_HEIGHT, bg);
    display_rect(left, 0, width, A733_PORTRAIT_HEIGHT, panel);
    display_rect(left, 0, width, 9, green);
    display_text(left + 22, 54, "iOS A733", white, 3);
    display_text(left + 22, 112, "BOOT STAGE 0", green, 2);
    display_rect(left + 22, 170, width - 44, 2, 0x38506A);

    display_text(left + 22, 215, "Orange Pi 4 Pro", white, 2);
    display_text(left + 22, 261, "Allwinner A733", muted, 2);
    display_text(left + 22, 337, "HDMI framebuffer TEST", green, 1);
    display_text(left + 22, 370, "Portrait 600 x 1024", muted, 1);
    display_text(left + 22, 411, "Framebuffer: BBF11000", muted, 1);
    display_text(left + 22, 470, "FDT:", green, 1);
    display_hex(left + 22, 492, fdt_address);
    display_text(left + 22, 535, "CurrentEL:", green, 1);
    display_hex(left + 22, 557, current_el);
    display_rect(left + 22, 648, width - 44, 3, 0x38506A);
    display_text(left + 22, 701, "XNU NOT LOADED", 0xFFC074, 2);
    display_text(left + 22, 749, "This is a hardware test", muted, 1);
    display_text(left + 22, 780, "No storage writes", muted, 1);
    display_rect(left + 22, 910, width - 44, 12, green);
    display_text(left + 22, 952, "ios-a733 / bring-up", muted, 1);
}
