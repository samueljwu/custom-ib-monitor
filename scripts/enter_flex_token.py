"""One-time local entry of an IBKR Flex token into Windows Credential Manager."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from app.secret_store import save_flex_token


def main() -> None:
    root = tk.Tk()
    root.title("Custom IB Monitor — Flex token")
    root.geometry("460x230")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    tk.Label(root, text="Enter the same IBKR account ID used in Settings.",
             wraplength=420).pack(padx=16, pady=(18, 6))
    account = tk.Entry(root, width=45)
    account.pack(padx=16, pady=4)
    account.focus_set()
    tk.Label(root, text="Paste the Flex token from IBKR Client Portal.",
             wraplength=420).pack(padx=16, pady=(10, 4))
    token = tk.Entry(root, show="•", width=45)
    token.pack(padx=16, pady=4)

    def save() -> None:
        try:
            save_flex_token(account.get().strip(), token.get().strip())
        except Exception as exc:
            messagebox.showerror("Token was not saved", str(exc), parent=root)
            return
        token.delete(0, tk.END)
        messagebox.showinfo("Saved", "Token saved in Windows Credential Manager.", parent=root)
        root.destroy()

    tk.Button(root, text="Save token", command=save).pack(pady=12)
    root.bind("<Return>", lambda _event: save())
    root.mainloop()


if __name__ == "__main__":
    main()
