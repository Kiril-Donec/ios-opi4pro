/*
 * Minimal XNU kernel declarations for a host -fsyntax-only check of
 * bsd/dev/a733_sdmmc.c (a733/xnu-a733-sdmmc.patch). Signatures are copied
 * from xnu-8796.141.3 (bsd/sys/conf.h, bsd/sys/buf.h, osfmk/kern/clock.h,
 * pexpert/pexpert/device_tree.h). This catches typos and type errors only;
 * the real compile happens in the macOS XNU workflow.
 */
#include <stdbool.h>
#include <stddef.h>
#include <limits.h>

/* XNU (bsd/arm/_types.h): 64-bit integers are long long, so printf uses %llu. */
typedef signed char int8_t;
typedef unsigned char uint8_t;
typedef short int16_t;
typedef unsigned short uint16_t;
typedef int int32_t;
typedef unsigned int uint32_t;
typedef long long int64_t;
typedef unsigned long long uint64_t;
typedef unsigned long uintptr_t;
void *memcpy(void *dst, const void *src, size_t n);
void *memset(void *dst, int c, size_t n);
size_t strlen(const char *s);
int snprintf(char *buf, size_t n, const char *fmt, ...) __attribute__((format(printf, 3, 4)));
#define UINT64_MAX 0xffffffffffffffffull
int memcmp(const void *a, const void *b, size_t n);

typedef uintptr_t vm_offset_t;
typedef uintptr_t vm_size_t;
typedef int32_t dev_t;
typedef char *caddr_t;
typedef unsigned long u_long;
typedef unsigned int u_int;
typedef struct buf *buf_t;
struct buf;
struct proc;
struct uio;
struct tty;

#define EPERM 1
#define EAGAIN 35
#define ENOTSUP 45
#define ENOENT 2
#define EIO 5
#define ENXIO 6
#define ENOMEM 12
#define ENODEV 19
#define EINVAL 22
#define ENOTTY 25
#define EFBIG 27
#define EROFS 30
#define ETIMEDOUT 60
#define EFTYPE 79

#define MIN(a, b) (((a) < (b)) ? (a) : (b))
#define DEV_BSIZE 512
#define FWRITE 0x0002
#define B_READ 0x00000001
#define B_WRITE 0x00000000
#define D_DISK 2
#define NSEC_PER_MSEC 1000000ull
#define DKIOCGETBLOCKSIZE 1
#define DKIOCSETBLOCKSIZE 2
#define DKIOCGETPHYSICALBLOCKSIZE 3
#define DKIOCGETBLOCKCOUNT 4
#define DKIOCISWRITABLE 5
#define DKIOCSYNCHRONIZE 6
#define DKIOCSYNCHRONIZECACHE 7
#define DKIOCGETMAXBLOCKCOUNTREAD 8
#define DKIOCGETMAXBLOCKCOUNTWRITE 9
#define DKIOCGETMAXSEGMENTCOUNTREAD 10
#define DKIOCGETMAXSEGMENTCOUNTWRITE 11

typedef int open_close_fcn_t(dev_t dev, int flags, int devtype, struct proc *p);
typedef void strategy_fcn_t(struct buf *bp);
typedef int ioctl_fcn_t(dev_t dev, u_long cmd, caddr_t data, int fflag, struct proc *p);
typedef int dump_fcn_t(void);
typedef int psize_fcn_t(dev_t dev);
typedef int read_write_fcn_t(dev_t dev, struct uio *uio, int ioflag);
typedef int stop_fcn_t(struct tty *tp, int rw);
typedef int reset_fcn_t(int uban);
typedef int select_fcn_t(dev_t dev, int which, void *wql, struct proc *p);
typedef int mmap_fcn_t(void);
typedef int rsvd_fcn_t(void);
typedef int empty_fcn_t(void);
extern int enodev(void);
extern void enodev_strat(void);
#define eno_strat ((strategy_fcn_t *)(empty_fcn_t*)&enodev_strat)
#define eno_dump ((dump_fcn_t *)(empty_fcn_t*)&enodev)
#define eno_stop ((stop_fcn_t *)(empty_fcn_t*)&enodev)
#define eno_reset ((reset_fcn_t *)(empty_fcn_t*)&enodev)
#define eno_mmap ((mmap_fcn_t *)(empty_fcn_t*)&enodev)
#define eno_select ((select_fcn_t *)(empty_fcn_t*)&enodev)
#define eno_getc ((rsvd_fcn_t *)&enodev)
#define eno_putc ((rsvd_fcn_t *)&enodev)

struct bdevsw {
	open_close_fcn_t *d_open;
	open_close_fcn_t *d_close;
	strategy_fcn_t *d_strategy;
	ioctl_fcn_t *d_ioctl;
	dump_fcn_t *d_dump;
	psize_fcn_t *d_psize;
	int d_type;
};

struct cdevsw {
	open_close_fcn_t *d_open;
	open_close_fcn_t *d_close;
	read_write_fcn_t *d_read;
	read_write_fcn_t *d_write;
	ioctl_fcn_t *d_ioctl;
	stop_fcn_t *d_stop;
	reset_fcn_t *d_reset;
	struct tty **d_ttys;
	select_fcn_t *d_select;
	mmap_fcn_t *d_mmap;
	strategy_fcn_t *d_strategy;
	rsvd_fcn_t *d_reserved_1;
	rsvd_fcn_t *d_reserved_2;
	int d_type;
};

int bdevsw_add(int, const struct bdevsw *);
int cdevsw_add_with_bdev(int index, const struct cdevsw *csw, int bdev);
#define makedev(x, y) ((dev_t)(((x) << 24) | (y)))
#define DEVFS_BLOCK 1
#define DEVFS_CHAR 2
#define UID_ROOT 0
#define GID_OPERATOR 5
void *devfs_make_node(dev_t dev, int chrblk, uint32_t uid, uint32_t gid, int perms,
    const char *fmt, ...) __attribute__((format(printf, 6, 7)));

int64_t buf_blkno(buf_t bp);
uint32_t buf_count(buf_t bp);
void buf_setresid(buf_t bp, uint32_t resid);
int32_t buf_flags(buf_t bp);
int buf_map(buf_t bp, caddr_t *io_addr);
int buf_unmap(buf_t bp);
void buf_seterror(buf_t bp, int error);
void buf_biodone(buf_t bp);
int physio(void (*f_strategy)(buf_t), buf_t bp, dev_t dev, int flags,
    u_int (*f_minphys)(buf_t), struct uio *uio, int blocksize);
u_int minphys(buf_t bp);

int printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
void delay(int usec);
uint64_t mach_absolute_time(void);
void nanoseconds_to_absolutetime(uint64_t nanoseconds, uint64_t *result);
bool PE_parse_boot_argn(const char *arg_string, void *arg_ptr, int max_arg);

typedef const void *DTEntry;
enum { kSuccess = 0, kError = -1 };
int SecureDTLookupEntry(const DTEntry searchPoint, const char *pathName, DTEntry *foundEntry);
int SecureDTGetProperty(const DTEntry entry, const char *propertyName,
    void const **propertyValue, unsigned int *propertySize);

typedef struct { int opaque; } lck_grp_t;
typedef struct { int opaque; } lck_mtx_t;
#define LCK_GRP_DECLARE(var, name) lck_grp_t var __attribute__((unused))
#define LCK_MTX_DECLARE(var, grp) lck_mtx_t var
void lck_mtx_lock(lck_mtx_t *lck);
void lck_mtx_unlock(lck_mtx_t *lck);
#define __unused __attribute__((unused))

/* osfmk/kern/kern_types.h, bsd/sys/proc.h, osfmk/kdp/kdp_callout.h */
typedef int kern_return_t;
#define KERN_SUCCESS 0
typedef struct thread *thread_t;
typedef int wait_result_t;
typedef void (*thread_continue_t)(void *, wait_result_t);
#define PZERO 22
int tsleep(void *chan, int pri, const char *wmesg, int timo);
typedef enum { KDP_EVENT_ENTER, KDP_EVENT_EXIT, KDP_EVENT_PANICLOG } kdp_event_t;
typedef void (*kdp_callout_fn_t)(void *arg, kdp_event_t event);
void kdp_register_callout(kdp_callout_fn_t fn, void *arg);
