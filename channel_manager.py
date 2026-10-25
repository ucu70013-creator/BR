#!/usr/bin/env python3
"""
Telegram Channel Manager
pip install telethon Pillow
"""
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import json, threading, os, tempfile
from datetime import datetime

try:
    from PIL import ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import asyncio
    from telethon import TelegramClient
    from telethon.errors import FloodWaitError
    HAS_TELETHON = True
except ImportError:
    HAS_TELETHON = False

# ── Palette ──────────────────────────────────────────────────────────────────
BG_MAIN    = "#17212B"
BG_HEADER  = "#0D1923"
BG_SIDEBAR = "#0E1621"
BG_INPUT   = "#0D1923"
BG_MY      = "#2B5278"
BG_FIELD   = "#242F3D"
BG_ACTIVE  = "#1C2B3A"
ACCENT     = "#5288C1"
TEXT_MAIN  = "#F0F0F0"
TEXT_DIM   = "#6C7883"
BORDER     = "#0E1621"

F_MAIN  = ("Segoe UI", 11)
F_BOLD  = ("Segoe UI", 11, "bold")
F_SMALL = ("Segoe UI", 9)
F_TIME  = ("Segoe UI", 8)

_HERE       = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_HERE, "tg_manager_config.json")
SESSION_DIR = os.path.join(_HERE, "sessions")

API_ID   = 24565698
API_HASH = "5a084b434f8505ace703485b9da85040"


# ── Telethon engine (bot token) ───────────────────────────────────────────────
class TGEngine:
    def __init__(self):
        os.makedirs(SESSION_DIR, exist_ok=True)
        self._loop   = asyncio.new_event_loop()
        self._client = None
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro, timeout=60):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    def _session_path(self, token: str) -> str:
        safe = token.split(":")[0]
        return os.path.join(SESSION_DIR, f"bot_{safe}")

    def connect(self, token: str):
        async def _():
            self._client = TelegramClient(
                self._session_path(token), API_ID, API_HASH,
                system_version='4.16.30-vxCUSTOM')
            await self._client.start(bot_token=token)
            return True
        return self._run(_())

    def get_dialogs(self, limit=200) -> list:
        async def _():
            dialogs = await self._client.get_dialogs(limit=limit)
            out = []
            for d in dialogs:
                e = d.entity
                title = (getattr(e, 'title', None)
                         or getattr(e, 'first_name', None)
                         or str(d.id))
                if getattr(e, 'last_name', None):
                    title = title + ' ' + e.last_name
                out.append({"id": d.id, "title": title.strip()})
            return out
        try:
            return self._run(_(), timeout=90)
        except Exception as e:
            print(f"[get_dialogs] {e}")
            return []

    def get_chat_info(self, chat_id: int) -> dict:
        async def _():
            e = await self._client.get_entity(chat_id)
            return {"title": getattr(e, "title", None)
                    or getattr(e, "first_name", str(chat_id))}
        try:
            return self._run(_())
        except Exception:
            return {"title": str(chat_id)}

    def get_history(self, chat_id: int, limit=200) -> list:
        async def _():
            try:
                entity = await self._client.get_entity(chat_id)
            except Exception:
                entity = chat_id
            msgs = await self._client.get_messages(entity, limit=limit)
            out = []
            for m in reversed(msgs):
                text = m.text or ("🖼 Фото" if m.photo else
                                  "📎 Файл" if m.document else "")
                if not text:
                    continue
                out.append({"id": m.id, "text": text,
                            "date": int(m.date.timestamp())})
            return out
        try:
            return self._run(_(), timeout=60)
        except Exception as e:
            print(f"[get_history] {chat_id}: {e}")
            return []

    def send_text(self, chat_id: int, text: str) -> dict:
        async def _():
            m = await self._client.send_message(chat_id, text)
            return {"id": m.id, "text": text, "date": int(m.date.timestamp())}
        return self._run(_())

    def send_photo(self, chat_id: int, path: str, caption: str = "") -> dict:
        async def _():
            m = await self._client.send_file(
                chat_id, path,
                caption=caption or None,
                force_document=False,
            )
            label = f"🖼 {caption}" if caption else "🖼 Фото"
            return {"id": m.id, "text": label, "date": int(m.date.timestamp())}
        return self._run(_(), timeout=120)

    def edit(self, chat_id: int, msg_id: int, text: str):
        async def _():
            await self._client.edit_message(chat_id, msg_id, text)
        self._run(_())

    def delete(self, chat_id: int, msg_id: int):
        async def _():
            await self._client.delete_messages(chat_id, [msg_id])
        self._run(_())


# ── Bubble widget ─────────────────────────────────────────────────────────────
class Bubble(tk.Frame):
    def __init__(self, parent, msg: dict, on_edit, on_delete):
        super().__init__(parent, bg=BG_MAIN)
        self.msg = msg
        self._oe = on_edit
        self._od = on_delete
        self._tv = tk.StringVar(value=msg["text"])
        self._build()

    def _build(self):
        row = tk.Frame(self, bg=BG_MAIN)
        row.pack(fill="x", padx=14, pady=2)
        tk.Frame(row, bg=BG_MAIN, width=80).pack(side="left")

        bub = tk.Frame(row, bg=BG_MY, padx=12, pady=7)
        bub.pack(side="right", anchor="e")

        lbl = tk.Label(bub, textvariable=self._tv, font=F_MAIN,
                       fg=TEXT_MAIN, bg=BG_MY,
                       wraplength=440, justify="left", anchor="w")
        lbl.pack(anchor="w")

        ts = datetime.fromtimestamp(self.msg["date"]).strftime("%H:%M")
        tk.Label(bub, text=ts, font=F_TIME, fg=TEXT_DIM, bg=BG_MY).pack(anchor="e")

        menu = tk.Menu(self, tearoff=0, bg="#1C2B3A", fg=TEXT_MAIN,
                       activebackground=ACCENT, activeforeground="white",
                       font=F_MAIN, bd=0)
        menu.add_command(label="✏   Редактировать",
                         command=lambda: self._oe(self.msg, self))
        menu.add_command(label="🗑   Удалить",
                         command=lambda: self._od(self.msg, self))
        menu.add_separator()
        menu.add_command(label="📋   Копировать", command=self._copy)

        for w in (row, bub, lbl):
            w.bind("<Button-3>", lambda e, m=menu: m.tk_popup(e.x_root, e.y_root))
            w.bind("<Double-Button-1>", lambda e: self._oe(self.msg, self))

    def set_text(self, t: str):
        self.msg["text"] = t
        self._tv.set(t)

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.msg["text"])


# ── Auth Dialog (bot token) ───────────────────────────────────────────────────
class AuthDialog(tk.Toplevel):
    def __init__(self, parent, engine: TGEngine, on_done):
        super().__init__(parent)
        self._engine  = engine
        self._on_done = on_done
        self.title("Токен бота")
        self.configure(bg=BG_MAIN)
        self.geometry("460x220")
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)

        tk.Label(self, text="🤖  Введи токен бота", font=F_BOLD,
                 fg=TEXT_MAIN, bg=BG_MAIN).pack(pady=(22, 10))
        tk.Label(self, text="Bot Token (от @BotFather):", font=F_MAIN,
                 fg=TEXT_DIM, bg=BG_MAIN).pack(anchor="w", padx=24)
        self._e = tk.Entry(self, font=F_MAIN, fg=TEXT_MAIN, bg=BG_FIELD,
                           insertbackground=TEXT_MAIN, relief="flat", bd=0)
        self._e.pack(fill="x", padx=24, ipady=8)
        self._e.focus_set()

        tk.Button(self, text="Подключить →", font=F_MAIN, fg="white",
                  bg=ACCENT, activebackground="#3A7BD5", bd=0, pady=8,
                  cursor="hand2", command=self._do).pack(fill="x", padx=24,
                                                         pady=(14, 4))
        self._st = tk.Label(self, text="", font=F_SMALL, fg=TEXT_DIM, bg=BG_MAIN)
        self._st.pack()
        self.bind("<Return>", lambda _: self._do())

    def _do(self):
        token = self._e.get().strip()
        if not token:
            return
        self._st.config(text="подключение…")

        def _work():
            try:
                self._engine.connect(token)
                self.after(0, lambda: (self.destroy(), self._on_done(token)))
            except Exception as ex:
                self.after(0, lambda: self._st.config(text=f"Ошибка: {ex}"))

        threading.Thread(target=_work, daemon=True).start()


# ── Edit Dialog ───────────────────────────────────────────────────────────────
class EditDialog(tk.Toplevel):
    def __init__(self, parent, text: str):
        super().__init__(parent)
        self.result = None
        self.title("Редактировать")
        self.configure(bg=BG_MAIN)
        self.geometry("500x200")
        self.resizable(False, False)
        self.grab_set(); self.transient(parent)

        tk.Label(self, text="Новый текст:", font=F_MAIN,
                 fg=TEXT_DIM, bg=BG_MAIN).pack(anchor="w", padx=18, pady=(16, 4))
        self._t = tk.Text(self, height=4, font=F_MAIN, fg=TEXT_MAIN,
                          bg=BG_FIELD, insertbackground=TEXT_MAIN,
                          relief="flat", bd=0, padx=10, pady=8)
        self._t.pack(fill="x", padx=18)
        self._t.insert("1.0", text); self._t.focus_set()

        bf = tk.Frame(self, bg=BG_MAIN)
        bf.pack(fill="x", padx=18, pady=12)
        tk.Button(bf, text="  Сохранить  ", font=F_MAIN, fg="white",
                  bg=ACCENT, activebackground="#3A7BD5", bd=0, pady=7,
                  cursor="hand2", command=self._ok).pack(side="right")
        tk.Button(bf, text="  Отмена  ", font=F_MAIN, fg=TEXT_DIM,
                  bg=BG_FIELD, activebackground=BG_ACTIVE, bd=0, pady=7,
                  cursor="hand2", command=self.destroy).pack(side="right", padx=8)
        self.bind("<Return>", lambda e: self._ok())
        self.wait_window()

    def _ok(self):
        self.result = self._t.get("1.0", "end-1c").strip()
        self.destroy()


# ── Main App ──────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Telegram Manager")
        self.geometry("900x700")
        self.minsize(600, 450)
        self.configure(bg=BG_MAIN)

        self._cfg          = self._load_cfg()
        self._engine       = TGEngine() if HAS_TELETHON else None
        self._channels     = list(self._cfg.get("channels", []))
        self._active       = None
        self._bubbles      = {}
        self._ch_btns      = {}
        self._msgs_frames  = {}
        self._loaded_cids  = set()

        self._build()

        token = self._cfg.get("token")
        if token:
            self._auto_connect(token)
        else:
            self.after(200, self._open_auth)

    # ── Config ────────────────────────────────────────────────────────────────
    def _load_cfg(self):
        try:
            return json.loads(open(CONFIG_FILE).read())
        except Exception:
            return {}

    def _save_cfg(self):
        open(CONFIG_FILE, "w").write(json.dumps(self._cfg, ensure_ascii=False))

    # ── Connect ───────────────────────────────────────────────────────────────
    def _auto_connect(self, token: str):
        self._v_sub.set("подключение…")

        def _do():
            try:
                self._engine.connect(token)
                self.after(0, lambda: self._v_sub.set("загрузка чатов…"))
                self.after(0, self._refresh_sidebar)
                dialogs = self._engine.get_dialogs(limit=300)
                existing = {c["id"] for c in self._channels}
                for d in dialogs:
                    if d["id"] not in existing:
                        self._channels.append(d)
                self._cfg["channels"] = self._channels
                self._save_cfg()
                self.after(0, self._refresh_sidebar)
                self.after(0, lambda: self._v_sub.set(
                    f"{len(self._channels)} чатов"))
            except Exception as e:
                err = str(e)
                self.after(0, lambda: self._v_sub.set("ошибка"))
                self.after(0, lambda msg=err: messagebox.showerror("Ошибка", msg))

        threading.Thread(target=_do, daemon=True).start()

    def _on_auth_done(self, token: str):
        self._cfg["token"] = token
        self._save_cfg()
        self._auto_connect(token)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build(self):
        self._build_sidebar()
        right = tk.Frame(self, bg=BG_MAIN)
        right.pack(side="left", fill="both", expand=True)
        self._build_header(right)
        self._build_chat(right)
        self._build_input(right)

    def _build_sidebar(self):
        sb = tk.Frame(self, bg=BG_SIDEBAR, width=220)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        hdr = tk.Frame(sb, bg=BG_HEADER, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Чаты", font=F_BOLD,
                 fg=TEXT_MAIN, bg=BG_HEADER).pack(side="left", padx=14, pady=16)

        self._ch_list = tk.Frame(sb, bg=BG_SIDEBAR)
        self._ch_list.pack(fill="both", expand=True)
        self._ch_list.bind_all("<MouseWheel>", self._on_scroll)

        btm = tk.Frame(sb, bg=BG_SIDEBAR, pady=6)
        btm.pack(fill="x", side="bottom")
        tk.Button(btm, text="＋  Добавить вручную",
                  font=F_MAIN, fg=ACCENT, bg=BG_SIDEBAR,
                  activebackground=BG_ACTIVE, activeforeground=ACCENT,
                  bd=0, cursor="hand2",
                  command=self._add_channel).pack(fill="x", padx=10, pady=2)
        tk.Button(btm, text="↻  Обновить список",
                  font=F_MAIN, fg=TEXT_DIM, bg=BG_SIDEBAR,
                  activebackground=BG_ACTIVE, activeforeground=TEXT_MAIN,
                  bd=0, cursor="hand2",
                  command=self._reload_dialogs).pack(fill="x", padx=10, pady=2)
        tk.Button(btm, text="⚙  Сменить токен",
                  font=F_SMALL, fg=TEXT_DIM, bg=BG_SIDEBAR,
                  activebackground=BG_ACTIVE,
                  bd=0, cursor="hand2",
                  command=self._open_auth).pack(fill="x", padx=10, pady=2)

    def _on_scroll(self, e):
        self._canvas.yview_scroll(int(-1*(e.delta/120)), "units")

    def _build_header(self, parent):
        hdr = tk.Frame(parent, bg=BG_HEADER, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        av = tk.Canvas(hdr, width=38, height=38, bg=BG_HEADER,
                       highlightthickness=0)
        av.pack(side="left", padx=(14,0), pady=9)
        av.create_oval(1,1,37,37, fill=ACCENT, outline="")
        av.create_text(19,19, text="💬", font=("Segoe UI",15))

        info = tk.Frame(hdr, bg=BG_HEADER)
        info.pack(side="left", padx=10, fill="y", pady=8)
        self._v_title = tk.StringVar(value="Выбери чат")
        tk.Label(info, textvariable=self._v_title, font=F_BOLD,
                 fg=TEXT_MAIN, bg=BG_HEADER).pack(anchor="w")
        self._v_sub = tk.StringVar(value="")
        tk.Label(info, textvariable=self._v_sub, font=F_SMALL,
                 fg=TEXT_DIM, bg=BG_HEADER).pack(anchor="w")

    def _build_chat(self, parent):
        wrap = tk.Frame(parent, bg=BG_MAIN)
        wrap.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(wrap, bg=BG_MAIN,
                                 highlightthickness=0, bd=0)
        chat_sb = tk.Scrollbar(wrap, orient="vertical",
                               command=self._canvas.yview,
                               bg=BG_MAIN, troughcolor=BG_MAIN)
        self._canvas.configure(yscrollcommand=chat_sb.set)
        chat_sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._placeholder = tk.Frame(self._canvas, bg=BG_MAIN)
        tk.Label(self._placeholder, text="Выбери чат слева",
                 font=("Segoe UI",13), fg=TEXT_DIM, bg=BG_MAIN
                 ).pack(expand=True, pady=80)
        self._cwin = self._canvas.create_window(
            (0,0), window=self._placeholder, anchor="nw")

        self._placeholder.bind("<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfig(self._cwin, width=e.width))

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x")

    def _build_input(self, parent):
        inp = tk.Frame(parent, bg=BG_INPUT, pady=10, padx=14)
        inp.pack(fill="x")

        self._inp = tk.Text(inp, height=1, font=F_MAIN,
                            fg=TEXT_MAIN, bg=BG_FIELD,
                            insertbackground=TEXT_MAIN,
                            relief="flat", bd=0, padx=12, pady=9, wrap="word")
        self._inp.pack(side="left", fill="x", expand=True, padx=(0,8))

        self._ph = "Написать сообщение…"
        self._inp.insert("1.0", self._ph)
        self._inp.config(fg=TEXT_DIM)
        self._inp.bind("<FocusIn>",      self._ph_clear)
        self._inp.bind("<FocusOut>",     self._ph_restore)
        self._inp.bind("<Return>",       self._on_enter)
        self._inp.bind("<Shift-Return>", lambda e: None)
        self._inp.bind("<KeyRelease>",   self._auto_h)
        self._inp.bind("<Control-a>",
            lambda e: (self._inp.tag_add("sel","1.0","end"),"break")[1])
        self._inp.bind("<Control-A>",
            lambda e: (self._inp.tag_add("sel","1.0","end"),"break")[1])
        self._inp.bind("<Control-v>", self._on_paste)
        self._inp.bind("<Control-V>", self._on_paste)

        tk.Button(inp, text="📎", font=("Segoe UI",15), fg=TEXT_DIM,
                  bg=BG_INPUT, activebackground=BG_INPUT,
                  bd=0, cursor="hand2",
                  command=self._pick_photo).pack(side="right", padx=(0,4))
        tk.Button(inp, text="➤", font=("Segoe UI",20), fg=ACCENT,
                  bg=BG_INPUT, activebackground=BG_INPUT,
                  bd=0, cursor="hand2",
                  command=self._send).pack(side="right")

    # ── Sidebar ───────────────────────────────────────────────────────────────
    def _refresh_sidebar(self):
        for w in self._ch_list.winfo_children():
            w.destroy()
        self._ch_btns.clear()
        for ch in self._channels:
            self._add_ch_row(ch)

    def _reload_dialogs(self):
        if not self._engine:
            return
        self._v_sub.set("обновление…")

        def _do():
            dialogs = self._engine.get_dialogs(limit=300)
            existing = {c["id"] for c in self._channels}
            added = 0
            for d in dialogs:
                if d["id"] not in existing:
                    self._channels.append(d)
                    added += 1
                    self.after(0, lambda ch=d: self._add_ch_row(ch))
            self._cfg["channels"] = self._channels
            self._save_cfg()
            self.after(0, lambda: self._v_sub.set(
                f"{len(self._channels)} чатов"))

        threading.Thread(target=_do, daemon=True).start()

    def _add_ch_row(self, ch: dict):
        cid   = ch["id"]
        title = ch.get("title", str(cid))
        initial = title[0].upper() if title else "?"

        row = tk.Frame(self._ch_list, bg=BG_SIDEBAR, cursor="hand2")
        row.pack(fill="x", pady=1)

        av = tk.Canvas(row, width=42, height=42, bg=BG_SIDEBAR,
                       highlightthickness=0)
        av.pack(side="left", padx=(10,8), pady=6)
        av.create_oval(1,1,41,41, fill=ACCENT, outline="")
        av.create_text(21,21, text=initial, font=F_BOLD, fill="white")

        info = tk.Frame(row, bg=BG_SIDEBAR)
        info.pack(side="left", fill="both", expand=True, pady=8)
        tk.Label(info, text=title, font=F_BOLD, fg=TEXT_MAIN,
                 bg=BG_SIDEBAR, anchor="w").pack(anchor="w")
        tk.Label(info, text=str(cid), font=F_SMALL, fg=TEXT_DIM,
                 bg=BG_SIDEBAR, anchor="w").pack(anchor="w")

        for w in (row, av, info):
            w.bind("<Button-1>", lambda e, c=cid: self._select_channel(c))

        self._ch_btns[cid] = row
        self._highlight_active()

    def _highlight_active(self):
        for cid, row in self._ch_btns.items():
            col = BG_ACTIVE if cid == self._active else BG_SIDEBAR
            for w in row.winfo_children():
                try:
                    w.configure(bg=col)
                    for ww in w.winfo_children():
                        try: ww.configure(bg=col)
                        except: pass
                except: pass
            row.configure(bg=col)

    def _add_channel(self):
        cid_str = simpledialog.askstring(
            "Добавить чат",
            "Введи Chat ID:",
            parent=self)
        if not cid_str:
            return
        try:
            cid = int(cid_str.strip())
        except Exception:
            messagebox.showerror("Ошибка", "Неверный Chat ID"); return

        if any(c["id"] == cid for c in self._channels):
            self._select_channel(cid); return

        def _do():
            info = self._engine.get_chat_info(cid) if self._engine else \
                   {"title": str(cid)}
            ch = {"id": cid, "title": info["title"]}
            self._channels.append(ch)
            self._cfg["channels"] = self._channels
            self._save_cfg()
            self.after(0, lambda: self._add_ch_row(ch))
            self.after(0, lambda: self._select_channel(cid))

        threading.Thread(target=_do, daemon=True).start()

    def _select_channel(self, cid: int):
        self._active = cid
        self._highlight_active()
        ch = next((c for c in self._channels if c["id"] == cid), None)
        self._v_title.set(ch["title"] if ch else str(cid))

        if cid not in self._msgs_frames:
            frame = tk.Frame(self._canvas, bg=BG_MAIN)
            frame.bind("<Configure>",
                lambda e: self._canvas.configure(
                    scrollregion=self._canvas.bbox("all")))
            self._msgs_frames[cid] = frame
            self._bubbles[cid] = {}

        self._canvas.itemconfig(self._cwin, window=self._msgs_frames[cid])
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

        if cid not in self._loaded_cids:
            self._loaded_cids.add(cid)
            self._v_sub.set("загрузка истории…")
            if not self._engine:
                self._v_sub.set("нет подключения"); return

            def _do():
                msgs = self._engine.get_history(cid, limit=200)
                self.after(0, lambda: self._v_sub.set(f"{len(msgs)} сообщений"))
                for m in msgs:
                    self.after(0, lambda mm=m, c=cid: self._render_bubble(c, mm))
                self.after(300, lambda: self._canvas.yview_moveto(1.0))

            threading.Thread(target=_do, daemon=True).start()
        else:
            count = len(self._bubbles.get(cid, {}))
            self._v_sub.set(f"{count} сообщений")
            self.after(100, lambda: self._canvas.yview_moveto(1.0))

    # ── Chat ──────────────────────────────────────────────────────────────────
    def _render_bubble(self, cid: int, msg: dict):
        if msg["id"] in self._bubbles.get(cid, {}):
            return
        frame = self._msgs_frames.get(cid)
        if frame is None:
            return
        b = Bubble(frame, msg, on_edit=self._edit_msg, on_delete=self._delete_msg)
        b.pack(fill="x")
        self._bubbles.setdefault(cid, {})[msg["id"]] = b
        if cid == self._active:
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _scroll_bottom(self):
        self.after(60, lambda: self._canvas.yview_moveto(1.0))

    # ── Input ─────────────────────────────────────────────────────────────────
    def _ph_clear(self, _):
        if self._inp.get("1.0","end-1c") == self._ph:
            self._inp.delete("1.0","end")
            self._inp.config(fg=TEXT_MAIN)

    def _ph_restore(self, _):
        if not self._inp.get("1.0","end-1c").strip():
            self._inp.delete("1.0","end")
            self._inp.insert("1.0", self._ph)
            self._inp.config(fg=TEXT_DIM)

    def _auto_h(self, _=None):
        lines = int(self._inp.index("end-1c").split(".")[0])
        self._inp.config(height=min(max(lines,1),5))

    def _get_text(self):
        t = self._inp.get("1.0","end-1c").strip()
        return "" if t == self._ph else t

    def _clear_inp(self):
        self._inp.delete("1.0","end")
        self._inp.config(height=1)
        self._ph_restore(None)

    def _on_enter(self, _):
        self._send(); return "break"

    def _on_paste(self, event):
        if not HAS_PIL:
            messagebox.showinfo("Нет Pillow",
                "Установи Pillow для вставки фото из буфера:\n"
                "pip install Pillow")
            return
        try:
            img = ImageGrab.grabclipboard()
        except Exception as e:
            print(f"[clipboard] {e}", flush=True)
            return
        if img is None:
            return
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        try:
            img.save(tmp.name, "PNG")
        except Exception as e:
            print(f"[clipboard save] {e}", flush=True)
            return
        finally:
            tmp.close()
        caption = self._get_text()
        self._clear_inp()
        self._do_send_photo(tmp.name, caption)
        return "break"

    # ── Send / Edit / Delete ──────────────────────────────────────────────────
    def _send(self):
        text = self._get_text()
        if not text or not self._engine or not self._active:
            return
        self._clear_inp()
        cid = self._active

        def _do():
            try:
                m = self._engine.send_text(cid, text)
                self.after(0, lambda: self._render_bubble(cid, m))
                self.after(0, self._scroll_bottom)
            except Exception as e:
                self.after(0, lambda msg=str(e): messagebox.showerror("Ошибка", msg))

        threading.Thread(target=_do, daemon=True).start()

    def _pick_photo(self):
        path = filedialog.askopenfilename(
            title="Выбери фото",
            filetypes=[("Изображения","*.jpg *.jpeg *.png *.webp *.gif"),
                       ("Все файлы","*.*")])
        if not path: return
        caption = self._get_text()
        self._clear_inp()
        self._do_send_photo(path, caption)

    def _do_send_photo(self, path: str, caption: str = ""):
        if not self._engine or not self._active:
            return
        cid = self._active

        def _do():
            try:
                m = self._engine.send_photo(cid, path, caption)
                self.after(0, lambda: self._render_bubble(cid, m))
                self.after(0, self._scroll_bottom)
            except Exception as e:
                import traceback
                print(f"[send_photo] cid={cid} path={path!r} err={e}", flush=True)
                traceback.print_exc()
                self.after(0, lambda msg=str(e): messagebox.showerror("Ошибка отправки фото", msg))

        threading.Thread(target=_do, daemon=True).start()

    def _edit_msg(self, msg: dict, bubble: Bubble):
        dlg = EditDialog(self, msg["text"])
        new = dlg.result
        if not new or new == msg["text"]:
            return
        cid = self._active

        def _do():
            try:
                self._engine.edit(cid, msg["id"], new)
                self.after(0, lambda: bubble.set_text(new))
            except Exception as e:
                self.after(0, lambda msg=str(e): messagebox.showerror("Ошибка", msg))

        threading.Thread(target=_do, daemon=True).start()

    def _delete_msg(self, msg: dict, bubble: Bubble):
        if not messagebox.askyesno("Удалить", "Удалить сообщение?", parent=self):
            return
        cid = self._active

        def _do():
            try:
                self._engine.delete(cid, msg["id"])
                self._bubbles.get(cid, {}).pop(msg["id"], None)
                self.after(0, bubble.destroy)
            except Exception as e:
                self.after(0, lambda msg=str(e): messagebox.showerror("Ошибка", msg))

        threading.Thread(target=_do, daemon=True).start()

    # ── Auth ──────────────────────────────────────────────────────────────────
    def _open_auth(self):
        if not HAS_TELETHON:
            messagebox.showerror("Ошибка", "pip install telethon")
            return
        AuthDialog(self, self._engine, self._on_auth_done)


if __name__ == "__main__":
    App().mainloop()
