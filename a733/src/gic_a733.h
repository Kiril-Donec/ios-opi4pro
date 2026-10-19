#ifndef A733_GIC_H
#define A733_GIC_H

/* Standard GICv3 Group-1NS boot-core setup for A733's virtual timer / SGI1.
 * Returns nonzero if the expected A76 redistributor is not available.
 */
int gic_a733_prepare_a76(void);

#endif
