/*
 * Extra XNU declarations for the host -fsyntax-only check of
 * bsd/dev/a733_power.c (a733/xnu-a733-cores-fb-power.patch), after
 * sdmmc_kernel_stubs.h and usbtouch_kernel_stubs.h. Signatures from
 * xnu-8796.141.3 (osfmk/kern/clock.h, osfmk/arm/cpu_number.h).
 */
void absolutetime_to_nanoseconds(uint64_t abstime, uint64_t *result);
int cpu_number(void);
