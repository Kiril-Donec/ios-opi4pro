ENTRY(_start)
SECTIONS
{
    . = 0x41000000;
    .text : { KEEP(*(.text.boot)) *(.text .text.*) }
    .rodata : { *(.rodata .rodata.*) }
    .data : { *(.data .data.*) }
    . = ALIGN(16);
    __bss_start = .;
    .bss (NOLOAD) : { *(.bss .bss.*) *(COMMON) }
    . = ALIGN(16);
    __bss_end = .;
    . = . + 0x4000;
    __stack_top = .;
    . = ALIGN(16);
    . = . + 0x4000;
    __secondary_stack_top = .;
    /* The Image header must reserve both PSCI CPU stacks, not just the
     * boot-CPU stack: the A76 may use the second one before XNU starts. */
    __image_size = __secondary_stack_top - 0x41000000;
    /DISCARD/ : { *(.comment) *(.note.*) *(.eh_frame*) }
}
