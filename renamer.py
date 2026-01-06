import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont


# ==== НАСТРОЙКИ ТРАНСЛИТА (можно править руками) ===========================

DEFAULT_MAPPING_MULTI = [
    ("shch", "щ"),
    ("sch", "щ"),
    ("yo", "ё"),
    ("jo", "ё"),
    ("zh", "ж"),
    ("kh", "х"),
    ("ts", "ц"),
    ("ch", "ч"),
    ("sh", "ш"),
    ("yu", "ю"),
    ("ju", "ю"),
    ("ya", "я"),
    ("ja", "я"),
    ("ye", "е"),
    ("je", "е"),
]

DEFAULT_MAPPING_SINGLE = {
    "a": "а",
    "b": "б",
    "v": "в",
    "g": "г",
    "d": "д",
    "e": "е",
    "z": "з",
    "i": "и",
    "j": "й",
    "y": "й",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "f": "ф",
    "h": "х",
    "c": "ц",
    "x": "кс",
    "q": "к",
    "w": "в",
    "'": "ь",   # апостроф = мягкий знак
}


def load_translit_config():
    mapping_multi = DEFAULT_MAPPING_MULTI
    mapping_single = DEFAULT_MAPPING_SINGLE

    cfg_path = os.path.join(os.path.dirname(__file__), "translit_config.json")
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if "mapping_multi" in cfg:
                mapping_multi = [(a, b) for a, b in cfg["mapping_multi"]]
            if "mapping_single" in cfg:
                m = dict(DEFAULT_MAPPING_SINGLE)
                m.update(cfg["mapping_single"])
                mapping_single = m
        except Exception:
            pass

    return mapping_multi, mapping_single


MAPPING_MULTI, MAPPING_SINGLE = load_translit_config()


def translit_to_cyrillic(text: str) -> str:
    """
    Перевод простого транслита → кириллицу,
    с сохранением регистра и поддержкой апострофа.
    """

    def apply_case(src: str, dst: str) -> str:
        if src.isupper():
            return dst.upper()
        if src[0].isupper() and src[1:].islower():
            return dst.capitalize()
        return dst

    result = []
    i = 0
    lower = text.lower()

    while i < len(text):
        ch = text[i]
        ch_lower = lower[i]

        if not ("a" <= ch_lower <= "z" or ch_lower == "'"):
            result.append(ch)
            i += 1
            continue

        replaced = False

        for latin, cyr in MAPPING_MULTI:
            ln = len(latin)
            segment = text[i:i+ln]
            if lower[i:i+ln] == latin:
                result.append(apply_case(segment, cyr))
                i += ln
                replaced = True
                break
        if replaced:
            continue

        if ch_lower in MAPPING_SINGLE:
            result.append(apply_case(ch, MAPPING_SINGLE[ch_lower]))
        else:
            result.append(ch)

        i += 1

    return "".join(result)


def has_cyrillic(s: str) -> bool:
    return any("а" <= ch.lower() <= "я" or ch in ("ё", "Ё") for ch in s)


class RenameToolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Переименование файлов и папок (транслит → кириллица)")
        self.geometry("1200x700")

        self.directory = tk.StringVar()

        # items: модель (все элементы)
        # {
        #   "rel_dir": str,
        #   "old_name": str,
        #   "new_name": str,
        #   "do_rename": bool,
        #   "is_dir": bool,
        #   "locked": bool,
        #   "modified": bool,  # [M] – кириллическое имя изменено вручную
        # }
        self.items = []

        # индексы с конфликтами (индексы в self.items)
        self.conflict_indices = set()

        # текущий выбранный индекс в self.items
        self.current_index = None

        # фильтры
        self.filter_conflicts_only = tk.BooleanVar(value=False)
        self.filter_by_dir = tk.BooleanVar(value=False)
        self.current_filter_dir = ""   # rel_dir текущего фильтра по подкаталогу

        # сортировка
        self.sort_column = None  # одно из: type, exc, lock, conf, mod, path, new
        self.sort_reverse = False

        self.create_widgets()
         # НАСТРОЙКА ШРИФТА И ВЫСОТЫ СТРОК ДЛЯ TREEVIEW
        style = ttk.Style(self)

        # базовый моноширинный шрифт
        tree_font = tkfont.nametofont("TkFixedFont")
        tree_font.configure(size=10)  # можно 9–11, на вкус

        # высота строки = высота шрифта + небольшой запас
        row_h = tree_font.metrics("linespace") + 4

        style.configure(
            "Treeview",
            font=tree_font,
            rowheight=row_h,
        )
        style.configure(
            "Treeview.Heading",
            font=("TkDefaultFont", 9, "bold"),
        )

    # ---------- UI ----------

    def create_widgets(self):
        frame_top = ttk.Frame(self)
        frame_top.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(frame_top, text="Директория:").pack(side=tk.LEFT)
        entry_dir = ttk.Entry(frame_top, textvariable=self.directory, width=50)
        entry_dir.pack(side=tk.LEFT, padx=(5, 5))

        ttk.Button(frame_top, text="Обзор...", command=self.browse_directory).pack(side=tk.LEFT)
        ttk.Button(frame_top, text="Сканировать", command=self.scan_directory).pack(side=tk.LEFT, padx=(10, 0))

        ttk.Button(frame_top, text="Сохранить сессию", command=self.save_session).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(frame_top, text="Загрузить сессию", command=self.load_session).pack(side=tk.LEFT, padx=(5, 0))

        # Легенда и фильтры
        frame_legend = ttk.Frame(self)
        frame_legend.pack(fill=tk.X, padx=10, pady=(0, 5))

        ttk.Label(
            frame_legend,
            text=(
                "Тип: DIR/FILE, Исключен: X, Лок: L, Конфликт: !, Изменён: M"
            ),
            foreground="gray"
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 3))

        chk_conf = ttk.Checkbutton(
            frame_legend,
            text="Только конфликтующие",
            variable=self.filter_conflicts_only,
            command=self.on_filter_change
        )
        chk_conf.grid(row=1, column=0, sticky="w", padx=(0, 10))

        chk_dir = ttk.Checkbutton(
            frame_legend,
            text="Только выбранная поддиректория",
            variable=self.filter_by_dir,
            command=self.on_filter_change
        )
        chk_dir.grid(row=1, column=1, sticky="w")

        self.label_current_dir_filter = ttk.Label(frame_legend, text="Фильтр по поддиректории: (нет)")
        self.label_current_dir_filter.grid(row=1, column=2, sticky="w", padx=(20, 0))

        # Центральная часть
        frame_center = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        frame_center.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        # Таблица
        frame_table = ttk.Frame(frame_center)
        frame_center.add(frame_table, weight=3)

        ttk.Label(frame_table, text="Элементы:").pack(anchor="w")

        cols = ("type", "exc", "lock", "conf", "mod", "path", "new")
        self.tree = ttk.Treeview(
            frame_table,
            columns=cols,
            show="headings",
            selectmode="browse"
        )

        headings = {
            "type": "Тип",
            "exc": "Исключен",
            "lock": "Лок",
            "conf": "Конфликт",
            "mod": "Изменён",
            "path": "Старый путь",
            "new": "Новое имя",
        }

        for col in cols:
            self.tree.heading(col, text=headings[col],
                              command=lambda c=col: self.on_column_click(c))

        # ширины по умолчанию
        self.tree.column("type", width=70, anchor="center")
        self.tree.column("exc", width=80, anchor="center")
        self.tree.column("lock", width=60, anchor="center")
        self.tree.column("conf", width=80, anchor="center")
        self.tree.column("mod", width=80, anchor="center")
        self.tree.column("path", width=400, anchor="w")
        self.tree.column("new", width=250, anchor="w")

        vsb = ttk.Scrollbar(frame_table, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # Панель редактирования
        frame_edit = ttk.Frame(frame_center)
        frame_center.add(frame_edit, weight=2)

        ttk.Label(frame_edit, text="Текущий элемент:").pack(anchor="w")
        self.label_current = ttk.Label(frame_edit, text="(не выбран)")
        self.label_current.pack(anchor="w", pady=(0, 10))

        self.label_type = ttk.Label(frame_edit, text="Тип: -")
        self.label_type.pack(anchor="w", pady=(0, 10))

        ttk.Label(frame_edit, text="Новое имя (только имя, без пути):").pack(anchor="w")
        self.new_name_var = tk.StringVar()
        self.entry_new_name = ttk.Entry(frame_edit, textvariable=self.new_name_var, width=40)
        self.entry_new_name.pack(anchor="w", pady=(0, 10))

        self.do_rename_var = tk.BooleanVar(value=True)
        chk_rename = ttk.Checkbutton(frame_edit, text="Переименовывать этот элемент", variable=self.do_rename_var)
        chk_rename.pack(anchor="w")

        self.locked_var = tk.BooleanVar(value=False)
        chk_locked = ttk.Checkbutton(
            frame_edit,
            text="Зафиксировать имя (не менять автоматически)",
            variable=self.locked_var,
            command=self.toggle_lock_for_selected
        )
        chk_locked.pack(anchor="w", pady=(5, 5))

        ttk.Button(frame_edit, text="Сохранить изменения для элемента",
                   command=self.apply_changes_to_selected).pack(anchor="w", pady=(10, 5))

        ttk.Button(
            frame_edit,
            text="Авто-решение конфликтов (для незафиксированных)",
            command=self.auto_resolve_conflicts
        ).pack(anchor="w", pady=(5, 5))

        # Нижняя часть: переименование + лог
        frame_bottom = ttk.Frame(self)
        frame_bottom.pack(fill=tk.BOTH, expand=False, padx=10, pady=(0, 10))

        ttk.Button(frame_bottom, text="Переименовать все отмеченные элементы",
                   command=self.rename_items).pack(anchor="w", pady=(0, 5))

        ttk.Label(frame_bottom, text="Лог:").pack(anchor="w")
        self.text_log = tk.Text(frame_bottom, height=8, state="disabled")
        self.text_log.pack(fill=tk.BOTH, expand=True)

    # ---------- ЛОГИКА ----------

    def browse_directory(self):
        dirname = filedialog.askdirectory()
        if dirname:
            self.directory.set(dirname)

    def scan_directory(self):
        root = self.directory.get().strip()
        if not root:
            messagebox.showwarning("Внимание", "Сначала укажите директорию.")
            return
        if not os.path.isdir(root):
            messagebox.showerror("Ошибка", f"'{root}' не является директорией.")
            return

        self.items = []
        self.current_index = None
        self.sort_column = None
        self.sort_reverse = False
        self.filter_conflicts_only.set(False)
        self.filter_by_dir.set(False)
        self.current_filter_dir = ""
        self.label_current_dir_filter.config(text="Фильтр по поддиректории: (нет)")

        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = os.path.relpath(dirpath, root)
            if rel_dir == ".":
                rel_dir = ""

            # ПОДДИРЕКТОРИИ
            for dname in dirnames:
                if has_cyrillic(dname):
                    new_name = dname
                else:
                    new_name = translit_to_cyrillic(dname)

                self.items.append({
                    "rel_dir": rel_dir,
                    "old_name": dname,
                    "new_name": new_name,
                    "do_rename": new_name != dname,
                    "is_dir": True,
                    "locked": False,
                    "modified": False,
                })

            # ФАЙЛЫ
            for fname in filenames:
                base, ext = os.path.splitext(fname)
                if has_cyrillic(fname):
                    new_name = fname
                else:
                    new_base = translit_to_cyrillic(base)
                    new_name = new_base + ext

                self.items.append({
                    "rel_dir": rel_dir,
                    "old_name": fname,
                    "new_name": new_name,
                    "do_rename": new_name != fname,
                    "is_dir": False,
                    "locked": False,
                    "modified": False,
                })

        self.refresh_tree(keep_position=False)
        self.log(f"Сканирование завершено. Найдено элементов: {len(self.items)}")

    def on_filter_change(self):
        if self.filter_by_dir.get():
            if not self.current_filter_dir:
                if self.current_index is not None and 0 <= self.current_index < len(self.items):
                    self.current_filter_dir = self.items[self.current_index]["rel_dir"]
            text = self.current_filter_dir if self.current_filter_dir else "(корень)"
        else:
            text = "(нет)"
        self.label_current_dir_filter.config(text=f"Фильтр по поддиректории: {text}")

        self.refresh_tree(keep_position=True)

    def on_column_click(self, col):
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False
        self.refresh_tree(keep_position=True)

    def _compute_conflicts(self):
        """Заполняет self.conflict_indices на основе self.items."""
        self.conflict_indices = set()
        root = self.directory.get().strip()

        # внутренние конфликты
        mapping = {}
        for idx, info in enumerate(self.items):
            if not info["do_rename"]:
                continue
            if info["old_name"] == info["new_name"]:
                continue
            key = (info["rel_dir"], info["new_name"])
            mapping.setdefault(key, []).append(idx)

        for indices in mapping.values():
            if len(indices) > 1:
                self.conflict_indices.update(indices)

        # внешние конфликты
        if root and os.path.isdir(root):
            for idx, info in enumerate(self.items):
                if not info["do_rename"]:
                    continue
                if info["old_name"] == info["new_name"]:
                    continue

                parent_dir = os.path.join(root, info["rel_dir"]) if info["rel_dir"] else root
                src = os.path.join(parent_dir, info["old_name"])
                dst = os.path.join(parent_dir, info["new_name"])

                if os.path.exists(dst) and os.path.abspath(dst) != os.path.abspath(src):
                    self.conflict_indices.add(idx)

    def _sort_indices(self, indices):
        """Сортировка списка индексов по текущей сортировке."""
        def key_func(idx):
            info = self.items[idx]

            if self.sort_column == "type":
                return (0 if info["is_dir"] else 1, info["rel_dir"], info["old_name"].lower())
            if self.sort_column == "exc":
                # Исключён = do_rename False -> [X]
                return (0 if not info["do_rename"] else 1, info["rel_dir"], info["old_name"].lower())
            if self.sort_column == "lock":
                return (0 if info["locked"] else 1, info["rel_dir"], info["old_name"].lower())
            if self.sort_column == "conf":
                return (0 if idx in self.conflict_indices else 1, info["rel_dir"], info["old_name"].lower())
            if self.sort_column == "mod":
                return (0 if info.get("modified", False) else 1, info["rel_dir"], info["old_name"].lower())
            if self.sort_column == "path":
                rel_path = os.path.join(info["rel_dir"], info["old_name"]) if info["rel_dir"] else info["old_name"]
                return rel_path.lower()
            if self.sort_column == "new":
                return info["new_name"].lower()

            # сортировка по умолчанию: по пути
            rel_path = os.path.join(info["rel_dir"], info["old_name"]) if info["rel_dir"] else info["old_name"]
            return rel_path.lower()

        indices.sort(key=key_func, reverse=self.sort_reverse)

    def refresh_tree(self, keep_position=True):
        """Перестраивает дерево с учётом фильтров, конфликтов и сортировки."""
        # Запоминаем позицию и выбор
        if keep_position:
            yview = self.tree.yview()
            selected = self.tree.selection()
        else:
            yview = (0.0, 1.0)
            selected = ()

        for child in self.tree.get_children():
            self.tree.delete(child)

        self._compute_conflicts()

        indices = list(range(len(self.items)))

        # фильтры
        filtered = []
        for idx in indices:
            info = self.items[idx]

            if self.filter_conflicts_only.get() and idx not in self.conflict_indices:
                continue

            if self.filter_by_dir.get():
                if info["rel_dir"] != self.current_filter_dir:
                    continue

            filtered.append(idx)

        self._sort_indices(filtered)

        # вставка строк
        for idx in filtered:
            info = self.items[idx]
            is_conf = idx in self.conflict_indices

            type_str = "DIR" if info["is_dir"] else "FILE"
            exc_str = "X" if not info["do_rename"] else ""
            lock_str = "L" if info["locked"] else ""
            conf_str = "!" if is_conf and info["do_rename"] else ""
            mod_str = "M" if info.get("modified", False) else ""

            rel_path = os.path.join(info["rel_dir"], info["old_name"]) if info["rel_dir"] else info["old_name"]

            values = (type_str, exc_str, lock_str, conf_str, mod_str, rel_path, info["new_name"])

            iid = str(idx)
            self.tree.insert("", "end", iid=iid, values=values)

            if is_conf and info["do_rename"]:
                self.tree.tag_configure("conflict", foreground="red")
                self.tree.item(iid, tags=("conflict",))

        # восстановление выбора и позиции
        if keep_position:
            existing_iids = set(self.tree.get_children())
            # выбор
            for s in selected:
                if s in existing_iids:
                    self.tree.selection_set(s)
                    self.tree.focus(s)
                    break
            # позиция
            self.tree.yview_moveto(yview[0])

    def on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        try:
            idx = int(iid)
        except ValueError:
            return

        if not (0 <= idx < len(self.items)):
            return

        self.current_index = idx
        info = self.items[idx]

        rel_path = os.path.join(info["rel_dir"], info["old_name"]) if info["rel_dir"] else info["old_name"]
        self.label_current.config(text=rel_path)
        self.new_name_var.set(info["new_name"])
        self.do_rename_var.set(info["do_rename"])
        self.locked_var.set(info["locked"])
        self.label_type.config(text=f"Тип: {'папка' if info['is_dir'] else 'файл'}")

        if self.filter_by_dir.get():
            self.current_filter_dir = info["rel_dir"]
            text = self.current_filter_dir if self.current_filter_dir else "(корень)"
            self.label_current_dir_filter.config(text=f"Фильтр по поддиректории: {text}")
            self.refresh_tree(keep_position=True)

    def apply_changes_to_selected(self):
        idx = self.current_index
        if idx is None or not (0 <= idx < len(self.items)):
            messagebox.showinfo("Информация", "Сначала выберите элемент в списке.")
            return

        info = self.items[idx]
        new_name = self.new_name_var.get().strip()
        if not new_name:
            messagebox.showwarning("Внимание", "Новое имя не может быть пустым.")
            return

        info["new_name"] = new_name
        info["do_rename"] = self.do_rename_var.get()
        info["locked"] = self.locked_var.get()

        # пометка [M]: кириллическое исходное имя и новое имя отличное от старого
        if has_cyrillic(info["old_name"]) and info["new_name"] != info["old_name"]:
            info["modified"] = True
        else:
            info["modified"] = False

        self.refresh_tree(keep_position=True)

        rel_path = os.path.join(info["rel_dir"], info["old_name"]) if info["rel_dir"] else info["old_name"]
        self.log(
            f"Обновлено: {rel_path} → {info['new_name']} "
            f"(переименовывать: {info['do_rename']}, зафиксировано: {info['locked']}, изменён: {info['modified']})"
        )

    def toggle_lock_for_selected(self):
        idx = self.current_index
        if idx is None or not (0 <= idx < len(self.items)):
            return
        info = self.items[idx]
        info["locked"] = self.locked_var.get()
        self.refresh_tree(keep_position=True)

    def auto_resolve_conflicts(self):
        if not self.conflict_indices:
            messagebox.showinfo("Информация", "Конфликтов не обнаружено.")
            return

        root = self.directory.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showwarning("Внимание", "Нет корректной корневой директории.")
            return

        changed = 0

        def occupied_names(rel_dir):
            names = set()
            for info in self.items:
                if info["rel_dir"] == rel_dir:
                    names.add(info["new_name"])
            return names

        for idx in sorted(self.conflict_indices):
            info = self.items[idx]
            if not info["do_rename"]:
                continue
            if info["locked"]:
                continue

            parent_rel = info["rel_dir"]
            base, ext = os.path.splitext(info["new_name"])
            used = occupied_names(parent_rel)

            candidate = info["new_name"]
            n = 1
            while True:
                if candidate not in used:
                    parent_dir = os.path.join(root, parent_rel) if parent_rel else root
                    dst = os.path.join(parent_dir, candidate)
                    if not os.path.exists(dst):
                        break
                candidate = f"{base}_{n}{ext}"
                n += 1

            if candidate != info["new_name"]:
                self.log(f"Авто-правка: {info['new_name']} → {candidate}")
                info["new_name"] = candidate
                # флаг modified не трогаем — [M] остаётся только за ручными изменениями
                changed += 1

        self.refresh_tree(keep_position=True)
        messagebox.showinfo("Готово", f"Автоматически скорректировано имён: {changed}")

    def rename_items(self):
        root = self.directory.get().strip()
        if not root:
            messagebox.showwarning("Внимание", "Сначала укажите директорию и выполните сканирование.")
            return

        if not self.items:
            messagebox.showinfo("Информация", "Список пуст. Сначала выполните сканирование.")
            return

        if self.conflict_indices:
            if not messagebox.askyesno(
                "Предупреждение",
                "Некоторые элементы всё ещё в конфликте ([!]). Продолжить переименование?\n"
                "Конфликтующие элементы будут пропущены."
            ):
                return

        if not messagebox.askyesno("Подтверждение", "Переименовать все отмеченные элементы?"):
            return

        renamed_count = 0
        errors_count = 0

        file_indices = [i for i, it in enumerate(self.items) if not it["is_dir"]]
        dir_indices = [i for i, it in enumerate(self.items) if it["is_dir"]]

        def depth_of_item(info):
            rel = os.path.join(info["rel_dir"], info["old_name"]) if info["rel_dir"] else info["old_name"]
            return rel.count(os.sep)

        dir_indices.sort(key=lambda idx: depth_of_item(self.items[idx]), reverse=True)

        def process_index(idx):
            nonlocal renamed_count, errors_count
            info = self.items[idx]

            if not info["do_rename"]:
                return
            if idx in self.conflict_indices:
                self.log(f"Пропуск (конфликт): {info['old_name']} в {info['rel_dir']}")
                errors_count += 1
                return
            if info["old_name"] == info["new_name"]:
                return

            parent_dir = os.path.join(root, info["rel_dir"]) if info["rel_dir"] else root
            src = os.path.join(parent_dir, info["old_name"])
            dst = os.path.join(parent_dir, info["new_name"])

            if not os.path.exists(src):
                self.log(f"Пропуск (не найден): {src}")
                errors_count += 1
                return

            if os.path.exists(dst):
                self.log(f"Ошибка: целевой путь уже существует: {dst}")
                errors_count += 1
                return

            try:
                os.rename(src, dst)
                self.log(f"OK: {src} → {dst}")
                renamed_count += 1
            except Exception as e:
                self.log(f"Ошибка при переименовании {src}: {e}")
                errors_count += 1

        for idx in file_indices:
            process_index(idx)
        for idx in dir_indices:
            process_index(idx)

        self.refresh_tree(keep_position=True)
        messagebox.showinfo("Готово", f"Переименовано: {renamed_count}\nОшибок/пропусков: {errors_count}")

    def save_session(self):
        if not self.items:
            messagebox.showinfo("Информация", "Нечего сохранять — список элементов пуст.")
            return

        path = filedialog.asksaveasfilename(
            title="Сохранить сессию",
            defaultextension=".json",
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")]
        )
        if not path:
            return

        data = {
            "root": self.directory.get(),
            "items": self.items,
        }

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.log(f"Сессия сохранена в {path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить сессию: {e}")

    def load_session(self):
        path = filedialog.askopenfilename(
            title="Загрузить сессию",
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")]
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить сессию: {e}")
            return

        root = data.get("root", "")
        items = data.get("items", [])

        if not isinstance(items, list):
            messagebox.showerror("Ошибка", "Формат файла сессии некорректен.")
            return

        # нормализация полей
        norm_items = []
        for it in items:
            norm_items.append({
                "rel_dir": it.get("rel_dir", ""),
                "old_name": it.get("old_name", ""),
                "new_name": it.get("new_name", it.get("old_name", "")),
                "do_rename": bool(it.get("do_rename", False)),
                "is_dir": bool(it.get("is_dir", False)),
                "locked": bool(it.get("locked", False)),
                "modified": bool(it.get("modified", False)),
            })

        self.directory.set(root)
        self.items = norm_items
        self.current_index = None
        self.sort_column = None
        self.sort_reverse = False
        self.filter_conflicts_only.set(False)
        self.filter_by_dir.set(False)
        self.current_filter_dir = ""
        self.label_current_dir_filter.config(text="Фильтр по поддиректории: (нет)")

        self.refresh_tree(keep_position=False)
        self.log(f"Сессия загружена из {path}")

    def log(self, msg: str):
        self.text_log.config(state="normal")
        self.text_log.insert(tk.END, msg + "\n")
        self.text_log.see(tk.END)
        self.text_log.config(state="disabled")


if __name__ == "__main__":
    app = RenameToolApp()
    app.mainloop()
