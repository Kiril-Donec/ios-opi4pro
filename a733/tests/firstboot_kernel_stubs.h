/*
 * XNU declarations for the host -fsyntax-only check of
 * bsd/dev/a733_firstboot.c (a733/xnu-a733-cpufreq-setup.patch), after
 * sdmmc_kernel_stubs.h. Signatures from xnu-8796.141.3 bsd/sys/vnode.h,
 * vnode_internal.h, namei.h, fcntl.h, uio.h. Type and syntax check only.
 */
typedef unsigned int uid_t;
typedef unsigned int gid_t;
typedef unsigned short mode_t;
typedef long long off_t;
typedef struct vnode *vnode_t;
typedef struct vfs_context *vfs_context_t;
typedef struct ucred *kauth_cred_t;
typedef struct proc *proc_t;
typedef unsigned long long user_addr_t;
typedef int errno_t;
#define NULLVP ((vnode_t)0)
#define CAST_USER_ADDR_T(a) ((user_addr_t)(uintptr_t)(a))

enum uio_rw { UIO_READ, UIO_WRITE };
enum uio_seg { UIO_USERSPACE, UIO_SYSSPACE };
enum vtype { VNON, VREG, VDIR };
#define FREAD 0x0001
#define O_NOFOLLOW 0x0100
#define O_CREAT 0x0200
#define O_TRUNC 0x0400
#define IO_UNIT 0x0001
#define IO_NODELOCKED 0x0008
#define VNODE_LOOKUP_NOFOLLOW 0x01

struct vnode_attr {
	unsigned long long va_supported, va_active;
	enum vtype va_type;
	mode_t va_mode;
	uid_t va_uid;
	gid_t va_gid;
};
#define VATTR_INIT(v) do { (v)->va_supported = (v)->va_active = 0; } while (0)
#define VATTR_SET(v, a, x) do { (v)->a = (x); (v)->va_active |= 1; } while (0)

struct componentname { int cn_nameiop; };
struct nameidata {
	vnode_t ni_dvp, ni_vp;
	struct componentname ni_cnd;
};
#define CREATE 1
#define OP_MKDIR 10
#define LOCKPARENT 0x0008
#define NDINIT(ndp, op, pop, flags, segflg, namep, ctx) do { \
	(ndp)->ni_cnd.cn_nameiop = (op); (void)(pop); (void)(flags); (void)(segflg); \
	(void)(namep); (void)(ctx); } while (0)

vfs_context_t vfs_context_kernel(void);
kauth_cred_t vfs_context_ucred(vfs_context_t ctx);
proc_t vfs_context_proc(vfs_context_t ctx);
errno_t vnode_lookup(const char *path, int flags, vnode_t *vpp, vfs_context_t ctx);
errno_t vnode_open(const char *path, int fmode, int cmode, int flags, vnode_t *vpp, vfs_context_t ctx);
errno_t vnode_close(vnode_t vp, int flags, vfs_context_t ctx);
int vnode_put(vnode_t vp);
int vnode_setattr(vnode_t vp, struct vnode_attr *vap, vfs_context_t ctx);
int vn_rdwr(enum uio_rw rw, vnode_t vp, caddr_t base, int len, off_t offset, enum uio_seg segflg,
    int ioflg, kauth_cred_t cred, int *aresid, proc_t p);
int namei(struct nameidata *ndp);
void nameidone(struct nameidata *ndp);
int vn_mkdir(vnode_t dvp, vnode_t *vpp, struct nameidata *ndp, struct vnode_attr *vap, vfs_context_t ctx);
