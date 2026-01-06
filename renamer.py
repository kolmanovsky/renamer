import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ==== НАСТРОЙКИ ТРАНСЛИТА (можно править руками) ===========================

# Попробуем загрузить настройки из JSON (опционально).
# Например, translit_config.json:
# {
#   "mapping_multi": [["shch", "щ"], ["yo", "ё"]],
#   "mapping_single": {"a": "а", "b": "б", "'": "ь"}
# }
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
    "y": "ы",
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

    # апостроф = мягкий знак
    "'": "ь",
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
            # Если конфиг битый — просто игнорируем и работаем с дефолтами
            pass

    return mapping_multi, mapping_single


MAPPING_MULTI, MAPPING_SINGLE = load_translit_config()


def translit_to_cyrillic(text: str) -> str:
    """
    Перевод простого транслита → кириллицу,
    с сохранением регистра и поддержкой апострофа (мягкий знак).
    """

    def apply_case(src: str, dst: str) -> str:
        """
        Применяем капителизацию исходного латинского фрагмента к кириллице:

        PRIVET -> ПРИВЕТ
        Privet -> Привет
        privet -> привет
        pRivet -> пРивет (как есть)
        """
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

        # Не латиница и не апостроф — копируем как есть
        if not ("a" <= ch_lower <= "z" or ch_lower == "'"):
            result.append(ch)
            i += 1
            continue

        replaced = False

        # МНОГОбуквенные сочетания
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

        # ОДНОбуквенные (включая апостроф)
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
        self.geometry("1050x700")

        self.directory = tk.StringVar()
        # items: список словарей:
        # {
        #   "rel_dir": str,   # относительный путь до родителя
        #   "old_name": str,
        #   "new_name": str,
        #   "do_rename": bool,
        #   "is_dir": bool,
        #   "locked": bool,   # вручную зафиксированное имя
        # }
        self.items = []

        # набор индексов с конфликтами (обновляется при refresh_listbox_with_conflicts)
        self.conflict_indices = set()

        self.create_widgets()

    # ---------- UI ----------

    def create_widgets(self):
        # Верхняя панель: выбор директории
        frame_top = ttk.Frame(self)
        frame_top.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(frame_top, text="Директория:").pack(side=tk.LEFT)

        entry_dir = ttk.Entry(frame_top, textvariable=self.directory, width=70)
        entry_dir.pack(side=tk.LEFT, padx=(5, 5))

        btn_browse = ttk.Button(frame_top, text="Обзор...", command=self.browse_directory)
        btn_browse.pack(side=tk.LEFT)

        btn_scan = ttk.Button(frame_top, text="Сканировать", command=self.scan_directory)
        btn_scan.pack(side=tk.LEFT, padx=(10, 0))

        # Легенда
        frame_legend = ttk.Frame(self)
        frame_legend.pack(fill=tk.X, padx=10, pady=(0, 5))

        ttk.Label(
            frame_legend,
            text=(
                "[DIR] — папка, [FILE] — файл, "
                "[X] — не переименовывать, "
                "[L] — имя зафиксировано, "
                "[!] — конфликт имен"
            ),
            foreground="gray"
        ).pack(anchor="w")

        # Центральная часть: список + панель редактирования
        frame_center = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        frame_center.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        # Список
        frame_list = ttk.Frame(frame_center)
        frame_center.add(frame_list, weight=3)

        ttk.Label(frame_list, text="Элементы (старое имя → новое имя):").pack(anchor="w")

        self.listbox = tk.Listbox(frame_list, selectmode=tk.SINGLE)
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=(5, 5))
        self.listbox.bind("<<ListboxSelect>>", self.on_listbox_select)

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

        btn_apply = ttk.Button(frame_edit, text="Сохранить изменения для элемента", command=self.apply_changes_to_selected)
        btn_apply.pack(anchor="w", pady=(10, 5))

        btn_auto_fix = ttk.Button(
            frame_edit,
            text="Авто-решение конфликтов (для незафиксированных)",
            command=self.auto_resolve_conflicts
        )
        btn_auto_fix.pack(anchor="w", pady=(5, 5))

        # Нижняя часть: кнопка "Переименовать" + лог
        frame_bottom = ttk.Frame(self)
        frame_bottom.pack(fill=tk.BOTH, expand=False, padx=10, pady=(0, 10))

        btn_rename = ttk.Button(frame_bottom, text="Переименовать все отмеченные файлы и папки", command=self.rename_items)
        btn_rename.pack(anchor="w", pady=(0, 5))

        ttk.Label(frame_bottom, text="Лог:").pack(anchor="w")
        self.text_log = tk.Text(frame_bottom, height=8, state="disabled")
        self.text_log.pack(fill=tk.BOTH, expand=True)

    # ---------- Обработчики и логика ----------

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
        self.listbox.delete(0, tk.END)

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

                item = {
                    "rel_dir": rel_dir,
                    "old_name": dname,
                    "new_name": new_name,
                    "do_rename": new_name != dname,
                    "is_dir": True,
                    "locked": False,
                }
                self.items.append(item)

            # ФАЙЛЫ
            for fname in filenames:
                base, ext = os.path.splitext(fname)
                if has_cyrillic(fname):
                    new_name = fname
                else:
                    new_base = translit_to_cyrillic(base)
                    new_name = new_base + ext

                item = {
                    "rel_dir": rel_dir,
                    "old_name": fname,
                    "new_name": new_name,
                    "do_rename": new_name != fname,
                    "is_dir": False,
                    "locked": False,
                }
                self.items.append(item)

        self.refresh_listbox_with_conflicts()
        self.log(f"Сканирование завершено. Найдено элементов: {len(self.items)}")

    def refresh_listbox_with_conflicts(self):
        """
        Перестраивает listbox и помечает строки с конфликтами:
        - внутренние конфликты (два элемента в одном родителе с одинаковым new_name);
        - внешние конфликты (на диске уже существует элемент с таким именем).
        """
        self.listbox.delete(0, tk.END)
        self.conflict_indices = set()

        root = self.directory.get().strip()

        # 1. Внутренние конфликты: (rel_dir, new_name) → несколько элементов
        mapping = {}
        for idx, info in enumerate(self.items):
            if not info["do_rename"]:
                continue
            if info["old_name"] == info["new_name"]:
                continue
            key = (info["rel_dir"], info["new_name"])
            mapping.setdefault(key, []).append(idx)

        for key, indices in mapping.items():
            if len(indices) > 1:
                self.conflict_indices.update(indices)

        # 2. Внешние конфликты: уже существует файл/папка с таким именем
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

        # 3. Заполняем listbox, отмечаем тип/флаги/конфликты
        for idx, info in enumerate(self.items):
            rel_path = os.path.join(info["rel_dir"], info["old_name"]) if info["rel_dir"] else info["old_name"]

            tags = []
            tags.append("[DIR]" if info["is_dir"] else "[FILE]")
            if not info["do_rename"]:
                tags.append("[X]")
            if info["locked"]:
                tags.append("[L]")
            if idx in self.conflict_indices and info["do_rename"]:
                tags.append("[!]")

            prefix = " ".join(tags)
            display = f"{prefix} {rel_path}  →  {info['new_name']}"
            self.listbox.insert(tk.END, display)

            if idx in self.conflict_indices and info["do_rename"]:
                try:
                    self.listbox.itemconfig(idx, foreground="red")
                except Exception:
                    pass

    def on_listbox_select(self, event):
        selection = self.listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        info = self.items[idx]

        rel_path = os.path.join(info["rel_dir"], info["old_name"]) if info["rel_dir"] else info["old_name"]
        self.label_current.config(text=rel_path)
        self.new_name_var.set(info["new_name"])
        self.do_rename_var.set(info["do_rename"])
        self.locked_var.set(info["locked"])
        self.label_type.config(text=f"Тип: {'папка' if info['is_dir'] else 'файл'}")

    def apply_changes_to_selected(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo("Информация", "Сначала выберите элемент в списке.")
            return
        idx = selection[0]
        info = self.items[idx]

        new_name = self.new_name_var.get().strip()
        if not new_name:
            messagebox.showwarning("Внимание", "Новое имя не может быть пустым.")
            return

        info["new_name"] = new_name
        info["do_rename"] = self.do_rename_var.get()
        info["locked"] = self.locked_var.get()

        self.refresh_listbox_with_conflicts()

        rel_path = os.path.join(info["rel_dir"], info["old_name"]) if info["rel_dir"] else info["old_name"]
        self.log(f"Обновлено: {rel_path} → {info['new_name']} "
                 f"(переименовывать: {info['do_rename']}, зафиксировано: {info['locked']})")

    def toggle_lock_for_selected(self):
        """Вызывается при клике по чекбоксу 'Зафиксировать имя'."""
        selection = self.listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        info = self.items[idx]
        info["locked"] = self.locked_var.get()
        self.refresh_listbox_with_conflicts()

    def auto_resolve_conflicts(self):
        """
        Автоматически решаем конфликты только для НЕ зафиксированных элементов:
        добавляем суффиксы _1, _2, ...
        """
        if not self.conflict_indices:
            messagebox.showinfo("Информация", "Конфликтов не обнаружено.")
            return

        root = self.directory.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showwarning("Внимание", "Нет корректной корневой директории.")
            return

        changed = 0

        # Для удобства: строим множество занятых имён в каждой папке
        # на основании текущих new_name (включая те, что не переименовываются)
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
                # зафиксированное имя не трогаем
                continue

            parent_rel = info["rel_dir"]
            parent_dir = os.path.join(root, parent_rel) if parent_rel else root

            base, ext = os.path.splitext(info["new_name"])
            used = occupied_names(parent_rel)

            candidate = info["new_name"]
            n = 1
            while True:
                if candidate not in used:
                    dst = os.path.join(parent_dir, candidate)
                    # не должен существовать на диске (если уже существует другой файл/папка)
                    if not os.path.exists(dst):
                        break
                candidate = f"{base}_{n}{ext}"
                n += 1

            if candidate != info["new_name"]:
                self.log(f"Авто-правка: {info['new_name']} → {candidate}")
                info["new_name"] = candidate
                changed += 1

        self.refresh_listbox_with_conflicts()
        messagebox.showinfo("Готово", f"Автоматически скорректировано имён: {changed}")

    def rename_items(self):
        root = self.directory.get().strip()
        if not root:
            messagebox.showwarning("Внимание", "Сначала укажите директорию и выполните сканирование.")
            return

        if not self.items:
            messagebox.showinfo("Информация", "Список пуст. Сначала выполните сканирование.")
            return

        # Проверим, остались ли конфликты
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

        # Сначала файлы, потом папки (папки — от самых глубоких к верхним)
        file_indices = [i for i, it in enumerate(self.items) if not it["is_dir"]]
        dir_indices = [i for i, it in enumerate(self.items) if it["is_dir"]]

        def depth_of_item(info):
            # глубина по старому пути (до переименования)
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
                # На всякий случай ещё одна защита
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

        self.refresh_listbox_with_conflicts()
        messagebox.showinfo("Готово", f"Переименовано: {renamed_count}\nОшибок/пропусков: {errors_count}")

    def log(self, msg: str):
        self.text_log.config(state="normal")
        self.text_log.insert(tk.END, msg + "\n")
        self.text_log.see(tk.END)
        self.text_log.config(state="disabled")


if __name__ == "__main__":
    app = RenameToolApp()
    app.mainloop()
