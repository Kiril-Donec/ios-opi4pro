#include <stdint.h>
#include <stdio.h>
#include "display.h"

static uint32_t fb[A733_FB_WIDTH * A733_FB_HEIGHT];

int main(int argc, char **argv)
{
    if (argc != 2)
        return 2;
    display_bind(fb, DISPLAY_MONITOR_CLOCKWISE);
    display_stage0_screen(0x43000000, 2);
    FILE *out = fopen(argv[1], "wb");
    if (!out)
        return 1;
    fprintf(out, "P6\n%d %d\n255\n", A733_PORTRAIT_WIDTH,
            A733_PORTRAIT_HEIGHT);
    for (int y = 0; y < A733_PORTRAIT_HEIGHT; ++y)
        for (int x = 0; x < A733_PORTRAIT_WIDTH; ++x) {
            uint32_t rgb = fb[(A733_PORTRAIT_WIDTH - 1 - x) *
                                   A733_FB_WIDTH + y];
            unsigned char p[3] = {(unsigned char)(rgb >> 16),
                                  (unsigned char)(rgb >> 8),
                                  (unsigned char)rgb};
            if (fwrite(p, 1, 3, out) != 3) {
                fclose(out);
                return 1;
            }
        }
    return fclose(out) == 0 ? 0 : 1;
}
