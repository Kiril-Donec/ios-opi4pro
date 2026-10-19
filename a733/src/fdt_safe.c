#include "fdt_safe.h"
#include <stddef.h>

#define FDT_BEGIN_NODE 1U
#define FDT_END_NODE 2U
#define FDT_PROP 3U
#define FDT_NOP 4U
#define FDT_END 9U
#define FDT_MAGIC 0xd00dfeedU
#define FDT_MAX_SIZE (2U * 1024U * 1024U)

static uint32_t be32(const uint8_t *p)
{
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 |
           (uint32_t)p[2] << 8 | p[3];
}

static uint64_t be64(const uint8_t *p)
{
    return ((uint64_t)be32(p) << 32) | be32(p + 4);
}

static int name_is(const uint8_t *p, uint32_t len, const char *str)
{
    for (uint32_t i = 0; i < len; ++i) {
        if (p[i] != (uint8_t)str[i])
            return 0;
        if (!p[i])
            return 1;
    }
    return 0;
}

static int nul_terminated(const uint8_t *p, uint32_t len)
{
    for (uint32_t i = 0; i < len; ++i)
        if (!p[i])
            return (int)i + 1;
    return 0;
}

int fdt_chosen_u64(const void *dtb, const char *name, uint64_t *value)
{
    if (!dtb || !name || !value)
        return 0;
    const uint8_t *blob = (const uint8_t *)dtb;
    if (be32(blob) != FDT_MAGIC)
        return 0;
    uint32_t total = be32(blob + 4);
    uint32_t structure = be32(blob + 8), strings = be32(blob + 12);
    uint32_t strings_len = be32(blob + 32), structure_len = be32(blob + 36);
    if (total < 40 || total > FDT_MAX_SIZE ||
        structure > total || structure_len > total - structure ||
        strings > total || strings_len > total - strings)
        return 0;

    const uint8_t *p = blob + structure;
    const uint8_t *end = p + structure_len;
    const uint8_t *strs = blob + strings;
    unsigned depth = 0;
    int chosen = 0;

    while (end - p >= 4) {
        uint32_t token = be32(p);
        p += 4;
        if (token == FDT_BEGIN_NODE) {
            uint32_t remain = (uint32_t)(end - p);
            int size = nul_terminated(p, remain);
            if (!size || depth >= 64)
                return 0;
            ++depth;
            chosen = depth == 2 && name_is(p, (uint32_t)size, "chosen");
            uint32_t step = ((uint32_t)size + 3) & ~3U;
            if (step > remain)
                return 0;
            p += step;
        } else if (token == FDT_END_NODE) {
            if (!depth)
                return 0;
            if (chosen && depth == 2)
                return 0;
            --depth;
            chosen = 0;
        } else if (token == FDT_PROP) {
            if (end - p < 8)
                return 0;
            uint32_t len = be32(p), off = be32(p + 4);
            p += 8;
            if (off >= strings_len || len > (uint32_t)(end - p))
                return 0;
            uint32_t available = strings_len - off;
            if (!nul_terminated(strs + off, available))
                return 0;
            if (chosen && name_is(strs + off, available, name)) {
                if (len == 4)
                    *value = be32(p);
                else if (len == 8)
                    *value = ((uint64_t)be32(p) << 32) | be32(p + 4);
                else
                    return 0;
                return 1;
            }
            uint32_t step = (len + 3) & ~3U;
            if (step > (uint32_t)(end - p))
                return 0;
            p += step;
        } else if (token == FDT_END) {
            return 0;
        } else if (token != FDT_NOP) {
            return 0;
        }
    }
    return 0;
}

static int intersects(uint64_t a, uint64_t asz, uint64_t b, uint64_t bsz)
{
    if (!asz || !bsz || a > UINT64_MAX - asz || b > UINT64_MAX - bsz)
        return 1; /* malformed/overflowing ranges are never safe */
    return a < b + bsz && b < a + asz;
}

static int reg_includes(const uint8_t *p, uint32_t len,
                        uint64_t base, uint64_t bytes)
{
    if (!len || len % 16)
        return 0; /* A733 requires 2 address + 2 size cells */
    for (uint32_t off = 0; off < len; off += 16) {
        uint64_t addr = be64(p + off), size = be64(p + off + 8);
        if (addr <= base && size >= bytes && base - addr <= size - bytes)
            return 1;
    }
    return 0;
}

static int reg_intersects(const uint8_t *p, uint32_t len,
                          uint64_t base, uint64_t bytes)
{
    if (!len || len % 16)
        return 1; /* fail closed */
    for (uint32_t off = 0; off < len; off += 16)
        if (intersects(be64(p + off), be64(p + off + 8), base, bytes))
            return 1;
    return 0;
}

static int starts_with(const uint8_t *p, uint32_t len, const char *prefix)
{
    for (uint32_t i = 0; prefix[i]; ++i) {
        if (i >= len || p[i] != (uint8_t)prefix[i])
            return 0;
    }
    return 1;
}

int fdt_region_usable(const void *dtb, uint64_t base, uint64_t bytes)
{
    if (!dtb || !bytes || base > UINT64_MAX - bytes)
        return 0;
    const uint8_t *blob = (const uint8_t *)dtb;
    if (be32(blob) != FDT_MAGIC)
        return 0;
    const uint32_t total = be32(blob + 4);
    const uint32_t structure = be32(blob + 8), strings = be32(blob + 12);
    const uint32_t rsv = be32(blob + 16);
    const uint32_t strings_len = be32(blob + 32), structure_len = be32(blob + 36);
    if (total < 40 || total > FDT_MAX_SIZE ||
        structure > total || structure_len > total - structure ||
        strings > total || strings_len > total - strings || rsv < 40 || rsv > total)
        return 0;

    /* The FDT reservation map has <base,size> 64-bit big-endian pairs. */
    uint32_t r = rsv;
    int terminated = 0;
    for (unsigned i = 0; i < 256; ++i) {
        if (r > total || total - r < 16)
            return 0;
        const uint64_t at = be64(blob + r), len = be64(blob + r + 8);
        r += 16;
        if (!at && !len) {
            terminated = 1;
            break;
        }
        if (intersects(at, len, base, bytes))
            return 0;
    }
    if (!terminated)
        return 0;

    const uint8_t *p = blob + structure, *end = p + structure_len;
    const uint8_t *strs = blob + strings;
    unsigned depth = 0;
    unsigned addr_cells = 0, size_cells = 0;
    int memory = 0, reserved = 0, reserved_child = 0, covered = 0;
    while (end - p >= 4) {
        uint32_t token = be32(p);
        p += 4;
        if (token == FDT_BEGIN_NODE) {
            uint32_t remain = (uint32_t)(end - p);
            int n = nul_terminated(p, remain);
            if (!n || depth >= 64)
                return 0;
            ++depth;
            if (depth == 2) {
                memory = name_is(p, (uint32_t)n, "memory") ||
                         starts_with(p, (uint32_t)n, "memory@");
                reserved = name_is(p, (uint32_t)n, "reserved-memory");
            } else if (depth == 3 && reserved) {
                reserved_child = 1;
            }
            uint32_t step = ((uint32_t)n + 3) & ~3U;
            if (step > remain)
                return 0;
            p += step;
        } else if (token == FDT_END_NODE) {
            if (!depth)
                return 0;
            if (depth == 3)
                reserved_child = 0;
            if (depth == 2)
                memory = reserved = 0;
            --depth;
        } else if (token == FDT_PROP) {
            if (end - p < 8)
                return 0;
            const uint32_t len = be32(p), off = be32(p + 4);
            p += 8;
            if (off >= strings_len || len > (uint32_t)(end - p))
                return 0;
            uint32_t available = strings_len - off;
            if (!nul_terminated(strs + off, available))
                return 0;
            if (depth == 1 && len == 4 &&
                name_is(strs + off, available, "#address-cells"))
                addr_cells = be32(p);
            if (depth == 1 && len == 4 &&
                name_is(strs + off, available, "#size-cells"))
                size_cells = be32(p);
            if (name_is(strs + off, available, "reg")) {
                if (depth == 2 && memory) {
                    if (addr_cells != 2 || size_cells != 2)
                        return 0;
                    covered |= reg_includes(p, len, base, bytes);
                }
                if (depth == 3 && reserved_child &&
                    reg_intersects(p, len, base, bytes))
                    return 0;
            }
            const uint32_t step = (len + 3) & ~3U;
            if (step > (uint32_t)(end - p))
                return 0;
            p += step;
        } else if (token == FDT_END) {
            return depth == 0 && covered;
        } else if (token != FDT_NOP) {
            return 0;
        }
    }
    return 0;
}
