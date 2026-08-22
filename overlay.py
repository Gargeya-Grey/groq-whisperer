"""Voice island — premium pill for Groq Whisperer.

Bottom-center premium pill, 2x the previous size.

  420x76  (was 210x38)  • 12pt type  • 7-bar waveform  • divider  • dot pulse
  Segoe UI Variable / Segoe UI 12pt normal, integer-snapped, DPI aware.

  Listening   7-bar micro waveform + soft red pulse + label
  Thinking    3-dot breathing (refined)
  Done/err    check / warn + quick fade

30 fps, Tkinter-only, idle-hidden.

Always-on-top · click-through · not in Alt-Tab · never steals focus.
"""

from __future__ import annotations

import collections
import math
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import font as tkfont

# -- premium geometry (2x prior 210x38) -------------------------------------
# Apply: 70% scale (30% down) then 70% width only (30% narrower): W = 420*0.7*0.7, H = 76*0.7
WIDTH, HEIGHT, BOTTOM_MARGIN, FRAME_MS = 206, 53, 88, 33
BG = "#1F1F23"
STRIPE = "#2E2E33"

def _to_rgb(s): return (int(s[1:3],16), int(s[3:5],16), int(s[5:7],16))
_IDLE, _HOT = _to_rgb("#6A6A70"), _to_rgb("#F2F2F7")
_BG = _to_rgb(BG)
DOT_RGB = {k: _to_rgb(v) for k,v in {
    "listening": "#FF3B30", "transcribing": "#6EA8FE",
    "success": "#34C759", "error": "#FF9F0A", "status": "#8E8E93",
}.items()}
_LABEL_FG, _LABEL_MUTED = "#E8E8EC", "#A9AAB0"
DOT_STR = {"listening":"#FF3B30","transcribing":"#6EA8FE","success":"#34C759","error":"#FF9F0A","status":"#8E8E93"}

N_BARS, BAR_W, BAR_PITCH, BAR_MAX, BAR_MIN = 7, 2.8, 7.0, 10.0, 1.8
_DWMWA_CORNER, _DWMWCP_ROUND, _GWL_EX = 33, 2, -20
_WS_EX_LAYERED, _WS_EX_TRANSP, _WS_EX_TOOL, _WS_EX_NOACT = 0x00080000,0x00000020,0x00000080,0x08000000

def _mix_rgb(a,b,t):
    return "#%02x%02x%02x" % (int(a[0]+(b[0]-a[0])*t), int(a[1]+(b[1]-a[1])*t), int(a[2]+(b[2]-a[2])*t))

_BAR_PAL = [_mix_rgb(_IDLE,_HOT, i/15) for i in range(16)]
def _bar_col(v): return _BAR_PAL[int(min(15, max(0, int((v*1.0+0.16)*15))))]
_halo_cache = {}
def _halo_col(base_rgb, a):
    k=(base_rgb, int(a*20))
    if k not in _halo_cache:
        t=0.12 + (a % 1)*0.06
        _halo_cache[k]=_mix_rgb(_BG, base_rgb, t)
    return _halo_cache[k]

class VoiceIsland:
    def __init__(self):
        self._q: "queue.Queue" = queue.Queue()
        self._levels = collections.deque(maxlen=72)
        self._closing=False; self._root=None
        self._state="status"; self._label=""; self._dot_rgb=DOT_RGB["status"]; self._dot_str=DOT_STR["status"]
        self._hide_at=None; self._alpha=0.0; self._target=0.0; self._mapped=False
        self._vals=[0.0]*N_BARS
        self._jitter=[random.Random(0xC0FFEE+i).random() for i in range(N_BARS)]
        self._t0=None

    def show_listening(self):     self._q.put(lambda: self._set("listening","Listening"))
    def show_transcribing(self):  self._q.put(lambda: self._set("transcribing","Thinking\u2026"))
    def show_success(self, m="Pasted"): self._q.put(lambda: self._set("success",m,1.02))
    def show_error(self, m):      self._q.put(lambda: self._set("error",m,1.35))
    def show_status(self, m, seconds=2.2): self._q.put(lambda: self._set("status",m,seconds))
    def push_level(self, v): self._levels.append((time.monotonic(), v if 0<=v<=1 else max(0,min(1,v))))
    def close(self): self._q.put(lambda: setattr(self,"_closing",True))
    def run(self):
        self._build()
        self._root.after(FRAME_MS, self._tick)
        self._root.mainloop()

    def _set(self, st, label, hide=None):
        self._state, self._label = st, label
        self._dot_rgb, self._dot_str = DOT_RGB[st], DOT_STR[st]
        self._hide_at = (time.monotonic()+hide) if hide is not None else None
        if not self._mapped and self._root is not None:
            self._root.deiconify(); self._root.lift(); self._mapped=True
        self._target=1.0
    def _hide(self): self._target=0.0; self._hide_at=None

    def _build(self):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try: import ctypes as _ct; _ct.windll.user32.SetProcessDPIAware()
            except Exception: pass
        r=tk.Tk()
        r.title("Groq Whisperer")
        r.overrideredirect(True)
        r.attributes("-topmost",True); r.attributes("-alpha",0.0)
        r.configure(bg=BG)
        try: r.tk.call("tk","scaling", r.tk.call("tk","scaling"))
        except Exception: pass
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry(f"{WIDTH}x{HEIGHT}+{(sw-WIDTH)//2}+{sh-HEIGHT-BOTTOM_MARGIN}")
        r.withdraw()
        self._cv=tk.Canvas(r, bg=BG, highlightthickness=0, bd=0)
        self._cv.pack(fill="both", expand=True)
        # Premium type: Segoe UI Variable if present, else Segoe UI; 12pt, clear at 2x
        fam="Segoe UI Variable"
        try:
            tkfont.Font(root=r, family=fam, size=1)
        except Exception:
            fam="Segoe UI"
        self._font=tkfont.Font(root=r, family=fam, size=9, weight="normal")
        self._font_sym=tkfont.Font(root=r, family=fam, size=9, weight="normal")
        self._t0=time.monotonic()
        r.update_idletasks()
        self._style(r); self._root=r

    def _style(self, r):
        try:
            import ctypes
            user32=ctypes.WinDLL("user32", use_last_error=True)
            hwnd=user32.GetParent(r.winfo_id()) or r.winfo_id()
            ex=user32.GetWindowLongW(hwnd, _GWL_EX)
            user32.SetWindowLongW(hwnd,_GWL_EX, ex|_WS_EX_LAYERED|_WS_EX_TRANSP|_WS_EX_TOOL|_WS_EX_NOACT)
            ok=False
            try:
                dwm=ctypes.WinDLL("dwmapi")
                pref=ctypes.c_int(_DWMWCP_ROUND)
                ok=dwm.DwmSetWindowAttribute(hwnd,_DWMWA_CORNER, ctypes.byref(pref), ctypes.sizeof(pref))==0
            except Exception: pass
            if not ok:
                gdi=ctypes.WinDLL("gdi32", use_last_error=True)
                R=HEIGHT//2
                rg=gdi.CreateRoundRectRgn(0,0,WIDTH+1,HEIGHT+1,R*2,R*2)
                user32.SetWindowRgn(hwnd,rg,True)
        except Exception: pass

    def _tick(self):
        r=self._root
        if not r: return
        try:
            drained=0
            while drained<8:
                try: fn=self._q.get_nowait()
                except queue.Empty: break
                fn(); drained+=1
            now=time.monotonic()
            if self._hide_at is not None and now>=self._hide_at: self._hide()
            if self._closing: r.destroy(); self._root=None; return
            dt=min(0.08, now-self._t0); self._t0=now
            if self._alpha!=self._target:
                rate=11.0 if self._target>self._alpha else 9.0
                self._alpha+=(self._target-self._alpha)*min(1.0, dt*rate)
                if abs(self._target-self._alpha)<0.012: self._alpha=self._target
                try: r.attributes("-alpha", self._alpha)
                except tk.TclError: pass
            if self._target==0.0 and self._alpha==0.0 and self._mapped:
                r.withdraw(); self._mapped=False
            if not self._mapped and self._target==0.0:
                r.after(80, self._tick); return
            self._step(now); self._draw(now)
            r.after(FRAME_MS, self._tick)
        except tk.TclError:
            self._root=None

    def _level_at(self, t):
        h=self._levels
        if not h: return 0.0
        bv,bd=0.0,1e9
        for tt,vv in reversed(h):
            d=tt-t
            if d<0: d=-d
            if d<bd: bd,bv=d,vv
            if tt<=t: break
            if bd>0.32: break
        return 0.0 if bd>0.32 else bv

    def _step(self, now):
        dt=0.033
        mid=(N_BARS-1)/2
        for i in range(N_BARS):
            if self._state=="listening":
                d=(abs(i-mid)/max(mid,1))*0.034 + self._jitter[i]*0.006
                tgt=self._level_at(now-d) + 0.02 + 0.014*math.sin(now*2.0+i*0.48)
            elif self._state=="transcribing":
                tgt=0.18 + 0.10*math.sin(now*2.15+i*0.62) + self._jitter[i]*0.04
            else:
                tgt=0.05 + self._jitter[i]*0.02
            if tgt<0: tgt=0
            elif tgt>1: tgt=1
            v=self._vals[i]
            v+=(tgt-v)*min(1.0, dt*(20 if tgt>v else 9))
            self._vals[i]=v

    def _draw(self, now):
        cv=self._cv; cv.delete("all")
        # No hair stroke drawn on canvas — keeps window's single rounded outer edge (from SetWindowRgn/DWM) as the only border. The double-ring came from drawing HAIR arcs inside a region-clipped window.
        cy=HEIGHT//2
        tx_y=cy
        label=self._label
        tw=self._font.measure(label) if label else 0

        if self._state=="listening":
            span=(N_BARS-1)*BAR_PITCH
            div_w=1
            gap1, gap2 = 14, 10
            dot_r=4.5
            group_w = span + gap1 + div_w + gap2 + dot_r*2 + 7 + tw
            x0=(WIDTH - group_w)/2
            # bars (centered block)
            for i in range(N_BARS):
                h=BAR_MIN + self._vals[i]*BAR_MAX
                x=x0 + i*BAR_PITCH
                cv.create_line(int(x), cy-int(h), int(x), cy+int(h), width=BAR_W, capstyle="round", fill=_bar_col(self._vals[i]))
            bx=x0+span
            # subtle vertical divider
            cv.create_line(bx+gap1, cy-10, bx+gap1, cy+10, fill=STRIPE, width=1)
            lx=bx+gap1+div_w+gap2
            pulse=0.5+0.5*math.sin(now*4.2)
            rr=dot_r+pulse*0.9
            cv.create_oval(lx-rr-1, cy-rr-1, lx+rr+1, cy+rr+1, fill=_halo_col(self._dot_rgb,pulse), outline="")
            pr=dot_r-0.2+pulse*0.35
            cv.create_oval(lx-pr, cy-pr, lx+pr, cy+pr, fill=DOT_STR["listening"], outline="")
            cv.create_text(int(lx+dot_r+7), tx_y, text=label, anchor="w", fill=_LABEL_FG, font=self._font)
        elif self._state=="transcribing":
            dg, dots_w, gap2 = 11, 22, 12
            x0=(WIDTH-(dots_w+gap2+tw))/2; cx0=x0+dg
            for k in range(3):
                a=0.32+0.68*(0.5+0.5*math.sin(now*2.4+k*0.9))
                idx=int(a*15); rr=2.6+a*1.0
                x=cx0+(k-1)*dg
                cv.create_oval(x-rr, cy-rr, x+rr, cy+rr, fill=_BAR_PAL[idx], outline="")
            cv.create_text(int(x0+dots_w+gap2), tx_y, text=label, anchor="w", fill=_LABEL_MUTED, font=self._font)
        else:
            if self._state=="status":
                cv.create_text(WIDTH//2, tx_y, text=label, anchor="center", fill=_LABEL_MUTED, font=self._font)
            else:
                sym="\u2713" if self._state=="success" else "\u2022"
                sw=self._font.measure(sym+" ")
                x0=(WIDTH-(sw+tw))//2
                cv.create_text(int(x0), tx_y, text=sym, anchor="w", fill=self._dot_str, font=self._font)
                cv.create_text(int(x0+sw), tx_y, text=label, anchor="w", fill=_LABEL_FG, font=self._font)


class NullIsland:
    def show_listening(self): pass
    def show_transcribing(self): pass
    def show_success(self, m="Pasted"): pass
    def show_error(self, m): pass
    def show_status(self, m, s=2.2): pass
    def push_level(self, v): pass
    def close(self): pass
    def run(self): pass


def create_island():
    try: import tkinter; return VoiceIsland()
    except Exception: return NullIsland()


def _synth(t):
    ph=math.sin(t*1.7)+0.6*math.sin(t*0.53+1.2)
    if ph<=-0.2: return 0.0
    return min(1.0,(0.45+0.55*abs(math.sin(t*9.1))**0.7)*(0.6+0.4*math.sin(t*3.1))+__import__("random").random()*0.20)


def _demo():
    isl=VoiceIsland()
    def w():
        time.sleep(0.5)
        while True:
            isl.show_listening()
            t0=time.time()
            while time.time()-t0<2.6:
                isl.push_level(_synth(time.time())); time.sleep(0.03)
            isl.show_transcribing(); time.sleep(1.5)
            isl.show_success("Pasted"); time.sleep(1.05)
            isl.show_listening()
            t0=time.time()
            while time.time()-t0<1.7:
                isl.push_level(_synth(time.time())); time.sleep(0.03)
            isl.show_error("Too short"); time.sleep(1.3)
            time.sleep(0.45)
    threading.Thread(target=w, daemon=True).start()
    isl.run()

if __name__=="__main__": _demo()
