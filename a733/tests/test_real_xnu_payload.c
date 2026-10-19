/* Host-side end-to-end validation of a packed, real XNU Mach-O kernel.
 * This does not execute the kernel or certify A733 hardware compatibility. */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include "xnu_payload.h"

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "usage: %s SWEETXNU_PAYLOAD\n", argv[0]);
        return 2;
    }
    struct stat st;
    if (stat(argv[1], &st) || st.st_size <= 0 ||
        (uint64_t)st.st_size > A733_XNU_PAYLOAD_LIMIT) {
        fprintf(stderr, "missing/oversize payload\n");
        return 1;
    }
    FILE *file = fopen(argv[1], "rb");
    if (!file) {
        perror("open payload");
        return 1;
    }
    uint8_t *bytes = malloc((size_t)st.st_size);
    if (!bytes || fread(bytes, 1, (size_t)st.st_size, file) != (size_t)st.st_size) {
        fprintf(stderr, "cannot read payload\n");
        fclose(file);
        free(bytes);
        return 1;
    }
    fclose(file);

    struct xnu_plan plan;
    const char *err = xnu_validate((const struct xnu_payload *)bytes,
                                   (uint64_t)st.st_size,
                                   A733_XNU_PAYLOAD_PA, &plan);
    if (err) {
        fprintf(stderr, "Stage0 would reject real kernel: %s\n", err);
        free(bytes);
        return 1;
    }
    printf("Real XNU payload validates against Stage0: PASS\n"
           "  physical entry:   0x%" PRIx64 "\n"
           "  Apple DT PA:      0x%" PRIx64 "\n"
           "  boot_args PA:     0x%" PRIx64 "\n"
           "  topOfKernelData:  0x%" PRIx64 "\n"
           "  kernel segments:  %u\n",
           plan.entry_pa, plan.adt_pa, plan.boot_args_pa,
           plan.top_of_kernel_data, ((const struct xnu_payload *)bytes)->nsegs);
    free(bytes);
    return 0;
}
