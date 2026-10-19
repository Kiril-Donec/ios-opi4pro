#ifndef A733_CACHE_H
#define A733_CACHE_H
#include <stddef.h>
#include <stdint.h>

/* Flush written pixels to PoC; the display engine is not CPU-cache-coherent. */
void cache_clean_framebuffer(uintptr_t base, size_t size);
#endif
