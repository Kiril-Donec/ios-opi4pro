/*
 * Extra XNU declarations for the host -fsyntax-only check of
 * bsd/dev/a733_power.c (a733/xnu-a733-cores-fb-power.patch), after
 * sdmmc_kernel_stubs.h and usbtouch_kernel_stubs.h. Signatures from
 * xnu-8796.141.3 (osfmk/kern/clock.h, osfmk/arm/cpu_number.h).
 */
void absolutetime_to_nanoseconds(uint64_t abstime, uint64_t *result);
int cpu_number(void);
/* 9999r: cpufreq PLL retune with interrupts off, clean shutdown (osfmk/arm, bsd/sys/reboot.h). */
typedef int boolean_t;
#define FALSE 0
boolean_t ml_set_interrupts_enabled(boolean_t enable);
#define RB_HALT 0x08
