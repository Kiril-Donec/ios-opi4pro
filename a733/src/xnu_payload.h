#ifndef A733_XNU_PAYLOAD_H
#define A733_XNU_PAYLOAD_H

#include <stdint.h>
#include <stddef.h>

/* SWEETXNU v1 is produced by ios-topaz/tools/mkpayload.py. */
#define A733_XNU_RAM_BASE 0x100000000ULL
#define A733_XNU_RAM_SIZE 0x40000000ULL
#define A733_XNU_PAYLOAD_PA 0x52000000ULL
#define A733_XNU_PAYLOAD_LIMIT (128ULL * 1024 * 1024)
#define A733_XNU_MAX_SEGS 32U
#define A733_XNU_PAGE 0x4000ULL
#define A733_XNU_CMDLINE 608U

struct xnu_segment {
    uint64_t vmaddr, vmsize, file_off, file_size;
};

struct xnu_payload {
    char magic[8];
    uint32_t version, nsegs;
    uint64_t virt_base, entry_va, adt_off, adt_size, kernel_end;
    uint64_t phys_base, mem_size;
    char cmdline[A733_XNU_CMDLINE];
    struct xnu_segment segs[];
};

struct xnu_video {
    uint64_t v_baseAddr, v_display, v_rowBytes, v_width, v_height, v_depth;
};

/* Apple pexpert/pexpert/arm64/boot.h, revision 2. */
struct xnu_boot_args {
    uint16_t Revision, Version;
    uint64_t virtBase, physBase, memSize, topOfKernelData;
    struct xnu_video Video;
    uint32_t machineType;
    uint64_t deviceTreeP;
    uint32_t deviceTreeLength;
    char CommandLine[A733_XNU_CMDLINE];
    uint64_t bootFlags, memSizeActual;
};

struct xnu_plan {
    uint64_t entry_pa;
    uint64_t adt_pa;
    uint64_t adt_va;
    uint64_t boot_args_pa;
    uint64_t top_of_kernel_data;
};

/* Checks every source and destination range before any memory is written. */
const char *xnu_validate(const struct xnu_payload *p, uint64_t payload_len,
                         uint64_t payload_pa, struct xnu_plan *plan);

/* Called only with MMU and D-cache disabled and after successful validation. */
void xnu_install(const struct xnu_payload *p, const struct xnu_plan *plan);

#endif
