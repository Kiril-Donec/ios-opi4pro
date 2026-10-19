#include <stdint.h>
#include "display.h"
#include "cache.h"
#include "xnu_boot.h"

/*
 * Inherits the v59 BGRA framebuffer at 0xBBF11000, tested on the board in v3.
 * Without explicit payload parameters the working screen-only test remains.
 * With an XNU payload v4 can enter the experimental CPU/interrupt handoff.
 * Neither mode writes block storage or display controller registers.
 */
void stage0_main(uint64_t fdt_address, uint64_t current_el)
{
    display_bind((volatile uint32_t *)(uintptr_t)A733_FB_BASE,
                 DISPLAY_MONITOR_CLOCKWISE);
    // A persistent-on-fault marker if full-screen painting fails afterwards.
    display_rect(0, 0, A733_PORTRAIT_WIDTH, 56, 0x003060);
    display_text(8, 8, "STAGE0 ENTERED", 0xffffff, 2);
    cache_clean_framebuffer(A733_FB_BASE,
                            A733_FB_WIDTH * A733_FB_HEIGHT * sizeof(uint32_t));
    display_stage0_screen(fdt_address, current_el >> 2);
    cache_clean_framebuffer(A733_FB_BASE,
                            A733_FB_WIDTH * A733_FB_HEIGHT * sizeof(uint32_t));
    stage0_try_xnu(fdt_address);
}

static void fault_hex(int y, uint64_t value)
{
    const char digits[] = "0123456789ABCDEF";
    char s[17];
    for (int i = 0; i < 16; ++i)
        s[i] = digits[(value >> (60 - 4 * i)) & 15];
    s[16] = 0;
    display_text(52, y, s, 0xFFFFFF, 2);
}

void stage0_exception(uint64_t slot, uint64_t esr, uint64_t elr, uint64_t far)
{
    display_bind((volatile uint32_t *)(uintptr_t)A733_FB_BASE,
                 DISPLAY_MONITOR_CLOCKWISE);
    display_rect(0, 0, A733_PORTRAIT_WIDTH, A733_PORTRAIT_HEIGHT, 0x430014);
    display_text(52, 64, "STAGE0 EXCEPTION", 0xFFFFFF, 2);
    display_text(52, 190, "VECTOR", 0xFFDD91, 2);
    fault_hex(226, slot);
    display_text(52, 310, "ESR_EL1", 0xFFDD91, 2);
    fault_hex(348, esr);
    display_text(52, 430, "ELR_EL1", 0xFFDD91, 2);
    fault_hex(468, elr);
    display_text(52, 550, "FAR_EL1", 0xFFDD91, 2);
    fault_hex(588, far);
    display_text(52, 762, "PHOTO THIS SCREEN", 0xFFFFFF, 2);
    cache_clean_framebuffer(A733_FB_BASE,
                            A733_FB_WIDTH * A733_FB_HEIGHT * sizeof(uint32_t));
    for (;;)
        __asm__ volatile("wfe");
}
