/*
 * Extra XNU declarations for the host -fsyntax-only check of
 * bsd/dev/a733_usbtouch.c (a733/xnu-a733-usbtouch.patch), included after
 * sdmmc_kernel_stubs.h. Signatures from xnu-8796.141.3 (osfmk/kern/clock.h,
 * osfmk/kern/sched_prim.h, osfmk/kern/kern_types.h).
 */
typedef void *event_t;
#define THREAD_UNINT 0
#define THREAD_CONTINUE_NULL ((thread_continue_t)0)
wait_result_t assert_wait_deadline(event_t event, int interruptible, uint64_t deadline);
wait_result_t thread_block(thread_continue_t continuation);
void clock_interval_to_deadline(uint32_t interval, uint32_t scale_factor, uint64_t *result);
/* arm64 builtin; the host check may run on x86. */
#define __builtin_arm_dsb(x) ((void)(x))
