from __future__ import annotations

from flask import Flask, render_template


def register(app: Flask) -> None:
    @app.get("/help/")
    def help():
        return render_template("help.html")
