/*
 * Host test for the keychain key wrapping of the built-in AppleKeyStore
 * (a733/xnu-a733-keychain.patch, iokit/Kernel/arm/SweetKeyStore.cpp).
 * test_keychain_patch.py cuts sweet_aks_struct_out() and the wrap block out
 * of the patched file into aks_block.inc; the IOKit types are stubbed here.
 * Checked: securityd's shapes from board test #14 (in 2/32 out 1/40), the
 * round trip, the class scalar, and that foreign / damaged blobs fail.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef int IOReturn;
#define kIOReturnSuccess        0
#define kIOReturnBadArgument    ((IOReturn)0xe00002c2)
#define kIOReturnNoSpace        ((IOReturn)0xe00002c4)

struct IOMemoryDescriptor {
	uint8_t *mem;
	uint32_t len;
	uint64_t getLength() const { return len; }
	void readBytes(uint64_t off, void *buf, uint64_t n) { memcpy(buf, mem + off, n); }
	void writeBytes(uint64_t off, const void *buf, uint64_t n) { memcpy(mem + off, buf, n); }
};

struct IOExternalMethodArguments {
	const uint64_t *scalarInput;
	uint32_t scalarInputCount;
	const void *structureInput;
	uint32_t structureInputSize;
	IOMemoryDescriptor *structureInputDescriptor;
	uint64_t *scalarOutput;
	uint32_t scalarOutputCount;
	void *structureOutput;
	uint32_t structureOutputSize;
	IOMemoryDescriptor *structureOutputDescriptor;
	uint32_t structureOutputDescriptorSize;
};

#include "aks_block.inc"

static int failures;
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static IOReturn
call(IOReturn (*fn)(IOExternalMethodArguments *), uint64_t bag, uint64_t cls, const uint8_t *in, uint32_t inlen,
    uint8_t *out, uint32_t *outlen, uint64_t *scalar_out, uint32_t *scalar_count, bool descriptors = false)
{
	uint64_t sin[2] = { bag, cls };
	IOMemoryDescriptor din = { const_cast<uint8_t *>(in), inlen }, dout = { out, *outlen };
	IOExternalMethodArguments a = {};
	a.scalarInput = sin;
	a.scalarInputCount = 2;
	a.scalarOutput = scalar_out;
	a.scalarOutputCount = *scalar_count;
	if (descriptors) {
		a.structureInputDescriptor = &din;
		a.structureOutputDescriptor = &dout;
	} else {
		a.structureInput = in;
		a.structureInputSize = inlen;
		a.structureOutput = out;
		a.structureOutputSize = *outlen;
	}
	IOReturn r = fn(&a);
	*outlen = descriptors ? a.structureOutputDescriptorSize : a.structureOutputSize;
	*scalar_count = a.scalarOutputCount;
	return r;
}

int
main(void)
{
	uint8_t key[32], wrapped[40], back[32];
	for (int i = 0; i < 32; i++) {
		key[i] = (uint8_t)(i * 37 + 11);
	}
	for (int d = 0; d < 2; d++) {
		uint64_t cls = 0;
		uint32_t wl = sizeof(wrapped), sc = 1, bl = sizeof(back), sc2 = 0;
		/* securityd: bag 0, class 6 (kSecAttrAccessibleAfterFirstUnlock-ish), 32-byte key, 40 out */
		CHECK(call(sweet_aks_wrap, 0, 6, key, 32, wrapped, &wl, &cls, &sc, d) == kIOReturnSuccess);
		CHECK(wl == 40 && sc == 1 && cls == 6);
		CHECK(memcmp(wrapped + 8, key, 32) != 0);       /* not stored in the clear */
		CHECK(call(sweet_aks_unwrap, 0, 6, wrapped, 40, back, &bl, &cls, &sc2, d) == kIOReturnSuccess);
		CHECK(bl == 32 && memcmp(back, key, 32) == 0);
	}
	/* Same input, same output: stable across boots (no per-boot secret). */
	uint8_t w2[40];
	uint64_t cls = 0;
	uint32_t l1 = 40, l2 = 40, sc = 1;
	call(sweet_aks_wrap, 0, 6, key, 32, wrapped, &l1, &cls, &sc);
	sc = 1;
	call(sweet_aks_wrap, 0, 6, key, 32, w2, &l2, &cls, &sc);
	CHECK(memcmp(wrapped, w2, 40) == 0);
	/* Too little room (securityd's n + 8 is exactly enough). */
	uint32_t small = 39;
	sc = 1;
	CHECK(call(sweet_aks_wrap, 0, 6, key, 32, w2, &small, &cls, &sc) == kIOReturnNoSpace);
	/* Damaged / foreign blobs are refused, never "unwrapped" to garbage. */
	for (int i = 0; i < 8; i++) {
		uint8_t bad[40];
		memcpy(bad, wrapped, 40);
		bad[i] ^= 0x40;
		uint32_t bl = 32, sc2 = 0;
		CHECK(call(sweet_aks_unwrap, 0, 6, bad, 40, back, &bl, &cls, &sc2) == kIOReturnBadArgument);
	}
	uint32_t bl = 32, sc2 = 0;
	CHECK(call(sweet_aks_unwrap, 0, 6, wrapped, 39, back, &bl, &cls, &sc2) == kIOReturnBadArgument);
	uint8_t rfc3394[40] = { 0xa6, 0xa6, 0xa6, 0xa6, 0xa6, 0xa6, 0xa6, 0xa6 };
	CHECK(call(sweet_aks_unwrap, 0, 6, rfc3394, 40, back, &bl, &cls, &sc2) == kIOReturnBadArgument);
	/* Empty and oversized keys. */
	uint8_t big[80] = {};
	uint32_t ol = 100;
	sc = 1;
	CHECK(call(sweet_aks_wrap, 0, 6, key, 0, w2, &ol, &cls, &sc) == kIOReturnBadArgument);
	CHECK(call(sweet_aks_wrap, 0, 6, big, 80, w2, &ol, &cls, &sc) == kIOReturnBadArgument);
	/* 16-byte keys work too (n + 8 = 24). */
	uint8_t w16[24], k16[16];
	uint32_t l16 = 24, b16 = 16;
	sc = 1;
	CHECK(call(sweet_aks_wrap, 0, 3, key, 16, w16, &l16, &cls, &sc) == kIOReturnSuccess && l16 == 24);
	CHECK(call(sweet_aks_unwrap, 0, 3, w16, 24, k16, &b16, &cls, &sc2) == kIOReturnSuccess &&
	    b16 == 16 && memcmp(k16, key, 16) == 0);
	if (failures) {
		printf("FAIL (%d)\n", failures);
		return 1;
	}
	printf("A733 AKS key wrap: PASS\n");
	return 0;
}
