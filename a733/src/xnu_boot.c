#include <stdint.h>
#include "xnu_boot.h"
#include "xnu_payload.h"
#include "fdt_safe.h"
#include "display.h"
#include "cache.h"
#include "gic_a733.h"

#define A733_BOOT_A76_MPIDR 0x600ULL
#define PSCI_CPU_ON 0xC4000003ULL
#define PSCI_VERSION 0x84000000ULL

static uint64_t reg_mpidr(void)
{
    uint64_t value;
    __asm__ volatile("mrs %0, mpidr_el1" : "=r"(value));
    return value & 0xFF00FFFFFFULL;
}

static uint64_t reg_current_el(void)
{
    uint64_t value;
    __asm__ volatile("mrs %0, CurrentEL" : "=r"(value));
    return value >> 2;
}

static uint64_t reg_mmfr0(void)
{
    uint64_t value;
    __asm__ volatile("mrs %0, id_aa64mmfr0_el1" : "=r"(value));
    return value;
}

static uint64_t reg_sctlr1(void)
{
    uint64_t value;
    __asm__ volatile("mrs %0, sctlr_el1" : "=r"(value));
    return value;
}

static int64_t smc64(uint64_t fid, uint64_t a1, uint64_t a2, uint64_t a3)
{
    register uint64_t x0 __asm__("x0") = fid;
    register uint64_t x1 __asm__("x1") = a1;
    register uint64_t x2 __asm__("x2") = a2;
    register uint64_t x3 __asm__("x3") = a3;
    __asm__ volatile("smc #0" : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3) : :
                     "x4", "x5", "x6", "x7", "x8", "x9", "x10", "x11",
                     "x12", "x13", "x14", "x15", "x16", "x17", "cc", "memory");
    return (int64_t)x0;
}

static void screen_message(const char *title, const char *detail)
{
    /* Overwrite only the existing XNU status area; keep confirmed v3 layout. */
    const int left = (A733_PORTRAIT_WIDTH - display_iphone_width()) / 2 + 22;
    display_rect(left, 690, display_iphone_width() - 44, 150, 0x101726);
    display_text(left, 708, title, 0x74E39B, 1);
    if (detail)
        display_text(left, 744, detail, 0xEDF2F7, 1);
    cache_clean_framebuffer(A733_FB_BASE, A733_FB_WIDTH * A733_FB_HEIGHT * 4U);
}

static void screen_hex(const char *title, uint64_t val)
{
    const char digits[] = "0123456789ABCDEF";
    char line[17];
    for (int i = 0; i < 16; ++i)
        line[i] = digits[(val >> (60 - 4 * i)) & 15];
    line[16] = 0;
    screen_message(title, line);
}

extern char a76_secondary_entry[];

static void run_xnu_from_a76(const struct xnu_payload *p,
                             const struct xnu_plan *plan)
{
    if (reg_current_el() != 1) {
        screen_hex("XNU: EXPECTED EL1", reg_current_el());
        return;
    }
    /* Never copy to physical RAM using an unknown virtual mapping. */
    if (reg_sctlr1() & ((1ULL << 0) | (1ULL << 2))) {
        screen_hex("XNU: MMU OR DCACHE ON", reg_sctlr1());
        return;
    }
    /* ID_AA64MMFR0_EL1.TGran16: 0 means unsupported, 1 supported. */
    const uint64_t tgran16 = (reg_mmfr0() >> 20) & 15;
    if (tgran16 != 1 && tgran16 != 2) {
        screen_message("XNU: 16K PAGES UNSUPPORTED", 0);
        return;
    }
    int gic_status = gic_a733_prepare_a76();
    if (gic_status) {
        screen_hex("XNU: GIC PREP FAILED", (uint64_t)(int64_t)gic_status);
        return;
    }
    screen_message("XNU: INSTALLING KERNEL", "HIGH RAM 0x100000000");
    xnu_install(p, plan);
    /* Hand over the physical HDMI framebuffer to the XNU panic console.
     * Keep the portrait timing established by U-Boot/Stage0, but remove
     * the old blue Stage0 panel; the early XNU renderer owns pixels now. */
    display_rect(0, 0, A733_PORTRAIT_WIDTH, A733_PORTRAIT_HEIGHT, 0x000000);
    cache_clean_framebuffer(A733_FB_BASE, A733_FB_WIDTH * A733_FB_HEIGHT * 4U);
    typedef void (*entry_fn)(uint64_t boot_args_pa);
    ((entry_fn)(uintptr_t)plan->entry_pa)(plan->boot_args_pa);
    screen_message("XNU RETURNED UNEXPECTEDLY", 0);
}

void stage0_try_xnu(uint64_t fdt_address)
{
    uint64_t start, end;
    uint64_t probe = 0;
    if (reg_current_el() != 1) {
        screen_hex("XNU: BOOT CORE MUST BE EL1", reg_current_el());
        return;
    }
    if (reg_sctlr1() & ((1ULL << 0) | (1ULL << 2))) {
        screen_hex("XNU: DIRECT PA NOT SAFE", reg_sctlr1());
        return;
    }
    const void *dt = (const void *)(uintptr_t)fdt_address;
    const int probe_only = fdt_chosen_u64(dt, "a733,a76-probe", &probe) && probe == 1;
    /* U-Boot/BL31 may leave Linux initrd properties in /chosen even when
     * bootm was called with "-" (no ramdisk). Those are not our payload.
     * The A76 probe must never validate or dereference an initrd range.
     * Use opt-in, A733-specific keys exclusively for a real XNU handoff. */
    const int has_start = !probe_only &&
        fdt_chosen_u64(dt, "a733,xnu-payload-start", &start);
    const int has_end = !probe_only &&
        fdt_chosen_u64(dt, "a733,xnu-payload-end", &end);
    if (!has_start && !has_end && !probe_only)
        return; /* Unchanged v3 screen diagnostic unless explicitly opted in. */
    if (has_start != has_end) {
        screen_message("XNU: INCOMPLETE PAYLOAD RANGE", 0);
        return;
    }
    if ((has_start || has_end) && (start != A733_XNU_PAYLOAD_PA || end <= start ||
        end - start > A733_XNU_PAYLOAD_LIMIT)) {
        screen_message("XNU: PAYLOAD ADDRESS REJECTED", 0);
        return;
    }
    if (has_start && (!fdt_region_usable(dt, A733_XNU_RAM_BASE, A733_XNU_RAM_SIZE) ||
                      !fdt_region_usable(dt, start, end - start))) {
        screen_message("XNU: LIVE FDT RAM UNSAFE", "CHECK U-BOOT DRAM SIZE");
        return;
    }

    struct xnu_plan plan;
    const struct xnu_payload *p = 0;
    if (has_start) {
        p = (const struct xnu_payload *)(uintptr_t)start;
        const char *problem = xnu_validate(p, end - start, start, &plan);
        if (problem) {
            screen_message("XNU PAYLOAD ERROR", problem);
            return;
        }
        cache_clean_framebuffer((uintptr_t)start, (size_t)(end - start));
    }

    const uint64_t mpidr = reg_mpidr();
    if (mpidr == A733_BOOT_A76_MPIDR) {
        if (p)
            run_xnu_from_a76(p, &plan);
        else
            screen_hex("A76 PROBE: MMFR0", reg_mmfr0());
        return;
    }
    if (reg_current_el() != 1) {
        screen_hex("XNU: BOOT CORE NOT EL1", reg_current_el());
        return;
    }
    screen_hex(p ? "XNU: STARTING A76 0x600" : "PROBE: STARTING A76 0x600", mpidr);
    const int64_t version = smc64(PSCI_VERSION, 0, 0, 0);
    if (version < 0) {
        screen_hex("PSCI VERSION FAILED", (uint64_t)version);
        return;
    }
    __asm__ volatile("dsb sy" ::: "memory");
    const int64_t rc = smc64(PSCI_CPU_ON, A733_BOOT_A76_MPIDR,
                              (uintptr_t)a76_secondary_entry, fdt_address);
    if (rc) {
        screen_hex("PSCI CPU_ON FAILURE", (uint64_t)rc);
        return;
    }
    for (;;)
        __asm__ volatile("wfe"); /* A55 does not touch RAM once A76 runs. */
}

void stage0_a76_entry(uint64_t fdt_address)
{
    display_bind((volatile uint32_t *)(uintptr_t)A733_FB_BASE,
                 DISPLAY_MONITOR_CLOCKWISE);
    if (reg_mpidr() != A733_BOOT_A76_MPIDR) {
        screen_hex("PSCI TARGET IS NOT A76", reg_mpidr());
    } else {
        screen_message("A76 ONLINE", "Checking XNU payload");
        stage0_try_xnu(fdt_address);
    }
    for (;;)
        __asm__ volatile("wfe");
}
