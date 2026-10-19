#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "xnu_payload.h"

static unsigned failures;
#define CHECK(pred) do { if (!(pred)) { \
    fprintf(stderr, "line %d: %s\n", __LINE__, #pred); ++failures; \
} } while (0)

static uint8_t blob[8192] __attribute__((aligned(8)));

static struct xnu_payload *make_valid(void)
{
    memset(blob, 0, sizeof(blob));
    struct xnu_payload *p = (struct xnu_payload *)blob;
    memcpy(p->magic, "A733XNU1", 8);
    p->version = 1;
    p->nsegs = 1;
    p->virt_base = 0xfffffff000000000ULL;
    p->phys_base = A733_XNU_RAM_BASE;
    p->mem_size = A733_XNU_RAM_SIZE;
    p->entry_va = p->virt_base + 0x2000100;
    p->kernel_end = p->virt_base + 0x2020000;
    p->adt_off = 0x1000;
    p->adt_size = 256;
    blob[p->adt_off] = 1;   /* root property count */
    blob[p->adt_off + 4] = 1; /* root child count */
    p->segs[0] = (struct xnu_segment){
        .vmaddr = p->virt_base + 0x2000000,
        .vmsize = 0x4000,
        .file_off = 0x300,
        .file_size = 0x400,
    };
    return p;
}

int main(void)
{
    struct xnu_plan plan;
    struct xnu_payload *p = make_valid();
    CHECK(xnu_validate(p, sizeof(blob), A733_XNU_PAYLOAD_PA, &plan) == NULL);
    CHECK(plan.entry_pa == A733_XNU_RAM_BASE + 0x2000100);
    CHECK(plan.adt_pa == A733_XNU_RAM_BASE + 0x2020000);
    CHECK(plan.adt_va == p->kernel_end);
    CHECK(plan.boot_args_pa % 0x4000 == 0);
    CHECK(plan.top_of_kernel_data < A733_XNU_RAM_BASE + A733_XNU_RAM_SIZE);

    p = make_valid(); memcpy(p->magic, "SWEETXNU", 8);
    CHECK(xnu_validate(p, sizeof(blob), A733_XNU_PAYLOAD_PA, &plan));
    p = make_valid(); p->phys_base = 0x80000000;
    CHECK(xnu_validate(p, sizeof(blob), A733_XNU_PAYLOAD_PA, &plan));
    p = make_valid(); p->segs[0].file_off = sizeof(blob) - 8;
    CHECK(xnu_validate(p, sizeof(blob), A733_XNU_PAYLOAD_PA, &plan));
    p = make_valid(); p->segs[0].vmsize = 8;
    CHECK(xnu_validate(p, sizeof(blob), A733_XNU_PAYLOAD_PA, &plan));
    p = make_valid(); p->entry_va = p->virt_base + 0x3000000;
    CHECK(xnu_validate(p, sizeof(blob), A733_XNU_PAYLOAD_PA, &plan));
    p = make_valid(); p->nsegs = 999;
    CHECK(xnu_validate(p, sizeof(blob), A733_XNU_PAYLOAD_PA, &plan));
    p = make_valid(); p->adt_size = sizeof(blob);
    CHECK(xnu_validate(p, sizeof(blob), A733_XNU_PAYLOAD_PA, &plan));
    p = make_valid(); blob[p->adt_off] = 0;
    CHECK(xnu_validate(p, sizeof(blob), A733_XNU_PAYLOAD_PA, &plan));
    p = make_valid(); p->kernel_end = p->virt_base + A733_XNU_RAM_SIZE;
    CHECK(xnu_validate(p, sizeof(blob), A733_XNU_PAYLOAD_PA, &plan));
    p = make_valid();
    CHECK(xnu_validate(p, sizeof(blob), A733_XNU_PAYLOAD_PA + 8, &plan));
    p = make_valid(); p->segs[0].file_off = 0;
    CHECK(xnu_validate(p, sizeof(blob), A733_XNU_PAYLOAD_PA, &plan));
    p = make_valid(); p->nsegs = 2;
    p->segs[1] = p->segs[0];
    CHECK(xnu_validate(p, sizeof(blob), A733_XNU_PAYLOAD_PA, &plan));

    if (failures)
        return 1;
    puts("XNU v1 payload layout, destination and bounds: PASS");
    return 0;
}
