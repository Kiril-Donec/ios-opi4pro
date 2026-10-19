#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "fdt_safe.h"

/* Pipe a raw DTB into this host test; it does not access hardware or disks. */
static uint8_t blob[2 * 1024 * 1024];

int main(int argc, char **argv)
{
    if (argc != 2 || (strcmp(argv[1], "static") && strcmp(argv[1], "live"))) {
        fprintf(stderr, "usage: test_fdt_region static|live < file.dtb\n");
        return 2;
    }
    size_t n = fread(blob, 1, sizeof(blob), stdin);
    if (n < 40 || ferror(stdin)) {
        fprintf(stderr, "could not read DTB\n");
        return 2;
    }
    int high = fdt_region_usable(blob, 0x100000000ULL, 0x40000000ULL);
    int source = fdt_region_usable(blob, 0x52000000ULL, 128ULL * 1024 * 1024);
    int bad = fdt_region_usable(blob, 0x48000000ULL, 0x1000000ULL);
    if (strcmp(argv[1], "static") == 0) {
        if (high || !source || bad) {
            fprintf(stderr, "unsafe static DTB unexpectedly passed: high=%d source=%d bl31=%d\n",
                    high, source, bad);
            return 1;
        }
        puts("static vendor DTB: high RAM not advertised, correctly rejected: PASS");
    } else {
        if (!high || !source || bad) {
            fprintf(stderr, "live DTB mismatch: high=%d source=%d bl31=%d\n",
                    high, source, bad);
            return 1;
        }
        puts("live Linux FDT: A733 RAM confirmed, BL31 reserved: PASS");
    }
    return 0;
}
