#include <stdint.h>
#include "gic_a733.h"

#define GICD 0x03400000ULL
#define GICR 0x03460000ULL
#define GICR_FRAMES 8U
#define GICR_STRIDE 0x20000ULL
#define GICR_TYPER 0x0008
#define GICR_WAKER 0x0014
#define GICR_SGI 0x10000
#define GICR_IGROUPR0 (GICR_SGI + 0x0080)
#define GICR_ISENABLER0 (GICR_SGI + 0x0100)
#define GICR_IPRIORITYR (GICR_SGI + 0x0400)

static uint32_t rd32(uint64_t address)
{
    return *(volatile uint32_t *)(uintptr_t)address;
}

static uint64_t rd64(uint64_t address)
{
    return *(volatile uint64_t *)(uintptr_t)address;
}

static void wr32(uint64_t address, uint32_t value)
{
    *(volatile uint32_t *)(uintptr_t)address = value;
}

static void wr8(uint64_t address, uint8_t value)
{
    *(volatile uint8_t *)(uintptr_t)address = value;
}

int gic_a733_prepare_a76(void)
{
    uint64_t mpidr;
    __asm__ volatile("mrs %0, mpidr_el1" : "=r"(mpidr));
    /* Aff3:Aff2:Aff1:Aff0 = 0x00000600 for the first Cortex-A76. */
    uint32_t affinity = (uint32_t)(mpidr & 0xFFFFFF) |
                        (uint32_t)((mpidr >> 8) & 0xFF000000);
    if (affinity != 0x600U)
        return -1;

    uint64_t redist = 0;
    for (unsigned i = 0; i < GICR_FRAMES; ++i) {
        const uint64_t candidate = GICR + i * GICR_STRIDE;
        uint64_t typer = rd64(candidate + GICR_TYPER);
        if ((uint32_t)(typer >> 32) == affinity) {
            redist = candidate;
            break;
        }
        if (typer & (1ULL << 4))
            break;
    }
    if (!redist)
        return -2;

    uint64_t sre;
    __asm__ volatile("mrs %0, icc_sre_el1" : "=r"(sre));
    if (!(sre & 1)) {
        uint64_t enable = sre | 1;
        __asm__ volatile("msr icc_sre_el1, %0; isb" :: "r"(enable) : "memory");
        __asm__ volatile("mrs %0, icc_sre_el1" : "=r"(sre));
    }
    if (!(sre & 1))
        return -3;

    uint32_t ctlr = rd32(GICD);
    /* GICD_CTLR bit 4 = ARE_NS, bit 1 = EnableGrp1NS. Do not turn on
     * Group 0 (bit 0): EL1 must not reconfigure secure interrupts. */
    wr32(GICD, ctlr | 0x12U);
    for (unsigned i = 0; i < 1000000 && (rd32(GICD) & (1U << 31)); ++i)
        if (i == 999999)
            return -4;

    uint32_t waker = rd32(redist + GICR_WAKER);
    if (waker & 2)
        wr32(redist + GICR_WAKER, waker & ~2U);
    for (unsigned i = 0; i < 1000000 &&
         (rd32(redist + GICR_WAKER) & 4); ++i)
        if (i == 999999)
            return -5;

    wr32(redist + GICR_IGROUPR0, 0xFFFFFFFFU);
    for (unsigned i = 0; i < 32; ++i)
        wr8(redist + GICR_IPRIORITYR + i, 0xA0);
    wr32(redist + GICR_ISENABLER0, (1U << 27) | (1U << 1));

    uint64_t icc;
    __asm__ volatile("mrs %0, icc_ctlr_el1" : "=r"(icc));
    icc &= ~2ULL; /* EOIR also deactivates interrupt. */
    __asm__ volatile(
        "msr icc_ctlr_el1, %0\n"
        "msr icc_pmr_el1, %1\n"
        "msr icc_igrpen1_el1, %2\n"
        "dsb sy\n"
        "isb\n"
        :: "r"(icc), "r"(0xF0ULL), "r"(1ULL) : "memory");
    return 0;
}
