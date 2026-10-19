#pragma once
#include <stdint.h>

#define FB_BASE		0xb8000000UL	/* fuxi reserved-memory splash_region (43 MiB); topaz used 0x5c000000 */
#define FB_W		1080
#define FB_H		2400
#define FB_STRIDE	(FB_W * 4)	/* a8r8g8b8, matches mainline simplefb */

#define RED	0xffff0000U
#define BLUE	0xff0000a0U
#define WHITE	0xffffffffU
#define YELLOW	0xffffff00U
#define GREEN	0xff00ff00U

extern volatile uint32_t *con_fb;

void con_clear(uint32_t bg);
void con_skip(void);
void con_str(const char *label, const char *s);
void con_hex(const char *label, uint64_t v);
/* label, then "a=xxxxxxxx b=xxxxxxxx" style pairs of 32-bit values */
void con_hex2(const char *label, const char *a, uint32_t va, const char *b, uint32_t vb);

#if defined(FUXI_FAST) && !defined(CONSOLE_IMPL)
/*
 * No-op console for timing-telemetry runs: with the MMU off every store is
 * strongly ordered and a screenful of scaled glyphs costs ~31 s of boot time.
 */
#define con_clear(bg)   ((void)0)
#define con_skip()      ((void)0)
#define con_str(l, s)   ((void)0)
#define con_hex(l, v)   ((void)0)
#define con_hex2(l, a, va, b, vb) ((void)0)
#endif
