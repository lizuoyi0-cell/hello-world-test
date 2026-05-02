"""Tiny built-in translation layer (English + Spanish).

Translations live inline so the package has no runtime dependencies on
locale files. Use :func:`set_language` to switch and :func:`t` to look up
a key. Missing keys fall through to the key itself.
"""

from __future__ import annotations

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": "Welcome to Taskman",
        "menu.main": "Main Menu",
        "menu.login": "Login",
        "menu.register": "Register",
        "menu.logout": "Logout",
        "menu.boards": "Boards",
        "menu.profile": "Profile",
        "menu.search": "Search",
        "menu.reports": "Reports",
        "menu.exit": "Exit",
        "menu.help": "Help",
        "prompt.choice": "Choose an option",
        "prompt.username": "Username",
        "prompt.password": "Password",
        "prompt.email": "Email",
        "msg.bye": "Goodbye!",
        "msg.invalid": "Invalid choice",
        "msg.login_ok": "Logged in",
        "msg.login_fail": "Login failed",
    },
    "es": {
        "welcome": "Bienvenido a Taskman",
        "menu.main": "Menu Principal",
        "menu.login": "Iniciar sesion",
        "menu.register": "Registrarse",
        "menu.logout": "Cerrar sesion",
        "menu.boards": "Tableros",
        "menu.profile": "Perfil",
        "menu.search": "Buscar",
        "menu.reports": "Informes",
        "menu.exit": "Salir",
        "menu.help": "Ayuda",
        "prompt.choice": "Elija una opcion",
        "prompt.username": "Usuario",
        "prompt.password": "Contrasena",
        "prompt.email": "Correo",
        "msg.bye": "Adios!",
        "msg.invalid": "Opcion invalida",
        "msg.login_ok": "Sesion iniciada",
        "msg.login_fail": "Fallo al iniciar sesion",
    },
}

_current = "en"


def set_language(lang: str) -> None:
    global _current
    if lang not in TRANSLATIONS:
        raise ValueError(f"unsupported language: {lang}")
    _current = lang


def get_language() -> str:
    return _current


def t(key: str) -> str:
    return TRANSLATIONS.get(_current, {}).get(key, key)
