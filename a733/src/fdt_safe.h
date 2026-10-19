#ifndef A733_FDT_SAFE_H
#define A733_FDT_SAFE_H
#include <stdint.h>

/* Bounded Linux FDT /chosen read; both 1-cell and 2-cell values work. */
int fdt_chosen_u64(const void *dtb, const char *property, uint64_t *value);

/* The U-Boot-passed *live* FDT must cover the entire requested RAM region.
 * Reject ranges overlapping its memreserve table or /reserved-memory nodes.
 * Fail closed on malformed/missing maps; no memory is written by this check.
 */
int fdt_region_usable(const void *dtb, uint64_t base, uint64_t bytes);

#endif
