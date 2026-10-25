/*
 * Extra XNU declarations for the host -fsyntax-only check of
 * bsd/dev/a733_eth.c (a733/xnu-a733-eth.patch), after sdmmc_kernel_stubs.h,
 * usbtouch_kernel_stubs.h and power_kernel_stubs.h. Signatures from
 * xnu-8796.141.3 (bsd/net/kpi_interface.h, bsd/net/if_ether.h,
 * bsd/net/kpi_protocol.h, bsd/sys/kpi_mbuf.h, bsd/sys/kpi_socket.h); the
 * structures only carry the fields the driver uses.
 */
typedef int errno_t;
typedef unsigned char u_char;
typedef unsigned char u_int8_t;
typedef unsigned short u_int16_t;
typedef unsigned int u_int32_t;
typedef unsigned long long u_int64_t;
typedef u_int32_t protocol_family_t;
typedef struct ifnet *ifnet_t;
typedef struct mbuf *mbuf_t;
typedef struct socket *socket_t;
typedef u_int32_t mbuf_flags_t;
typedef int mbuf_how_t;
typedef int mbuf_type_t;
struct sockaddr {
	u_int8_t sa_len;
	u_int8_t sa_family;
	char sa_data[14];
};
struct sockaddr_dl;

#define EOPNOTSUPP 102
#define NSEC_PER_MSEC 1000000ull
#define LCK_GRP_ATTR_NULL ((void *)0)
#define LCK_ATTR_NULL ((void *)0)
lck_grp_t *lck_grp_alloc_init(const char *name, void *attr);
lck_mtx_t *lck_mtx_alloc_init(lck_grp_t *grp, void *attr);
void bzero(void *s, size_t n);

#define PF_INET 2
#define AF_INET 2
#define SOCK_DGRAM 2
#define IFF_UP 0x1
#define IFF_BROADCAST 0x2
#define IFF_RUNNING 0x40
#define IFF_SIMPLEX 0x800
#define IFF_MULTICAST 0x8000
#define IFT_ETHER 0x6
#define ETHER_ADDR_LEN 6
#define ETHER_HDR_LEN 14
#define ETHERMTU 1500
#define IFNAMSIZ 16
#define SIOCSIFADDR 0x8020690cUL
#define SIOCAIFADDR 0x8040691aUL
#define SIOCSIFFLAGS 0x80206910UL
#define SIOCADDMULTI 0x80206931UL
#define SIOCDELMULTI 0x80206932UL
#define MBUF_DONTWAIT 1
#define MBUF_TYPE_DATA 1
#define MBUF_EXT 0x0001
#define IFNET_INIT_LEGACY 0x1
#define IFNET_INIT_CURRENT_VERSION 2
#define IFNET_FAMILY_ETHERNET 2
extern u_char etherbroadcastaddr[ETHER_ADDR_LEN];
static inline uint32_t htonl(uint32_t x) { return __builtin_bswap32(x); }

struct ether_header {
	u_char ether_dhost[ETHER_ADDR_LEN];
	u_char ether_shost[ETHER_ADDR_LEN];
	u_int16_t ether_type;
};
struct in_addr {
	uint32_t s_addr;
};
struct sockaddr_in {
	u_int8_t sin_len;
	u_int8_t sin_family;
	u_int16_t sin_port;
	struct in_addr sin_addr;
	char sin_zero[8];
};
struct ifaliasreq {
	char ifra_name[IFNAMSIZ];
	struct sockaddr ifra_addr;
	struct sockaddr ifra_broadaddr;
	struct sockaddr ifra_mask;
};
struct ifnet_stat_increment_param {
	u_int32_t packets_in, bytes_in, errors_in, packets_out, bytes_out, errors_out, collisions, dropped;
};

typedef errno_t (*ifnet_output_func)(ifnet_t interface, mbuf_t data);
typedef errno_t (*ifnet_ioctl_func)(ifnet_t interface, unsigned long cmd, void *data);
typedef void (*ifnet_detached_func)(ifnet_t interface);
typedef errno_t (*ifnet_demux_func)(ifnet_t interface, mbuf_t packet, char *header, protocol_family_t *protocol);
struct ifnet_demux_desc;
typedef errno_t (*ifnet_add_proto_func)(ifnet_t interface, protocol_family_t protocol,
    const struct ifnet_demux_desc *demux_array, u_int32_t demux_count);
typedef errno_t (*ifnet_del_proto_func)(ifnet_t interface, protocol_family_t protocol);
typedef errno_t (*ifnet_check_multi)(ifnet_t interface, const struct sockaddr *mcast);
typedef errno_t (*ifnet_framer_extended_func)(ifnet_t interface, mbuf_t *packet, const struct sockaddr *dest,
    const char *dest_linkaddr, const char *frame_type, u_int32_t *prepend_len, u_int32_t *postpend_len);

struct ifnet_init_eparams {
	u_int32_t ver;
	u_int32_t len;
	u_int32_t flags;
	const void *uniqueid;
	u_int32_t uniqueid_len;
	const char *name;
	u_int32_t unit;
	u_int32_t family;
	u_int32_t type;
	ifnet_output_func output;
	ifnet_demux_func demux;
	ifnet_add_proto_func add_proto;
	ifnet_del_proto_func del_proto;
	ifnet_check_multi check_multi;
	ifnet_framer_extended_func framer_extended;
	ifnet_ioctl_func ioctl;
	ifnet_detached_func detach;
	const void *broadcast_addr;
	u_int32_t broadcast_len;
};

errno_t ifnet_allocate_extended(const struct ifnet_init_eparams *init, ifnet_t *interface);
errno_t ifnet_attach(ifnet_t interface, const struct sockaddr_dl *ll_addr);
errno_t ifnet_set_flags(ifnet_t interface, u_int16_t new_flags, u_int16_t mask);
errno_t ifnet_set_lladdr(ifnet_t interface, const void *lladdr, size_t lladdr_len);
errno_t ifnet_set_mtu(ifnet_t interface, u_int32_t mtu);
errno_t ifnet_set_addrlen(ifnet_t interface, u_int8_t addrlen);
errno_t ifnet_set_hdrlen(ifnet_t interface, u_int8_t hdrlen);
errno_t ifnet_set_baudrate(ifnet_t interface, u_int64_t baudrate);
errno_t ifnet_input(ifnet_t interface, mbuf_t first_packet, const struct ifnet_stat_increment_param *stats);
errno_t ifnet_stat_increment_out(ifnet_t interface, u_int32_t packets_out, u_int32_t bytes_out, u_int32_t errors_out);
errno_t ether_demux(ifnet_t interface, mbuf_t packet, char *header, protocol_family_t *protocol);
errno_t ether_add_proto(ifnet_t interface, protocol_family_t protocol, const struct ifnet_demux_desc *demux_list,
    u_int32_t demux_count);
errno_t ether_del_proto(ifnet_t interface, protocol_family_t protocol);
errno_t ether_frameout_extended(ifnet_t interface, mbuf_t *packet, const struct sockaddr *ndest,
    const char *dest, const char *type, u_int32_t *prepend_len, u_int32_t *postpend_len);
errno_t ether_check_multi(ifnet_t ifp, const struct sockaddr *multicast);
errno_t proto_plumb(protocol_family_t protocol_family, ifnet_t ifp);

void *mbuf_data(mbuf_t mbuf);
errno_t mbuf_setdata(mbuf_t mbuf, void *data, size_t len);
errno_t mbuf_gethdr(mbuf_how_t how, mbuf_type_t type, mbuf_t *mbuf);
errno_t mbuf_mclget(mbuf_how_t how, mbuf_type_t type, mbuf_t *mbuf);
void mbuf_freem(mbuf_t mbuf);
errno_t mbuf_copydata(const mbuf_t mbuf, size_t offset, size_t length, void *out_data);
size_t mbuf_len(const mbuf_t mbuf);
void mbuf_setlen(mbuf_t mbuf, size_t len);
size_t mbuf_maxlen(const mbuf_t mbuf);
mbuf_flags_t mbuf_flags(const mbuf_t mbuf);
size_t mbuf_pkthdr_len(const mbuf_t mbuf);
void mbuf_pkthdr_setlen(mbuf_t mbuf, size_t len);
void mbuf_pkthdr_adjustlen(mbuf_t mbuf, int amount);
errno_t mbuf_pkthdr_setrcvif(mbuf_t mbuf, ifnet_t ifp);
void mbuf_pkthdr_setheader(mbuf_t mbuf, void *header);

typedef void (*sock_upcall)(socket_t so, void *cookie, int waitf);
errno_t sock_socket(int domain, int type, int protocol, sock_upcall callback, void *cookie, socket_t *new_so);
errno_t sock_ioctl(socket_t so, unsigned long request, void *argp);
void sock_close(socket_t so);

/* 9999w v5: BPF, media status, address / route report (bsd/net/bpf.h, if_media.h, if_private.h,
 * route_private.h, kpi_interface.h, sys/sockio.h). */
#define DLT_EN10MB 1
void bpfattach(ifnet_t interface, unsigned int data_link_type, unsigned int header_length);
void bpf_tap_in(ifnet_t interface, u_int32_t dlt, mbuf_t packet, void *header, size_t header_len);
void bpf_tap_out(ifnet_t interface, u_int32_t dlt, mbuf_t packet, void *header, size_t header_len);
#define IFM_ETHER 0x00000020
#define IFM_AUTO 0
#define IFM_10_T 3
#define IFM_100_TX 6
#define IFM_1000_T 16
#define IFM_FDX 0x00100000
#define IFM_HDX 0x00200000
#define IFM_AVALID 0x00000001
#define IFM_ACTIVE 0x00000002
typedef u_int64_t user_addr_t;
#define USER_ADDR_NULL ((user_addr_t)0)
#define CAST_USER_ADDR_T(a) ((user_addr_t)(uintptr_t)(a))
int copyout(const void *kaddr, user_addr_t udaddr, size_t len);
struct ifmediareq {
	char ifm_name[IFNAMSIZ];
	int ifm_current;
	int ifm_mask;
	int ifm_status;
	int ifm_active;
	int ifm_count;
	int *ifm_ulist;
};
struct ifmediareq64 {
	char ifm_name[IFNAMSIZ];
	int ifm_current;
	int ifm_mask;
	int ifm_status;
	int ifm_active;
	int ifm_count;
	user_addr_t ifmu_ulist __attribute__((aligned(8)));
};
struct ifmediareq32 {
	char ifm_name[IFNAMSIZ];
	int ifm_current;
	int ifm_mask;
	int ifm_status;
	int ifm_active;
	int ifm_count;
	u_int32_t ifmu_ulist;
};
#define SIOCGIFMEDIA32 0xc02c6938UL
#define SIOCGIFMEDIA64 0xc0306938UL
typedef struct ifaddr *ifaddr_t;
errno_t ifnet_get_address_list_family(ifnet_t interface, ifaddr_t **addresses, int family);
void ifnet_free_address_list(ifaddr_t *addresses);
errno_t ifaddr_address(ifaddr_t ifaddr, struct sockaddr *out_addr, u_int32_t addr_size);
const char *ifnet_name(ifnet_t interface);
u_int32_t ifnet_unit(ifnet_t interface);
static inline uint32_t ntohl(uint32_t x) { return __builtin_bswap32(x); }
struct rtentry {
	struct sockaddr *rt_gateway;
	ifnet_t rt_ifp;
};
struct rtentry *rtalloc1(struct sockaddr *dst, int report, uint32_t ignflags);
void rtfree(struct rtentry *rt);
