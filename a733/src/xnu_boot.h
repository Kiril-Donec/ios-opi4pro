#ifndef A733_XNU_BOOT_H
#define A733_XNU_BOOT_H
#include <stdint.h>

/* Optional: only runs when U-Boot explicitly loads a SWEETXNU payload. */
void stage0_try_xnu(uint64_t fdt_address);
void stage0_a76_entry(uint64_t fdt_address) __attribute__((noreturn));

#endif
