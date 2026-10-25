/* Private DRIVE_A acquisition helper. Linux ARM EABI, no libc, no device writes.
 * Source ABI: Linux v4.9 include/uapi/mtd/mtd-abi.h; ARM fcntl/stat/unistd.h.
 * The only ioctl requests below are information/read/per-FD mode operations.
 * Build/runtime tests do not establish this vendor driver's RAW/OOB support.
 */
typedef unsigned char u8;
typedef unsigned int u32;
typedef unsigned long long u64;
typedef long slong;
#define SIZE 12058624u
#define ERASE 131072u
#define PAGE 2048u
#define OOB 128u
#define CHUNK 65536u
#define O_RDONLY 0
#define O_WRONLY 1
#define O_CREAT 64
#define O_EXCL 128
/* ARM overrides these generic Linux flag values. */
#define O_DIRECTORY 0x4000
#define O_NOFOLLOW 0x8000
#define O_CLOEXEC 0x80000
#define MEMGETINFO 0x80204d01u
#define MEMGETBADBLOCK 0x40084d0bu
#define ECCGETSTATS 0x80104d12u
#define MTDFILEMODE 0x4d13u
#define MEMREADOOB64 0xc0184d16u
struct info { u8 type; u32 flags,size,erase,page,oob; u64 padding; };
struct oob_request { u64 start; u32 pad,length; u64 pointer; };
struct ecc { u32 corrected,failed,badblocks,bbtblocks; };
_Static_assert(sizeof(struct info)==32,"MTD info ABI");
_Static_assert(sizeof(struct oob_request)==24,"MTD OOB64 ABI");
_Static_assert(sizeof(struct ecc)==16,"MTD ECC ABI");
_Static_assert(__builtin_offsetof(struct oob_request,pointer)==16,"OOB pointer ABI");
#ifndef NB_MTD_TEST
_Static_assert(sizeof(void*)==4 && sizeof(long)==4,"ARM32 EABI required");
static slong sc(slong n,slong a,slong b,slong c,slong d) {
    register slong r0 __asm__("r0")=a;
    register slong r1 __asm__("r1")=b;
    register slong r2 __asm__("r2")=c;
    register slong r3 __asm__("r3")=d;
    register slong r7 __asm__("r7")=n;
    __asm__ volatile("svc #0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r7):"memory","cc");
    return r0;
}
#else
extern slong nb_test_syscall(slong,slong,slong,slong,slong);
#define sc nb_test_syscall
#endif
static u32 length(const char *s) { u32 n=0;while(s[n])n++;return n; }
static int equal(const char *a,const char *b) { while(*a && *a==*b){a++;b++;}return *a==*b; }
static int prefix(const char *s,const char *p) { while(*p){if(*s++!=*p++)return 0;}return 1; }
static slong rd(int f,void *b,u32 n) { slong r;do{r=sc(3,f,(slong)b,n,0);}while(r==-4);return r; }
static slong op(const char *p,int flags) { return sc(5,(slong)p,flags,0,0); }
static slong cl(int f) { return sc(6,f,0,0,0); }
static slong io(int f,u32 request,slong arg) { return sc(54,f,(slong)request,arg,0); }
static int error_number(slong r) { return r<0?(int)-r:0; }

struct writer { int fd,broken;u32 used,bytes;u8 data[CHUNK]; };
static struct writer writers[5]; /* corrected, raw, OOB, read log, bad map */
static u8 data[CHUNK],oob_data[OOB];
static struct ecc initial,last;
static int source=-1,raw=-1,summary=-1,outdir=-1,sd=-1;
static int status=0,last_errno=0,ecc_valid=0;
static u32 bad_records=0;
static const char *component="preflight",*reason="all selected bytes and metadata acquired";
static void fail(const char *c,const char *why,int err,int code) {
    if(!status){status=code;component=c;reason=why;last_errno=err;}
}
static int write_all(int fd,const void *buffer,u32 count,u32 *written) {
    const u8 *p=buffer;
    while(count) {
        slong r=sc(4,fd,(slong)p,count,0);
        if(r==-4)continue;
        if(r<=0 || (u32)r>count)return r<0?(int)-r:5;
        p+=r;count-=(u32)r;if(written)*written+=(u32)r;
    }
    return 0;
}
static int flush(struct writer *w) {
    int e=0;
    if(w->used && !w->broken)e=write_all(w->fd,w->data,w->used,&w->bytes);
    w->used=0;
    if(e){w->broken=1;fail("output","output write failed",e,30);}
    return !e && !w->broken;
}
static int append(struct writer *w,const void *buffer,u32 n) {
    const u8 *p=buffer;
    if(w->broken)return 0;
    while(n) {
        u32 take=CHUNK-w->used;if(take>n)take=n;
        for(u32 i=0;i<take;i++)w->data[w->used+i]=p[i];
        w->used+=take;p+=take;n-=take;
        if(w->used==CHUNK && !flush(w))return 0;
    }
    return 1;
}
static char text[2048];static u32 text_used;
static void txt(const char *s) { while(*s && text_used<sizeof(text)-1)text[text_used++]=*s++; }
static void num(u32 n) { char digits[10];u32 used=0;do{digits[used++]=(char)('0'+n%10);n/=10;}while(n);while(used)text[text_used++]=digits[--used]; }
static void signed_num(slong n) { if(n<0){txt("-");num((u32)-n);}else num((u32)n); }
static void field(const char *name,u32 value) { txt(name);txt("=");num(value);txt("\n"); }
static int new_file(const char *name) { return (int)sc(322,outdir,(slong)name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600); }
static void ecc_file(const char *name) {
    int fd=new_file(name);if(fd<0){fail("output","cannot create ECC record",-fd,30);return;}
    text_used=0;field("corrected",last.corrected);field("failed",last.failed);field("badblocks",last.badblocks);field("bbtblocks",last.bbtblocks);
    int e=write_all(fd,text,text_used,0);if(e)fail("output","cannot write ECC record",e,30);
    slong r=cl(fd);if(r<0)fail("output","cannot close ECC record",-r,30);
}
static int get_ecc(int fd,int code) {
    struct ecc now;
    slong r=io(fd,ECCGETSTATS,(slong)&now);
    if(r<0){fail("ecc","ECCGETSTATS unavailable",-r,code);return 0;}
    last=now;ecc_valid=1;return 1;
}
static int text_file(const char *path,char *buffer,u32 cap) {
    int fd=(int)op(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)return 0;
    slong r=rd(fd,buffer,cap-1);cl(fd);
    if(r<0 || (u32)r>=cap-1)return 0;
    buffer[r]=0;return 1;
}
static int check_field(const char *path,const char *expected) {
    char b[96];if(!text_file(path,b,sizeof(b)))return 0;
    u32 n=length(b);if(n && b[n-1]=='\n')b[n-1]=0;
    return equal(b,expected);
}
static int geometry(void) {
    static const char *paths[]={
        "/sys/class/mtd/mtd9/name","/sys/class/mtd/mtd9/type","/sys/class/mtd/mtd9/offset",
        "/sys/class/mtd/mtd9/size","/sys/class/mtd/mtd9/erasesize","/sys/class/mtd/mtd9/writesize",
        "/sys/class/mtd/mtd9/oobsize","/sys/class/mtd/mtd9/dev","/sys/class/mtd/mtd9/ecc_strength","/sys/class/mtd/mtd9/ecc_step_size"};
    static const char *values[]={"DRIVE_A","nand","203685888","12058624","131072","2048","128","90:18","8","512"};
    for(u32 i=0;i<10;i++)if(!check_field(paths[i],values[i]))return 0;
    return 1;
}
static u32 le32(const u8 *p) { return (u32)p[0]|(u32)p[1]<<8|(u32)p[2]<<16|(u32)p[3]<<24; }
static int validate_source(int fd) {
    /* Linux ARM stat64 is104 bytes; mode at16, 64-bit rdev at32. */
    union { u64 align;u8 b[104]; } s;
    slong r=sc(197,fd,(slong)s.b,0,0);
    if(r<0 || (le32(s.b+16)&0170000)!=0020000 || le32(s.b+32)!=0x5a13 || le32(s.b+36)!=0) {
        fail("preflight","source is not character device90:19",error_number(r),20);return 0;
    }
    struct info info;
    r=io(fd,MEMGETINFO,(slong)&info);
    if(r<0 || info.type!=4 || info.flags!=0x400 || info.size!=SIZE || info.erase!=ERASE || info.page!=PAGE || info.oob!=OOB) {
        fail("preflight","MEMGETINFO geometry mismatch or unavailable",error_number(r),20);return 0;
    }
    return 1;
}
static void log_read(const char *which,u32 offset,u32 requested,slong returned,int err) {
    text_used=0;txt(which);txt("\t");num(offset);txt("\t");num(requested);txt("\t");signed_num(returned);
    txt("\t");num((u32)err);txt("\t");num(last.corrected);txt("\t");num(last.failed);txt("\n");
    append(&writers[3],text,text_used);
}
static int main_read(int fd,int writer,const char *which,u32 offset) {
    slong r=rd(fd,data,CHUNK);int e=error_number(r);
    int observed=get_ecc(fd,30);
    log_read(which,offset,CHUNK,r<0?-1:r,e);
    if(r>0 && (u32)r<=CHUNK)append(&writers[writer],data,(u32)r);
    if(r!=CHUNK){fail(which,"main-area read failed or short",e,30);return 0;}
    if(!observed || last.failed){fail(which,"ECC failure observed",0,30);return 0;}
    return !status;
}
static int oob_read(u32 offset) {
    struct oob_request q={offset,0,OOB,(u64)(unsigned long)oob_data};
    slong r=io(raw,MEMREADOOB64,(slong)&q);int e=error_number(r);
    int observed=get_ecc(raw,30);
    log_read("raw-oob",offset,OOB,r<0?-1:(slong)q.length,e);
    if(r>=0 && q.length<=OOB)append(&writers[2],oob_data,q.length);
    if(r<0 || q.length!=OOB){fail("raw-oob","OOB capability/read failed or short",e,r<0 && offset==0?20:30);return 0;}
    if(!observed || last.failed){fail("raw-oob","ECC failure observed after OOB read",0,30);return 0;}
    return !status;
}
static int finish(void) {
    for(u32 i=0;i<5;i++)if(writers[i].fd>=0)flush(&writers[i]);
    if(source>=0 && ecc_valid){get_ecc(source,30);ecc_file("helper-ecc-after.txt");}
    if(ecc_valid && last.failed)fail("ecc","ECC failure present",0,30);
    for(u32 i=0;i<5;i++)if(writers[i].fd>=0){slong r=cl(writers[i].fd);if(r<0)fail("output","output close failed",-r,30);}
    if(source>=0)cl(source);if(raw>=0)cl(raw);
    if(!status && (writers[0].bytes!=SIZE || writers[1].bytes!=SIZE || writers[2].bytes!=SIZE/PAGE*OOB || bad_records!=SIZE/ERASE))fail("finalize","length/count mismatch",0,30);
    if(summary>=0) {
        text_used=0;txt(status?"INCOMPLETE\n":"COMPLETE\n");txt("component=");txt(status?component:"complete");txt("\nreason=");txt(reason);txt("\n");
        field("errno",(u32)last_errno);field("corrected_main_bytes",writers[0].bytes);field("raw_main_bytes",writers[1].bytes);field("raw_oob_bytes",writers[2].bytes);field("badblock_records",bad_records);
        field("ecc_corrected_before",initial.corrected);field("ecc_corrected_after",last.corrected);field("ecc_failures_before",initial.failed);field("ecc_failures_after",last.failed);
        txt("restorable_nand_backup=no\nfull_nand_backup=no\n");
        int e=write_all(summary,text,text_used,0);if(e)fail("output","summary write failed",e,30);
        slong r=cl(summary);if(r<0)fail("output","summary close failed",-r,30);
    }
    if(outdir>=0)cl(outdir);if(sd>=0)cl(sd);
    const char *message=status?"NAND partition capture INCOMPLETE.\n":"NAND partition capture COMPLETE; not a restore guarantee.\n";
    write_all(1,message,length(message),0);
    return status;
}
int nb_main(int argc,char **argv) {
    for(u32 i=0;i<5;i++)writers[i].fd=-1;
    const char *p;
    if(argc!=2 || !prefix(argv[1],"/tmp/SD0/bt-nand-backup-")){fail("preflight","output must be an SD capture directory",0,20);return finish();}
    p=argv[1]+length("/tmp/SD0/bt-nand-backup-");
    u32 digits=0;while(p[digits]>='0' && p[digits]<='9')digits++;
    if(!digits || digits>8 || p[digits]){fail("preflight","invalid capture directory suffix",0,20);return finish();}
    sd=(int)op("/tmp/SD0",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(sd<0){fail("preflight","SD directory open failed",-sd,20);return finish();}
    outdir=(int)sc(322,sd,(slong)(argv[1]+length("/tmp/SD0/")),O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC,0);
    if(outdir<0){fail("preflight","capture directory open failed",-outdir,20);return finish();}
    summary=new_file("helper-summary.txt");
    if(summary<0){fail("preflight","existing or unavailable summary file",-summary,20);return finish();}
    char mounts[4096];int mounted=0;
    if(text_file("/proc/self/mounts",mounts,sizeof(mounts)))for(p=mounts;*p;p++)if((p==mounts || p[-1]=='\n') && prefix(p,"c: /tmp/SD0 ambafs "))mounted=1;
    if(!mounted || !geometry()){fail("preflight","SD mount or exact DRIVE_A sysfs geometry mismatch",0,20);return finish();}
    source=(int)op("/dev/mtd9ro",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(source<0){fail("preflight","read-only source open failed",-source,20);return finish();}
    if(!validate_source(source) || !get_ecc(source,20))return finish();
    initial=last;ecc_file("helper-ecc-before.txt");
    if(last.failed){fail("ecc","ECC failure already present",0,20);return finish();}
    static const char *names[]={"DRIVE_A-corrected-main.bin","DRIVE_A-raw-main.bin","DRIVE_A-raw-oob.bin","read-status.tsv","DRIVE_A-badblocks.tsv"};
    for(u32 i=0;i<5;i++){writers[i].fd=new_file(names[i]);if(writers[i].fd<0){fail("output","existing or unavailable output file",-writers[i].fd,30);return finish();}}
    const char *read_header="component\toffset\trequested\treturned\terrno\tcorrected_bits\tecc_failures\n";
    const char *map_header="offset\tis_bad\terrno\n";
    append(&writers[3],read_header,length(read_header));
    append(&writers[4],map_header,length(map_header));
    for(u32 offset=0;offset<SIZE;offset+=CHUNK)if(!main_read(source,0,"corrected-main",offset))return finish();
    for(u32 offset=0;offset<SIZE;offset+=ERASE) {
        u64 where=offset;slong r=io(source,MEMGETBADBLOCK,(slong)&where);
        text_used=0;num(offset);txt("\t");signed_num(r<0?-1:r);txt("\t");num((u32)error_number(r));txt("\n");append(&writers[4],text,text_used);
        if(r<0 || r>1){fail("badblocks","bad-block query failed",error_number(r),20);return finish();}
        bad_records++;
    }
    if(!flush(&writers[4]))return finish();
    raw=(int)op("/dev/mtd9ro",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(raw<0){fail("raw-main","read-only RAW source open failed",-raw,20);return finish();}
    if(!validate_source(raw))return finish();
    slong r=io(raw,MTDFILEMODE,3); /* Scalar3, NOT a pointer; mode belongs to this FD. */
    if(r<0){fail("raw-main","RAW file mode unavailable",-r,20);return finish();}
    for(u32 offset=0;offset<SIZE;offset+=CHUNK) {
        if(!main_read(raw,1,"raw-main",offset))return finish();
        for(u32 page=offset;page<offset+CHUNK;page+=PAGE)if(!oob_read(page))return finish();
    }
    return finish();
}
#ifndef NB_MTD_TEST
__attribute__((used,noreturn)) void nb_start(u32 *stack) {
    int result=nb_main((int)stack[0],(char**)&stack[1]);
    sc(1,result,0,0,0);__builtin_unreachable();
}
__attribute__((naked,noreturn)) void _start(void) { __asm__ volatile("mov r0, sp\nb nb_start"); }
#endif
