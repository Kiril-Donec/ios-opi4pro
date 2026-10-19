    .section .text.boot, "ax"
    .globl _start
_start:
    // ARM64 Linux Image header, inside the legacy uImage wrapper.
    // Vendor bootm/BL31 uses this signature to identify a 64-bit payload.
    b stage0_entry
    .long 0
    .quad 0                         // text_offset: fixed 2-MiB-aligned load
    .quad __image_size              // includes BSS and reserved stack
    .quad 0                         // little endian, page size unspecified
    .quad 0
    .quad 0
    .quad 0
    .long 0x644d5241                 // ARM\x64
    .long 0
stage0_entry:
    msr daifset, #0xf
    msr spsel, #1                   // use the current EL's own stack
    mov x19, x0
    adr x1, __stack_top
    mov sp, x1
    adr x1, a733_vectors
    msr vbar_el1, x1
    isb
    adr x1, __bss_start
    adr x2, __bss_end
1:
    cmp x1, x2
    b.hs 2f
    str xzr, [x1], #8
    b 1b
2:
    mov x0, x19
    mrs x1, CurrentEL
    bl stage0_main
3:
    wfe
    b 3b

// PSCI CPU_ON target (context_id/x0 is the FDT physical address).
// Unlike _start, this MUST NOT clear .bss: the A55 and A76 share it.
    .balign 16
    .globl a76_secondary_entry
a76_secondary_entry:
    msr daifset, #0xf
    msr spsel, #1
    adr x1, __secondary_stack_top
    mov sp, x1
    adr x1, a733_vectors
    msr vbar_el1, x1
    isb
    bl stage0_a76_entry
4:
    wfe
    b 4b

// EL1 vectors are only for diagnostics before XNU installs its own table.
// All early synchronous faults show ESR/ELR/FAR on the physical HDMI screen.
.macro a733_vector number
    .balign 128
    mov x0, #\number
    b a733_fault_common
.endm

    .balign 2048
a733_vectors:
    a733_vector 0
    a733_vector 1
    a733_vector 2
    a733_vector 3
    a733_vector 4
    a733_vector 5
    a733_vector 6
    a733_vector 7
    a733_vector 8
    a733_vector 9
    a733_vector 10
    a733_vector 11
    a733_vector 12
    a733_vector 13
    a733_vector 14
    a733_vector 15

a733_fault_common:
    msr daifset, #0xf
    mrs x1, esr_el1
    mrs x2, elr_el1
    mrs x3, far_el1
    bl stage0_exception
5:
    wfe
    b 5b
