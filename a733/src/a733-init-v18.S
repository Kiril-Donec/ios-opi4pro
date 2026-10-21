/*
 * A733 v18: extend the physically verified v17 single-core userspace PID 1.
 * Execute a real HFS+ file read into the user stack, compare its Mach-O magic,
 * close the descriptor, then verify that missing-file open returns ENOENT.
 * Only then open /dev/console, report a clear PASS/FAIL, and keep running.
 *
 * Static Mach-O is emitted by tools/mkinit.py: no relocations or writable data.
 * All addresses use adr, buffers use the 16-byte-aligned stack.
 * Darwin ARM64 BSD syscalls: x16=number, svc #0x80, carry set on error.
 */
#define SYS_read       3
#define SYS_write      4
#define SYS_open       5
#define SYS_close      6
#define SYS_getpid    20
#define SYS_select    93
#define O_RDONLY       0
#define O_RDWR         2
#define ENOENT         2

    .text
    .globl _start
    .p2align 2
_start:
    mov x9, sp
    and x9, x9, #~15
    mov sp, x9

    /* Status x21: 0=pass, 1=self open, 2=read, 3=magic,
       4=close, 5=missing path unexpectedly opened, 6=wrong errno. */
    mov x21, #0

    /* Keep v17's first tested syscall order unchanged. */
    mov x16, #SYS_getpid
    svc #0x80

    adr x0, self_path
    mov x1, #O_RDONLY
    mov x2, #0
    mov x16, #SYS_open
    svc #0x80
    b.cs self_open_failed
    mov x20, x0

    /* Exercise copyout into valid user memory, checking Mach-O signature. */
    sub sp, sp, #16
    mov x0, x20
    mov x1, sp
    mov x2, #4
    mov x16, #SYS_read
    svc #0x80
    b.cs read_failed
    cmp x0, #4
    b.ne read_failed
    ldr w9, [sp]
    movz w10, #0xfacf
    movk w10, #0xfeed, lsl #16
    cmp w9, w10
    b.ne magic_failed
    add sp, sp, #16
    b close_self

read_failed:
    mov x21, #2
    add sp, sp, #16
    b close_self
magic_failed:
    mov x21, #3
    add sp, sp, #16

close_self:
    mov x0, x20
    mov x16, #SYS_close
    svc #0x80
    b.cc missing_probe
    cbnz x21, missing_probe
    mov x21, #4
    b missing_probe

self_open_failed:
    mov x21, #1

missing_probe:
    /* Negative-path VFS test: open should fail with ENOENT (2). */
    adr x0, missing_path
    mov x1, #O_RDONLY
    mov x2, #0
    mov x16, #SYS_open
    svc #0x80
    b.cs missing_error
    /* Unexpected success: close the extra descriptor, preserve test status. */
    mov x20, x0
    mov x0, x20
    mov x16, #SYS_close
    svc #0x80
    cbnz x21, open_console
    mov x21, #5
    b open_console
missing_error:
    cmp x0, #ENOENT
    b.eq open_console
    cbnz x21, open_console
    mov x21, #6

open_console:
    adr x0, console_path
    mov x1, #O_RDWR
    mov x2, #0
    mov x16, #SYS_open
    svc #0x80
    b.cs hang                  /* No output path. Kernel syscall log remains. */
    mov x19, x0

    adr x1, hello
    adr x2, hello_tail
    sub x2, x2, x1
    bl write_console

    mov x16, #SYS_getpid
    svc #0x80
    add w0, w0, #'0'
    sub sp, sp, #16
    strb w0, [sp]
    mov x1, sp
    mov x2, #1
    bl write_console
    add sp, sp, #16
    adr x1, hello_tail
    adr x2, v18_pass
    sub x2, x2, x1
    bl write_console

    cbnz x21, report_failure
    adr x1, v18_pass
    adr x2, v18_pass_end
    b report
report_failure:
    cmp x21, #1
    b.eq report_self_open
    cmp x21, #2
    b.eq report_read
    cmp x21, #3
    b.eq report_magic
    cmp x21, #4
    b.eq report_close
    cmp x21, #5
    b.eq report_missing_open
    adr x1, v18_missing_errno
    adr x2, v18_missing_errno_end
    b report
report_self_open:
    adr x1, v18_self_open
    adr x2, v18_self_open_end
    b report
report_read:
    adr x1, v18_read
    adr x2, v18_read_end
    b report
report_magic:
    adr x1, v18_magic
    adr x2, v18_magic_end
    b report
report_close:
    adr x1, v18_close
    adr x2, v18_close_end
    b report
report_missing_open:
    adr x1, v18_missing_open
    adr x2, v18_missing_open_end
report:
    sub x2, x2, x1
    bl write_console

    /* Preserve proven v17 heartbeat and scheduling behavior. */
tick:
    mov x0, #0
    mov x1, #0
    mov x2, #0
    mov x3, #0
    adr x4, five_sec
    mov x16, #SYS_select
    svc #0x80
    adr x1, alive
    adr x2, alive_end
    sub x2, x2, x1
    bl write_console
    b tick

write_console:
    mov x0, x19
    mov x16, #SYS_write
    svc #0x80
    ret

hang:
    b hang

    .p2align 3
five_sec:
    .quad 5
    .quad 0
self_path:
    .asciz "/sbin/launchd"
missing_path:
    .asciz "/a733-v18-definitely-missing"
console_path:
    .asciz "/dev/console"
hello:
    .ascii "\n*** A733 userspace: init running as PID "
hello_tail:
    .ascii " ***\n"
v18_pass:
    .ascii "A733 V18 PASS: read(4B Mach-O) + close + ENOENT\n"
v18_pass_end:
v18_self_open:
    .ascii "A733 V18 FAIL: self open\n"
v18_self_open_end:
v18_read:
    .ascii "A733 V18 FAIL: read(4B)\n"
v18_read_end:
v18_magic:
    .ascii "A733 V18 FAIL: wrong Mach-O magic\n"
v18_magic_end:
v18_close:
    .ascii "A733 V18 FAIL: close\n"
v18_close_end:
v18_missing_open:
    .ascii "A733 V18 FAIL: missing file opened\n"
v18_missing_open_end:
v18_missing_errno:
    .ascii "A733 V18 FAIL: expected ENOENT\n"
v18_missing_errno_end:
alive:
    .ascii "A733 init: still alive\n"
alive_end:
