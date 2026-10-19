#include "cache.h"

void cache_clean_framebuffer(uintptr_t base, size_t size)
{
    uint64_t ctr;
    __asm__ volatile("mrs %0, ctr_el0" : "=r"(ctr));
    const uintptr_t line_size = (uintptr_t)4 << ((ctr >> 16) & 15);
    const uintptr_t end = base + size;
    __asm__ volatile("dsb sy" ::: "memory");
    for (uintptr_t address = base & ~(line_size - 1); address < end;
         address += line_size) {
        __asm__ volatile("dc cvac, %0" :: "r"(address) : "memory");
    }
    __asm__ volatile("dsb sy; isb" ::: "memory");
}
