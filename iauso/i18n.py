"""Panel text, per language.

Only what the e-ink display shows is translated here. Log lines, CLI output
and exception messages are always English: they are diagnostics for whoever
runs the service, not part of the panel.

Pick the language with "language" in config.json ("en" by default). To add
one, copy a block below and translate the values; the keys must stay the same.
Window labels such as "5 h" or "7 d" are not here: they come from the provider
snapshot, so several displays in different languages can share one server.
"""

STRINGS = {
    "en": {
        "title": "AI QUOTA",
        "header": "PLAN USAGE",
        "demo": "DEMO",
        "footer_demo": "DEMO: fictional values",
        "footer_stale": "* Previous reading. R: reset",
        "footer": "Percentage used | Local time",
        "window_missing": "No data",
        "reset": "R: ",
        "reset_unknown": "R: no date",
        "reset_pending": "R: to confirm",
        "status": {
            "ok": "Data ",
            "stale": "OLD ",
            "needs_auth": "SIGN IN",
            "expired": "RENEW SESSION",
            "rate_limited": "WAIT / 429",
            "offline": "NO CONNECTION",
            "error": "QUERY FAILED",
            "no_data": "NO QUOTA REPORTED",
            "disabled": "DISABLED",
            "unknown": "NO DATA",
        },
    },
    "es": {
        "title": "CUOTAS IA",
        "header": "USO DEL PLAN",
        "demo": "DEMO",
        "footer_demo": "DEMO: valores ficticios",
        "footer_stale": "* Dato anterior. R: reinicio",
        "footer": "Porcentaje usado | Hora local",
        "window_missing": "Sin dato",
        "reset": "R: ",
        "reset_unknown": "R: sin fecha",
        "reset_pending": "R: por confirmar",
        "status": {
            "ok": "Dato ",
            "stale": "ANT. ",
            "needs_auth": "INICIAR SESION",
            "expired": "RENOVAR SESION",
            "rate_limited": "ESPERAR / 429",
            "offline": "SIN CONEXION",
            "error": "ERROR CONSULTA",
            "no_data": "SIN CUOTA INFORMADA",
            "disabled": "DESACTIVADO",
            "unknown": "SIN DATOS",
        },
    },
}

DEFAULT_LANGUAGE = "en"


def strings(language=DEFAULT_LANGUAGE):
    try:
        return STRINGS[language]
    except KeyError:
        raise ValueError("language must be one of: " + ", ".join(sorted(STRINGS))) from None
