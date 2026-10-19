#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "fdt_safe.h"

#define A733_START 0x52000000ULL
#define A733_END 0x53112233ULL

static uint8_t dtb[512];
static unsigned off = 64;
static unsigned tests_failed;

static void put32(unsigned at, uint32_t value)
{
    dtb[at + 0] = (uint8_t)(value >> 24);
    dtb[at + 1] = (uint8_t)(value >> 16);
    dtb[at + 2] = (uint8_t)(value >> 8);
    dtb[at + 3] = (uint8_t)value;
}

static void tok(uint32_t value)
{
    put32(off, value);
    off += 4;
}

static void node(const char *name)
{
    tok(1);
    unsigned size = (unsigned)strlen(name) + 1;
    memcpy(dtb + off, name, size);
    off += (size + 3) & ~3U;
}

static void prop(uint32_t nameoff, uint64_t value)
{
    tok(3);
    tok(8);
    tok(nameoff);
    put32(off, (uint32_t)(value >> 32));
    put32(off + 4, (uint32_t)value);
    off += 8;
}

static void build(void)
{
    memset(dtb, 0, sizeof(dtb));
    off = 64;
    const char strings[] = "linux,initrd-start\0linux,initrd-end\0";
    memcpy(dtb + 256, strings, sizeof(strings));
    put32(0, 0xd00dfeed);
    put32(4, sizeof(dtb));
    put32(8, 64);
    put32(12, 256);
    put32(32, sizeof(strings));
    node("");
    node("chosen");
    prop(0, A733_START);
    prop(19, A733_END);
    tok(2); tok(2); tok(9);
    put32(36, off - 64);
}

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "line %u: %s\n", __LINE__, #expr); ++tests_failed; \
} } while (0)

int main(void)
{
    uint64_t value = 0;
    build();
    CHECK(fdt_chosen_u64(dtb, "linux,initrd-start", &value));
    CHECK(value == A733_START);
    CHECK(fdt_chosen_u64(dtb, "linux,initrd-end", &value));
    CHECK(value == A733_END);
    CHECK(!fdt_chosen_u64(dtb, "unknown", &value));
    put32(4, 0x90000000);
    CHECK(!fdt_chosen_u64(dtb, "linux,initrd-start", &value));
    build(); put32(36, 4);
    CHECK(!fdt_chosen_u64(dtb, "linux,initrd-start", &value));
    build(); put32(12, 490);
    CHECK(!fdt_chosen_u64(dtb, "linux,initrd-start", &value));
    build(); put32(32, 1);
    CHECK(!fdt_chosen_u64(dtb, "linux,initrd-start", &value));
    if (tests_failed)
        return 1;
    puts("bounded FDT /chosen 64-bit parser: PASS");
    return 0;
}
