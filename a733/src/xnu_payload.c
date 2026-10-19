#include "xnu_payload.h"
#include "display.h"

_Static_assert(offsetof(struct xnu_payload, segs) == 0x2a8,
               "SWEETXNU header size");
_Static_assert(offsetof(struct xnu_boot_args, Video) == 40,
               "Apple boot_video offset");
_Static_assert(offsetof(struct xnu_boot_args, CommandLine) == 108,
               "Apple command line offset");
_Static_assert(sizeof(struct xnu_boot_args) == 736,
               "Apple boot_args revision 2 size");

static int range_ok(uint64_t offset, uint64_t size, uint64_t limit)
{
    return offset <= limit && size <= limit - offset;
}

static int add_ok(uint64_t a, uint64_t b, uint64_t *out)
{
    if (b > UINT64_MAX - a)
        return 0;
    *out = a + b;
    return 1;
}

static int magic_ok(const char bytes[8])
{
    const char expected[8] = {'A','7','3','3','X','N','U','1'};
    for (int i = 0; i < 8; ++i)
        if (bytes[i] != expected[i])
            return 0;
    return 1;
}

const char *xnu_validate(const struct xnu_payload *p, uint64_t len,
                         uint64_t payload_pa, struct xnu_plan *out)
{
    uint64_t pa_end, kernel_bytes, adt_end, ba, top;
    const uint64_t hdr = offsetof(struct xnu_payload, segs);

    if (!p || !out || (payload_pa & 7))
        return "bad payload pointer";
    if (payload_pa != A733_XNU_PAYLOAD_PA ||
        len > A733_XNU_PAYLOAD_LIMIT || len < hdr)
        return "payload address or length";
    if (!magic_ok(p->magic) || p->version != 1 ||
        p->nsegs == 0 || p->nsegs > A733_XNU_MAX_SEGS)
        return "not A733XNU1 v1";
    if (!range_ok(hdr, (uint64_t)p->nsegs * sizeof(struct xnu_segment), len))
        return "truncated segments";
    if (p->phys_base != A733_XNU_RAM_BASE ||
        p->mem_size != A733_XNU_RAM_SIZE ||
        (p->virt_base & ((32ULL * 1024 * 1024) - 1)))
        return "kernel memory layout is not A733";
    if (!add_ok(payload_pa, len, &pa_end) || pa_end > A733_XNU_RAM_BASE)
        return "source overlaps kernel RAM";
    if ((p->adt_off & 7) || p->adt_size < 8 ||
        p->adt_size > UINT32_MAX ||
        !range_ok(p->adt_off, p->adt_size, len))
        return "ADT bounds";
    /* The Apple DT parser expects the root node's property/child counts.
     * Reject a missing/corrupt tree before switching CPUs or writing RAM. */
    const uint8_t *adt = (const uint8_t *)p + p->adt_off;
    const uint32_t root_props = (uint32_t)adt[0] | (uint32_t)adt[1] << 8 |
                                (uint32_t)adt[2] << 16 | (uint32_t)adt[3] << 24;
    const uint32_t root_children = (uint32_t)adt[4] | (uint32_t)adt[5] << 8 |
                                   (uint32_t)adt[6] << 16 | (uint32_t)adt[7] << 24;
    if (!root_props || !root_children || root_props > 1024 ||
        root_children > 1024)
        return "invalid ADT root";
    if (p->kernel_end < p->virt_base ||
        (p->kernel_end & (A733_XNU_PAGE - 1)))
        return "kernel end alignment";
    kernel_bytes = p->kernel_end - p->virt_base;
    if (kernel_bytes > p->mem_size)
        return "kernel exceeds RAM";
    if (!add_ok(p->phys_base, kernel_bytes, &out->adt_pa) ||
        !add_ok(out->adt_pa, p->adt_size, &adt_end))
        return "ADT address overflow";
    if (adt_end > p->phys_base + p->mem_size ||
        adt_end > UINT64_MAX - (A733_XNU_PAGE - 1))
        return "no room for ADT";
    ba = (adt_end + A733_XNU_PAGE - 1) & ~(A733_XNU_PAGE - 1);
    if (!add_ok(ba, A733_XNU_PAGE, &top) ||
        top > p->phys_base + p->mem_size)
        return "no room for boot_args";
    if (p->entry_va < p->virt_base ||
        !range_ok(p->entry_va - p->virt_base, 4, kernel_bytes))
        return "entry outside kernel";

    int entry_in_segment = 0;
    for (uint32_t i = 0; i < p->nsegs; ++i) {
        const struct xnu_segment *s = &p->segs[i];
        if (s->vmaddr < p->virt_base || s->file_size > s->vmsize ||
            !range_ok(s->file_off, s->file_size, len) ||
            !range_ok(s->vmaddr - p->virt_base, s->vmsize, kernel_bytes))
            return "segment source/destination bounds";
        if (s->file_off < hdr + p->nsegs * sizeof(struct xnu_segment))
            return "segment points into header";
        if (p->entry_va >= s->vmaddr &&
            p->entry_va - s->vmaddr < s->file_size)
            entry_in_segment = 1;
        for (uint32_t j = 0; j < i; ++j) {
            const struct xnu_segment *other = &p->segs[j];
            const uint64_t a = s->vmaddr - p->virt_base;
            const uint64_t b = other->vmaddr - p->virt_base;
            if (s->vmsize && other->vmsize &&
                a < b + other->vmsize && b < a + s->vmsize)
                return "overlapping kernel segments";
        }
    }
    if (!entry_in_segment)
        return "entry not inside loaded bytes";
    out->entry_pa = p->phys_base + (p->entry_va - p->virt_base);
    out->adt_va = p->virt_base + kernel_bytes;
    out->boot_args_pa = ba;
    out->top_of_kernel_data = top;
    return 0;
}

static void copy_bytes(uint64_t dst_pa, const uint8_t *src, uint64_t count)
{
    volatile uint8_t *dst = (volatile uint8_t *)(uintptr_t)dst_pa;
    for (uint64_t i = 0; i < count; ++i)
        dst[i] = src[i];
}

static void zero_bytes(uint64_t dst_pa, uint64_t count)
{
    volatile uint8_t *dst = (volatile uint8_t *)(uintptr_t)dst_pa;
    for (uint64_t i = 0; i < count; ++i)
        dst[i] = 0;
}

void xnu_install(const struct xnu_payload *p, const struct xnu_plan *plan)
{
    const uint8_t *const blob = (const uint8_t *)p;
    for (uint32_t i = 0; i < p->nsegs; ++i) {
        const struct xnu_segment *s = &p->segs[i];
        const uint64_t dst = p->phys_base + (s->vmaddr - p->virt_base);
        copy_bytes(dst, blob + s->file_off, s->file_size);
        zero_bytes(dst + s->file_size, s->vmsize - s->file_size);
    }
    copy_bytes(plan->adt_pa, blob + p->adt_off, p->adt_size);
    zero_bytes(plan->boot_args_pa, A733_XNU_PAGE);

    volatile struct xnu_boot_args *ba =
        (volatile struct xnu_boot_args *)(uintptr_t)plan->boot_args_pa;
    ba->Revision = 2;
    ba->Version = 2;
    ba->virtBase = p->virt_base;
    ba->physBase = p->phys_base;
    ba->memSize = p->mem_size;
    ba->memSizeActual = p->mem_size;
    ba->topOfKernelData = plan->top_of_kernel_data;
    ba->Video.v_baseAddr = A733_FB_BASE;
    ba->Video.v_display = 1;
    ba->Video.v_rowBytes = A733_FB_WIDTH * 4;
    ba->Video.v_width = A733_FB_WIDTH;
    ba->Video.v_height = A733_FB_HEIGHT;
    ba->Video.v_depth = 32;
    ba->deviceTreeP = plan->adt_va;
    ba->deviceTreeLength = (uint32_t)p->adt_size;
    for (uint32_t i = 0; i < A733_XNU_CMDLINE; ++i)
        ba->CommandLine[i] = p->cmdline[i];
    ba->CommandLine[A733_XNU_CMDLINE - 1] = 0;
#ifndef A733_HOST_TEST
    __asm__ volatile("dsb sy; ic iallu; dsb sy; isb" ::: "memory");
#endif
}
