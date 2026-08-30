import threading

import customtkinter as ctk

from edesk_bridge import detect_ecom_number, detect_order_number, open_tracking_page
from netsuite_bridge import (
    open_ecom_record,
    open_return_auths,
    open_sales_orders,
    open_sales_orders_with_ra,
)
from order_parser import parse_order_number

ctk.set_appearance_mode("dark")

FONT_HEADER = ("Segoe UI", 12, "bold")
FONT_BODY = ("Segoe UI", 10)
FONT_BUTTON = ("Segoe UI", 11, "bold")
FONT_STATUS = ("Segoe UI", 10)
FONT_SUBTITLE = ("Segoe UI", 10)

STATUS_STYLES = {
    "idle": dict(fg_color="#2a2d34", text_color="#9aa0aa"),
    "info": dict(fg_color="#1e3a5f", text_color="#8ecbff"),
    "success": dict(fg_color="#1e4620", text_color="#8ee6a0"),
    "error": dict(fg_color="#4a1f24", text_color="#ff9aa2"),
}

# Selected up front, then all run in one go when "Open Selected" is clicked —
# no more waiting for one action to finish before queuing the next.
# Rendered as a 2x2 grid of big toggle tiles (easier to hit than checkboxes).
CHECKBOX_ITEMS = [
    dict(key="so", text="Sales Order", fg_color="#2f6fed", hover_color="#2558c4"),
    dict(key="ra", text="Return Auth", fg_color="#0891b2", hover_color="#0e7490"),
    dict(key="tracking", text="Tracking", fg_color="#b45309", hover_color="#92400e"),
    dict(key="ecom", text="Ecom Record\n(Pre-Sales)", fg_color="#7c3aed", hover_color="#6d28d9"),
]
CHECKBOX_BY_KEY = {item["key"]: item for item in CHECKBOX_ITEMS}
DEFAULT_CHECKED = {"so"}


class CommandCenter:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("EDNIS")
        self.root.attributes("-topmost", True)
        self.root.geometry("320x470+40+40")
        self.root.minsize(300, 380)
        self.root.resizable(True, True)
        self.root.configure(fg_color="#1a1c22")

        self._wrap_labels = []
        self.buttons = {}
        self.checkboxes = {}
        self.checkbox_widgets = {}

        self.scroll = ctk.CTkScrollableFrame(self.root, fg_color="#1a1c22")
        self.scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(
            self.scroll,
            text="eDesk & NetSuite by loredans",
            font=FONT_HEADER,
            text_color="#e8eaed",
        ).pack(anchor="w", padx=10, pady=(10, 1))

        subtitle = ctk.CTkLabel(
            self.scroll,
            text="Ticket open in the automation Chrome window? Tap what to open.",
            font=FONT_BODY,
            text_color="#7b8291",
            wraplength=260,
            justify="left",
        )
        subtitle.pack(anchor="w", padx=10, pady=(0, 8), fill="x")
        self._wrap_labels.append(subtitle)

        self.grid_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.grid_frame.pack(fill="x", padx=8, pady=(0, 4))
        self.grid_frame.grid_columnconfigure((0, 1), weight=1, uniform="tiles")

        for i, item in enumerate(CHECKBOX_ITEMS):
            key = item["key"]
            var = ctk.BooleanVar(value=key in DEFAULT_CHECKED)
            tile = ctk.CTkButton(
                self.grid_frame,
                text=item["text"],
                font=FONT_BUTTON,
                height=62,
                corner_radius=10,
                border_width=2,
                border_color=item["fg_color"],
                command=lambda k=key: self.toggle_tile(k),
            )
            tile.grid(row=i // 2, column=i % 2, padx=4, pady=4, sticky="nsew")
            self.checkboxes[key] = var
            self.checkbox_widgets[key] = tile
            self._style_tile(key)

        self.open_btn = ctk.CTkButton(
            self.scroll,
            text="Open Selected",
            font=FONT_BUTTON,
            height=36,
            corner_radius=8,
            fg_color="#16a34a",
            hover_color="#15803d",
            command=self.on_open,
        )
        self.open_btn.pack(fill="x", padx=10, pady=(6, 10))
        self.buttons["open"] = self.open_btn

        self.status_frame = ctk.CTkFrame(self.scroll, corner_radius=8, fg_color=STATUS_STYLES["idle"]["fg_color"])
        self.status_frame.pack(fill="x", padx=10, pady=(0, 8))

        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Ready.",
            font=FONT_STATUS,
            text_color=STATUS_STYLES["idle"]["text_color"],
            wraplength=260,
            justify="left",
            anchor="w",
        )
        self.status_label.pack(fill="x", padx=8, pady=6)
        self._wrap_labels.append(self.status_label)

        divider = ctk.CTkFrame(self.scroll, height=1, fg_color="#31343c")
        divider.pack(fill="x", padx=10, pady=(0, 6))

        ctk.CTkLabel(
            self.scroll,
            text="No order number found? Enter it manually (Sales Order / RA only):",
            font=FONT_BODY,
            text_color="#c3c7cf",
            wraplength=260,
            justify="left",
        ).pack(anchor="w", padx=10)

        self.entry = ctk.CTkEntry(
            self.scroll,
            height=30,
            corner_radius=6,
            font=("Segoe UI", 12),
            fg_color="#0f1115",
            border_width=2,
            border_color="#5b6274",
            text_color="#ffffff",
            placeholder_text="e.g. #220461",
        )
        self.entry.pack(fill="x", padx=10, pady=(4, 6))
        self.entry.bind("<Return>", lambda e: self.on_manual())

        self.manual_btn = ctk.CTkButton(
            self.scroll,
            text="Search This Number (Enter)",
            font=FONT_BUTTON,
            height=32,
            corner_radius=8,
            fg_color="#059669",
            hover_color="#047857",
            command=self.on_manual,
        )
        self.manual_btn.pack(fill="x", padx=10, pady=(0, 10))
        self.buttons["manual"] = self.manual_btn

        self.root.bind("<Control-Return>", lambda e: self.on_manual())
        self.root.bind("<Configure>", self.on_resize)

    def on_resize(self, event):
        if event.widget is not self.root:
            return
        wrap = max(140, event.width - 40)
        for label in self._wrap_labels:
            label.configure(wraplength=wrap)

    # --- Toggle tiles (2x2 grid, big hitboxes) -------------------------------

    def toggle_tile(self, key):
        var = self.checkboxes[key]
        var.set(not var.get())
        self._style_tile(key)

    def _style_tile(self, key):
        """Filled in its accent color when selected, hollow outline when not."""
        item = CHECKBOX_BY_KEY[key]
        tile = self.checkbox_widgets[key]
        if self.checkboxes[key].get():
            tile.configure(
                fg_color=item["fg_color"],
                hover_color=item["hover_color"],
                text_color="#ffffff",
            )
        else:
            tile.configure(
                fg_color="transparent",
                hover_color=item["fg_color"],
                text_color="#e8eaed",
            )

    # --- Status / control helpers ---------------------------------------------

    def set_status(self, text, state="info"):
        style = STATUS_STYLES[state]

        def apply():
            self.status_frame.configure(fg_color=style["fg_color"])
            self.status_label.configure(text=text, text_color=style["text_color"])

        self.root.after(0, apply)

    def set_controls_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for btn in self.buttons.values():
            self.root.after(0, lambda b=btn: b.configure(state=state))
        for key, cb in self.checkbox_widgets.items():
            self.root.after(0, lambda c=cb: c.configure(state=state))
            if enabled:
                self.root.after(0, lambda k=key: self._style_tile(k))

    def ask_pick_ticket(self, labels):
        """Called from a background thread when more than one eDesk ticket
        tab is open. Blocks until the user picks one in a popup on the main
        thread. Returns the chosen index, or None if they closed it without
        picking."""
        result = {"index": None}
        done = threading.Event()

        def show_dialog():
            dialog = ctk.CTkToplevel(self.root)
            dialog.title("Which ticket?")
            dialog.attributes("-topmost", True)

            width = 320
            height = 80 + 36 * len(labels)
            x = self.root.winfo_x() + self.root.winfo_width() + 10
            y = self.root.winfo_y()
            dialog.geometry(f"{width}x{height}+{x}+{y}")

            dialog.configure(fg_color="#1a1c22")
            dialog.grab_set()

            ctk.CTkLabel(
                dialog,
                text="Multiple tickets are open. Use which one?",
                font=FONT_BODY,
                text_color="#c3c7cf",
                wraplength=280,
                justify="left",
            ).pack(anchor="w", padx=12, pady=(12, 8))

            def choose(i):
                result["index"] = i
                done.set()
                dialog.destroy()

            for i, label in enumerate(labels):
                ctk.CTkButton(
                    dialog,
                    text=label[:60],
                    font=FONT_BODY,
                    height=30,
                    corner_radius=8,
                    fg_color="#2f6fed",
                    hover_color="#2558c4",
                    command=lambda i=i: choose(i),
                ).pack(fill="x", padx=12, pady=3)

            def on_close():
                done.set()
                dialog.destroy()

            dialog.protocol("WM_DELETE_WINDOW", on_close)

        self.root.after(0, show_dialog)
        done.wait()
        return result["index"]

    # --- Checkbox-driven "Open Selected" flow ----------------------------------

    def on_open(self):
        selected = {key: var.get() for key, var in self.checkboxes.items()}
        if not any(selected.values()):
            self.set_status("Check at least one thing to open first.", "error")
            return

        self.set_controls_enabled(False)
        threading.Thread(target=self._run_open, args=(selected,), daemon=True).start()

    def _run_open(self, selected):
        results = []
        try:
            if selected["so"] or selected["ra"]:
                results.append(self._open_order(selected["so"], selected["ra"]))

            if selected["tracking"]:
                results.append(self._open_tracking())

            if selected["ecom"]:
                results.append(self._open_ecom())

            self.set_status("Done — " + "; ".join(results), "success")
        except Exception as e:
            self.set_status(str(e), "error")
        finally:
            self.set_controls_enabled(True)

    def _open_order(self, want_so, want_ra):
        query = detect_order_number(
            log=lambda msg: self.set_status(msg, "info"), pick_page=self.ask_pick_ticket
        )
        if not query:
            return "no order number found"
        return self._open_order_records(query, want_so, want_ra)

    def _open_order_records(self, query, want_so, want_ra):
        """Opens exactly what's asked for: Sales Order, Return Authorization, or
        both. Returns a short summary string for the status bar."""
        logf = lambda msg: self.set_status(msg, "info")

        if want_so and want_ra:
            so_count, ra_count = open_sales_orders_with_ra(query, log=logf)
            so_noun = "sales order" if so_count == 1 else "sales orders"
            if ra_count == 0:
                return f"{so_count} {so_noun}, no RA tied"
            ra_noun = "RA" if ra_count == 1 else "RAs"
            return f"{so_count} {so_noun} + {ra_count} {ra_noun}"

        if want_ra:
            ra_count = open_return_auths(query, log=logf)
            if ra_count == 0:
                return "no RA tied to this order"
            return f"{ra_count} RA" if ra_count == 1 else f"{ra_count} RAs"

        count = open_sales_orders(query, log=logf)
        noun = "sales order" if count == 1 else "sales orders"
        return f"{count} {noun}"

    def _open_tracking(self):
        carrier, number = open_tracking_page(
            log=lambda msg: self.set_status(msg, "info"), pick_page=self.ask_pick_ticket
        )
        return f"{carrier} tracking" if number else "no tracking number found"

    def _open_ecom(self):
        number = detect_ecom_number(
            log=lambda msg: self.set_status(msg, "info"), pick_page=self.ask_pick_ticket
        )
        if not number:
            return "no ecom record number found"
        open_ecom_record(number, log=lambda msg: self.set_status(msg, "info"))
        return "ecom record + parent"

    # --- Manual fallback (Sales Order / RA only) --------------------------------

    def on_manual(self):
        raw = self.entry.get().strip()
        if not raw:
            self.set_status("Paste an order number first.", "error")
            return

        query = parse_order_number(raw)
        if not query:
            self.set_status(f"Couldn't find an order number in: {raw[:60]}", "error")
            return

        want_so = self.checkboxes["so"].get()
        want_ra = self.checkboxes["ra"].get()
        # The manual box is Sales Order / RA only. If neither is ticked (e.g.
        # only Tracking is), fall back to Sales Order so the button still does
        # the obvious thing.
        if not want_so and not want_ra:
            want_so = True

        self.set_controls_enabled(False)
        self._search_netsuite(query, want_so, want_ra)

    # --- Shared NetSuite step -----------------------------------------------

    def _search_netsuite(self, query, want_so, want_ra):
        self.set_status(f"Searching NetSuite for {query}...", "info")
        threading.Thread(
            target=self._run_search, args=(query, want_so, want_ra), daemon=True
        ).start()

    def _run_search(self, query, want_so, want_ra):
        try:
            summary = self._open_order_records(query, want_so, want_ra)
            self.set_status(f"{query} — {summary}.", "success")
            self.root.after(0, lambda: self.entry.delete(0, "end"))
        except Exception as e:
            self.set_status(str(e), "error")
        finally:
            self.set_controls_enabled(True)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    CommandCenter().run()
