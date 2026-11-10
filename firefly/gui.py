"""Tkinter 桌面界面（无实时预览，转换后给质量分级）。

配色：浅绿。视觉稿见 design/mockup.py；两边保持同一套色值。
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, TAGLINE, __version__
from .convert import Options, convert
from .help_text import HELP

EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".gif")
GRADE_TAG = {"A": "gA", "B": "gB", "C": "gC"}

# ---- 浅绿配色（改这里就改全局）----
C_BG = "#F2F7F2"        # 窗口底
C_CARD = "#FFFFFF"      # 卡片
C_BORDER = "#DCE7DE"
C_FIELD = "#FFFFFF"
C_TEXT = "#1C2B26"
C_SUB = "#5F736B"
C_ACCENT = "#1F8A6E"    # 主色（按钮/进度）
C_ACCENT_DK = "#17745C"
C_SEL = "#D8EFE4"       # 列表选中
C_HEAD = "#E8F1EA"      # 表头
C_ROWALT = "#F6FAF7"    # 隔行
C_A_BG, C_A_FG = "#E6F5EC", "#177245"
C_B_BG, C_B_FG = "#FFF6E7", "#8F5400"
C_C_BG, C_C_FG = "#FDEDEF", "#B3122B"


def asset(name: str) -> Path:
    """资源路径：源码运行与 PyInstaller 冻结后都要能找到。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "assets" / name


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} · {TAGLINE}  v{__version__}")
        self.geometry("1120x800")
        self.minsize(1000, 720)
        self.configure(bg=C_BG)
        self.files: list[str] = []
        self.q: queue.Queue = queue.Queue()
        self.cancel_ev = threading.Event()
        self.worker: threading.Thread | None = None

        self.out_dir = tk.StringVar(value=str(Path.home() / "Pictures" / "firefly"))
        self.v_mode = tk.StringVar(value="自动")
        self.v_bin = tk.StringVar(value="自动阈值 (Otsu)")
        self.v_win = tk.IntVar(value=51)
        self.v_mono = tk.StringVar(value="标准")
        self.v_color = tk.StringVar(value="平涂图标")
        self.v_invert = tk.BooleanVar(value=False)
        self.v_snap = tk.BooleanVar(value=True)
        self.v_ss = tk.BooleanVar(value=False)
        self.v_qc = tk.BooleanVar(value=True)
        self.v_status = tk.StringVar(value="就绪")
        self.v_count = tk.StringVar(value="0 个文件")

        self.fam = self._pick_font()
        self._style()
        self._build()
        self._sync_param_state()
        self._set_icon()
        self.after(120, self._poll)

    # ---------- 外观 ----------
    def _pick_font(self) -> str:
        try:
            import tkinter.font as tkfont

            fams = set(tkfont.families())
            for cand in ("Microsoft YaHei UI", "Microsoft YaHei"):
                if cand in fams:
                    return cand
        except Exception:
            pass
        return "TkDefaultFont"

    def _style(self):
        fam = self.fam
        self.option_add("*Font", (fam, 10))
        st = ttk.Style(self)
        try:
            st.theme_use("clam")  # clam 才能自定义配色；vista 主题不给改
        except tk.TclError:
            pass

        st.configure(".", background=C_BG, foreground=C_TEXT, font=(fam, 10))
        st.configure("TFrame", background=C_BG)
        st.configure("Card.TFrame", background=C_CARD)
        st.configure("TLabel", background=C_BG, foreground=C_TEXT)
        st.configure("Card.TLabel", background=C_CARD, foreground=C_TEXT)
        st.configure("Sub.TLabel", background=C_CARD, foreground=C_SUB)
        st.configure("Hint.TLabel", background=C_CARD, foreground=C_SUB, font=(fam, 9))
        st.configure("Count.TLabel", background=C_BG, foreground=C_SUB)
        st.configure("Status.TLabel", background=C_BG, foreground=C_SUB, font=(fam, 9))
        st.configure("Title.TLabel", background=C_BG, foreground=C_TEXT, font=(fam, 13, "bold"))
        st.configure("Link.TLabel", background=C_CARD, foreground=C_ACCENT, font=(fam, 9, "underline"))

        # 按钮：主色实心 + 次级描边
        st.configure("TButton", background="#F7FAF8", foreground=C_TEXT,
                     bordercolor=C_BORDER, focusthickness=1, padding=(10, 6),
                     relief="flat")
        st.map("TButton",
               background=[("active", "#EDF4EF"), ("disabled", "#F2F5F3")],
               foreground=[("disabled", "#A8B5AE")])
        st.configure("Go.TButton", background=C_ACCENT, foreground="#FFFFFF",
                     font=(fam, 10, "bold"), padding=(18, 7), relief="flat",
                     bordercolor=C_ACCENT)
        st.map("Go.TButton",
               background=[("active", C_ACCENT_DK), ("disabled", "#A9CDBF")],
               foreground=[("disabled", "#FFFFFF")])

        st.configure("TEntry", fieldbackground=C_FIELD, bordercolor=C_BORDER,
                     lightcolor=C_BORDER, darkcolor=C_BORDER, insertcolor=C_TEXT,
                     padding=5)
        st.configure("TCombobox", fieldbackground=C_FIELD, background=C_FIELD,
                     bordercolor=C_BORDER, arrowcolor=C_SUB, padding=4)
        st.configure("TSpinbox", fieldbackground=C_FIELD, bordercolor=C_BORDER,
                     arrowcolor=C_SUB, padding=4)
        st.map("TSpinbox",
               fieldbackground=[("disabled", "#F1F4F2")],
               foreground=[("disabled", "#A8B5AE")])
        st.configure("TCheckbutton", background=C_CARD, foreground=C_TEXT)
        st.map("TCheckbutton", background=[("active", C_CARD)])

        # 进度条
        st.configure("Green.Horizontal.TProgressbar", background=C_ACCENT,
                     troughcolor="#E4EDE7", bordercolor="#E4EDE7",
                     lightcolor=C_ACCENT, darkcolor=C_ACCENT, thickness=10)

        # 表格
        st.configure("Treeview", background=C_CARD, fieldbackground=C_CARD,
                     foreground=C_TEXT, bordercolor=C_BORDER, rowheight=26)
        st.configure("Treeview.Heading", background=C_HEAD, foreground=C_SUB,
                     relief="flat", padding=(6, 5))
        st.map("Treeview.Heading", background=[("active", "#DEEAE1")])
        st.map("Treeview", background=[("selected", C_SEL), ("!selected", C_CARD)],
               foreground=[("selected", C_TEXT)])

        # 滚动条
        st.configure("TScrollbar", background="#DCE7DE", troughcolor=C_BG,
                     bordercolor=C_BG, arrowcolor=C_SUB, relief="flat",
                     gripcount=0)
        st.map("TScrollbar",
               background=[("active", "#C3D5C9"), ("pressed", "#A9C2B1")])

        # clam 主题的复选框/单选框指示器默认是灰白小方块，勾选后几乎看不出，
        # 必须显式配色，否则「选中」和「未选中」几乎一样。
        for name, on_bg, on_fg in (
            ("TCheckbutton", C_CARD, C_ACCENT),
            ("Card.TCheckbutton", C_CARD, C_ACCENT),
        ):
            st.configure(name, background=C_CARD, foreground=C_TEXT,
                         indicatorcolor=C_FIELD, indicatorrelief="solid",
                         indicatormargin=(0, 0, 6, 0), padding=(2, 3))
            st.map(name,
                   background=[("active", C_CARD)],
                   indicatorcolor=[("selected", on_fg), ("!selected", C_FIELD)],
                   foreground=[("disabled", "#A8B5AE")])

        # 下拉框箭头区域
        st.map("TCombobox",
               fieldbackground=[("readonly", C_FIELD), ("disabled", "#F1F4F2")],
               foreground=[("disabled", "#A8B5AE")],
               background=[("readonly", C_FIELD), ("active", C_FIELD),
                           ("disabled", "#F1F4F2")],
               selectbackground=[("readonly", C_FIELD)],
               selectforeground=[("readonly", C_TEXT)])
        # 下拉列表本身（Listbox 部分）也要配，否则弹出的是系统白色
        self.option_add("*TCombobox*Listbox.background", C_CARD)
        self.option_add("*TCombobox*Listbox.foreground", C_TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", C_SEL)
        self.option_add("*TCombobox*Listbox.selectForeground", C_TEXT)

    def _set_icon(self):
        ico = asset("icon.ico")
        if ico.exists():
            try:
                self.iconbitmap(default=str(ico))
            except tk.TclError:
                pass

    # ---------- 布局 ----------
    def _build(self):
        outer = ttk.Frame(self, padding=(14, 10, 14, 10))
        outer.pack(fill="both", expand=True)

        # 标题栏
        head = ttk.Frame(outer)
        head.pack(fill="x", pady=(0, 8))
        try:
            self._logo_img = tk.PhotoImage(file=str(asset("logo_ui.png")))
            ttk.Label(head, image=self._logo_img, style="TLabel").pack(side="left")
        except tk.TclError:
            ttk.Label(head, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(head, text=f"v{__version__}", style="Status.TLabel").pack(
            side="left", padx=(10, 0))
        ttk.Label(head, text=TAGLINE, style="Status.TLabel").pack(
            side="left", padx=(12, 0))
        ttk.Button(head, text="使用说明", command=self._help).pack(side="right")

        # 输出目录卡
        outcard = ttk.Frame(outer, style="Card.TFrame", padding=(12, 10))
        outcard.pack(fill="x")
        ttk.Label(outcard, text="输出目录", style="Sub.TLabel").pack(side="left")
        ttk.Entry(outcard, textvariable=self.out_dir).pack(
            side="left", fill="x", expand=True, padx=(10, 8))
        ttk.Button(outcard, text="浏览…", command=self._pick_out).pack(side="left")
        ttk.Button(outcard, text="打开目录", command=self._open_out).pack(side="left", padx=(6, 0))

        # 主体：左文件列表 + 右设置
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True, pady=(8, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Card.TFrame", padding=(10, 8))
        left.grid(row=0, column=0, sticky="nsew")
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        bar = ttk.Frame(left, style="Card.TFrame")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Button(bar, text="添加图片…", command=self._add).pack(side="left")
        ttk.Button(bar, text="移除所选", command=self._remove).pack(side="left", padx=5)
        ttk.Button(bar, text="清空", command=self._clear).pack(side="left")
        ttk.Label(bar, textvariable=self.v_count, style="Sub.TLabel").pack(side="right")

        self.tree_files = ttk.Treeview(left, columns=("dir",), show="tree headings",
                                       selectmode="extended")
        self.tree_files.heading("#0", text="文件名", anchor="w")
        self.tree_files.column("#0", width=230, anchor="w")
        self.tree_files.heading("dir", text="所在目录", anchor="w")
        # 太长的路径会把「文件名」挤掉，固定宽度（内容在 _short_dir 里主动省略）
        self.tree_files.column("dir", width=250, anchor="w", stretch=True)
        self.tree_files.grid(row=1, column=0, sticky="nsew")
        self.tree_files.tag_configure("odd", background=C_ROWALT)
        fsb = ttk.Scrollbar(left, orient="vertical", command=self.tree_files.yview)
        self.tree_files.configure(yscrollcommand=fsb.set)
        fsb.grid(row=1, column=1, sticky="ns")

        right = ttk.Frame(body, style="Card.TFrame", padding=(12, 10))
        right.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        right.columnconfigure(1, weight=1)
        ttk.Label(right, text="转换设置", style="Card.TLabel",
                  font=(self.fam, 11, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        def row(label, widget, r):
            ttk.Label(right, text=label, style="Sub.TLabel").grid(
                row=r, column=0, sticky="w", pady=4, padx=(0, 10))
            widget.grid(row=r, column=1, sticky="ew", pady=4)

        self.cb_mode = ttk.Combobox(right, textvariable=self.v_mode, width=14,
                                    state="readonly",
                                    values=["自动", "单色线条", "彩色平涂"])
        self.cb_mode.bind("<<ComboboxSelected>>", lambda _e: self._sync_param_state())
        row("路线", self.cb_mode, 1)
        self.cb_bin = ttk.Combobox(right, textvariable=self.v_bin, width=14,
                                   state="readonly",
                                   values=["自动阈值 (Otsu)", "局部阈值 (Sauvola)"])
        self.cb_bin.bind("<<ComboboxSelected>>", lambda _e: self._sync_param_state())
        row("二值化", self.cb_bin, 2)
        self.sp_win = ttk.Spinbox(right, from_=15, to=99, increment=2,
                                  textvariable=self.v_win, width=8)
        row("Sauvola 窗口", self.sp_win, 3)
        self.cb_mono = ttk.Combobox(right, textvariable=self.v_mono, width=14,
                                    state="readonly",
                                    values=["平滑优先", "标准", "细节优先"])
        row("线条类细节", self.cb_mono, 4)
        self.cb_color = ttk.Combobox(right, textvariable=self.v_color, width=14,
                                     state="readonly",
                                     values=["平涂图标", "标准", "高保真", "细节优先"])
        row("彩色类风格", self.cb_color, 5)

        ttk.Checkbutton(right, text="反色（白画黑底）", variable=self.v_invert,
                        style="Card.TCheckbutton").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(right, text="几何吸附（圆/方不歪）", variable=self.v_snap,
                        style="Card.TCheckbutton").grid(
            row=7, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(right, text="超采样 ×2（边缘更顺，体积约 3 倍）", variable=self.v_ss,
                        style="Card.TCheckbutton").grid(
            row=8, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(right, text="转换后做质量检查", variable=self.v_qc,
                        style="Card.TCheckbutton").grid(
            row=9, column=0, columnspan=2, sticky="w")
        ttk.Label(right, text="文字类截图只能得到轮廓，\n不能选中 / 搜索文字。",
                  style="Hint.TLabel", justify="left").grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(8, 0))
        reset = ttk.Label(right, text="恢复默认设置", style="Link.TLabel",
                          cursor="hand2")
        reset.grid(row=11, column=0, columnspan=2, sticky="w", pady=(8, 0))
        reset.bind("<Button-1>", lambda _e: self._reset())

        # 动作行
        act = ttk.Frame(outer)
        act.pack(fill="x", pady=(8, 0))
        self.btn_start = ttk.Button(act, text="开始转换", style="Go.TButton",
                                    command=self._start)
        self.btn_start.pack(side="left")
        self.btn_cancel = ttk.Button(act, text="取消", command=self._cancel,
                                     state="disabled")
        self.btn_cancel.pack(side="left", padx=6)
        self.pb = ttk.Progressbar(act, mode="determinate", maximum=1, value=0,
                                  style="Green.Horizontal.TProgressbar")
        self.pb.pack(side="left", fill="x", expand=True, padx=(16, 12))
        ttk.Label(act, textvariable=self.v_status, style="Status.TLabel",
                  width=26, anchor="e").pack(side="left")

        # 结果表
        res = ttk.Frame(outer, style="Card.TFrame", padding=(10, 8))
        res.pack(fill="both", expand=True, pady=(8, 0))
        res.rowconfigure(0, weight=1)
        res.columnconfigure(0, weight=1)
        cols = ("mode", "grade", "ssim", "ratio", "note")
        self.tree = ttk.Treeview(res, columns=cols, show="tree headings", height=7)
        heads = {"mode": "路线", "grade": "等级", "ssim": "SSIM",
                 "ratio": "体积比", "note": "说明"}
        widths = {"mode": 66, "grade": 54, "ssim": 78, "ratio": 78, "note": 430}
        # 短列居中，长列左对齐：左对齐时数字看着像偏了
        anchors = {"mode": "center", "grade": "center", "ssim": "center",
                   "ratio": "center", "note": "w"}
        for c in cols:
            self.tree.heading(c, text=heads[c], anchor=anchors[c])
            self.tree.column(c, width=widths[c], anchor=anchors[c],
                             stretch=(c == "note"))
        self.tree.heading("#0", text="文件", anchor="w")
        self.tree.column("#0", width=230, anchor="w")
        self.tree.tag_configure("gA", background=C_A_BG, foreground=C_A_FG)
        self.tree.tag_configure("gB", background=C_B_BG, foreground=C_B_FG)
        self.tree.tag_configure("gC", background=C_C_BG, foreground=C_C_FG)
        self.tree.tag_configure("bad", background=C_C_BG, foreground=C_C_FG)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(res, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", self._open_row)

    def _reset(self):
        self.v_mode.set("自动")
        self.v_bin.set("自动阈值 (Otsu)")
        self.v_win.set(51)
        self.v_mono.set("标准")
        self.v_color.set("平涂图标")
        self.v_invert.set(False)
        self.v_snap.set(True)
        self.v_ss.set(False)
        self.v_qc.set(True)
        self._sync_param_state()

    def _sync_param_state(self):
        """Otsu 不用窗口参数，把 Sauvola 窗口置灰，免得以为调了有用。"""
        use_sauvola = self.v_bin.get().startswith("局部")
        self.sp_win.configure(state="normal" if use_sauvola else "disabled")
        auto = self.v_mode.get() == "自动"
        self.cb_mono.configure(state="disabled" if auto else "readonly")
        self.cb_color.configure(state="disabled" if auto else "readonly")

    # ---------- 文件管理 ----------
    def _refresh_files(self):
        self.tree_files.delete(*self.tree_files.get_children())
        for i, p in enumerate(self.files):
            tags = ("odd",) if i % 2 else ()
            self.tree_files.insert("", "end", text=Path(p).name,
                                   values=(self._short_dir(p),), tags=tags)
        self.v_count.set(f"{len(self.files)} 个文件")

    @staticmethod
    def _short_dir(p: str) -> str:
        """路径太长会被 Treeview 硬切成半截，这里主动从左边省略成 …\\a\\b。"""
        s = str(Path(p).parent)
        if len(s) <= 30:
            return s
        return "…" + s[-29:]

    def _add(self):
        paths = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[("图片", " ".join("*" + e for e in EXTS)), ("所有文件", "*.*")],
        )
        for p in paths:
            if p not in self.files:
                self.files.append(p)
        self._refresh_files()
        self.v_status.set(f"共 {len(self.files)} 个文件")

    def _remove(self):
        sel = {self.tree_files.index(i) for i in self.tree_files.selection()}
        if not sel:
            return
        self.files = [p for i, p in enumerate(self.files) if i not in sel]
        self._refresh_files()
        self.v_status.set(f"共 {len(self.files)} 个文件")

    def _clear(self):
        self.files.clear()
        self._refresh_files()
        self.v_status.set("就绪")

    def _pick_out(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.out_dir.set(d)

    def _help(self):
        win = tk.Toplevel(self)
        win.title(f"{APP_NAME} 使用说明 v{__version__}")
        win.geometry("860x740")
        win.configure(bg=C_BG)
        win.transient(self)
        wrap = ttk.Frame(win, padding=(14, 10))
        wrap.pack(fill="both", expand=True)
        # 大图只在帮助页出现（唯一能看到完整渐变+辉光的地方）
        try:
            self._hero_img = tk.PhotoImage(file=str(asset("logo_hero.png")))
            ttk.Label(wrap, image=self._hero_img, style="TLabel").pack(
                anchor="w", pady=(0, 8))
        except tk.TclError:
            pass
        frame = ttk.Frame(wrap)
        frame.pack(fill="both", expand=True)
        txt = tk.Text(frame, wrap="word", padx=10, pady=8, relief="flat",
                      bg=C_CARD, fg=C_TEXT, insertbackground=C_TEXT,
                      highlightthickness=1, highlightbackground=C_BORDER,
                      font=(self.fam, 10))
        sb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        txt.insert("1.0", HELP)
        txt.configure(state="disabled")

    def _open_out(self):
        d = Path(self.out_dir.get())
        d.mkdir(parents=True, exist_ok=True)
        os.startfile(str(d))  # noqa: S606

    # ---------- 转换 ----------
    def _opts(self) -> Options:
        return Options(
            mode={"自动": "自动", "单色线条": "单色", "彩色平涂": "彩色"}[self.v_mode.get()],
            binarize="otsu" if self.v_bin.get().startswith("自动") else "sauvola",
            window=int(self.v_win.get() or 51) | 1,
            mono_preset=self.v_mono.get(),
            color_preset=self.v_color.get(),
            invert=self.v_invert.get(),
            snap=self.v_snap.get(),
            supersample=2 if self.v_ss.get() else 1,
            do_qc=self.v_qc.get(),
        )

    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        if not self.files:
            messagebox.showinfo("提示", "先添加要转换的图片。")
            return
        out = Path(self.out_dir.get())
        try:
            out.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("输出目录不可用", str(exc))
            return
        self.tree.delete(*self.tree.get_children())
        self.cancel_ev.clear()
        self.btn_start.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.pb.config(maximum=len(self.files), value=0)
        self.v_status.set(f"0 / {len(self.files)}")
        self.worker = threading.Thread(
            target=self._run, args=(list(self.files), out, self._opts()), daemon=True
        )
        self.worker.start()

    def _run(self, files, out, opts):
        total = len(files)
        for i, f in enumerate(files, 1):
            if self.cancel_ev.is_set():
                self.q.put(("cancelled", i - 1, total))
                return
            self.q.put(("begin", i, total, Path(f).name))
            try:
                r = convert(f, out, opts)
            except Exception as exc:  # 单个文件失败不能拖垮整批
                self.q.put(("error", Path(f).name, str(exc)))
                self.q.put(("step",))
                continue
            self.q.put(("done", r))
        self.q.put(("finish", total, total))

    def _cancel(self):
        self.cancel_ev.set()
        self.v_status.set("正在取消…")

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "begin":
                    _, i, total, name = msg
                    self.v_status.set(f"{i} / {total}  {name[:14]}")
                elif kind == "done":
                    self._insert(msg[1])
                    self.pb.step(1)
                    self.update_idletasks()
                elif kind == "error":
                    _, name, err = msg
                    self.tree.insert("", "end", text=name,
                                     values=("-", "失败", "-", "-", err),
                                     tags=("bad",))
                    self.pb.step(1)
                elif kind == "step":
                    pass
                elif kind in ("finish", "cancelled"):
                    self.pb["value"] = msg[1]
                    self.btn_start.config(state="normal")
                    self.btn_cancel.config(state="disabled")
                    self.v_status.set("完成" if kind == "finish" else "已取消")
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _insert(self, r):
        name = Path(r.src).name
        if not r.ok:
            self.tree.insert("", "end", text=name,
                             values=("-", "失败", "-", "-", r.error), tags=("bad",))
            return
        ratio = f"{r.svg_bytes / r.src_bytes:.2f}×" if r.src_bytes else "—"
        # Treeview 只能整行着色，等级那一格的「居中」靠补足全角空格实现，
        # 否则两字宽的中文等级会贴在左边缘，看起来像没对齐。
        grade = r.grade if r.grade != "-" else "—"
        g_cell = f"　{grade}　" if grade in ("A", "B", "C") else grade
        self.tree.insert(
            "", "end", text=name,
            values=(r.mode, g_cell, f"{r.ssim:.4f}" if r.ssim else "—",
                    ratio, r.note),
            tags=(GRADE_TAG.get(r.grade, ""),),
        )

    def _open_row(self, _evt=None):
        sel = self.tree.selection()
        if not sel:
            return
        name = self.tree.item(sel[0], "text")
        out = Path(self.out_dir.get())
        for cand in (out / (Path(name).stem + ".svg"), out / (Path(name).stem + ".pdf")):
            if cand.exists():
                os.startfile(str(cand))  # noqa: S606
                return


def main():
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()


if __name__ == "__main__":
    main()
