# Fuentes y alcance técnico

Revisión: 7 de septiembre de 2026. Adaptación Python realizada para Raspberry Pi Zero 2 W + Waveshare 2.15inch e-Paper HAT+ (G).

## Codenotch

Repositorio: https://github.com/vinzdg/codenotch

Commit revisado: `743601acd69e701131602b88082fcaeee0c2e88b`.

- [ClaudeOAuthProvider.swift](https://github.com/vinzdg/codenotch/blob/743601acd69e701131602b88082fcaeee0c2e88b/Sources/Providers/ClaudeOAuthProvider.swift): endpoint OAuth de uso, cabecera beta, campos `limits`, `five_hour`, `seven_day` y combinación de formatos.
- [CodexLocalProvider.swift](https://github.com/vinzdg/codenotch/blob/743601acd69e701131602b88082fcaeee0c2e88b/Sources/Providers/CodexLocalProvider.swift): GET `https://chatgpt.com/backend-api/wham/usage` con sesión de Codex y `ChatGPT-Account-Id`.
- [CodexUsage.swift](https://github.com/vinzdg/codenotch/blob/743601acd69e701131602b88082fcaeee0c2e88b/Sources/Providers/CodexUsage.swift): ventanas principales, porcentajes, duración y reinicio absoluto o relativo. No se mezcla el contador de revisiones de código con las cuotas principales.
- `ClaudeCredentials.swift` y `CodexCredentials.swift`: lectura de sesiones sin modificar ni renovar credenciales.

La adaptación no ejecuta el código Swift ni replica la interfaz macOS. Implementa en Python las consultas y el significado de sus datos. Añade persistencia de intervalo, archivo receptor, validación, renderizado e-ink y pruebas.

## Waveshare

- [Producto: 2.15inch e-Paper HAT+ (G)](https://www.waveshare.com/2.15inch-e-paper-hat-plus-g.htm): 296 × 160; negro, blanco, amarillo y rojo; interfaz SPI; refresco completo aproximado de 20 segundos.
- [Manual](https://www.waveshare.com/wiki/2.15inch_e-Paper_HAT%2B_%28G%29_Manual).
- [Repositorio oficial e-Paper](https://github.com/waveshareteam/e-Paper).

Commit de los archivos incluidos: `a794fbc39656b0f93938d1ffb3fdc77eaed9e9fc`.

Se incluyen sin cambios `RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd2in15g.py` y `epdconfig.py`. La adaptación hereda `EPD` para agregar un límite de espera BUSY. No modifica registros, secuencias de inicialización ni formas de onda. `getbuffer()` del fabricante rota la imagen horizontal 296 × 160 a la orientación interna 160 × 296 y genera 11.840 bytes, a dos bits por píxel.

### Paneles adicionales (v1.2, sin probar en hardware fisico)

Commit de los archivos incluidos: `06e834491bf62023a1b86a481b4530978883d2c4` (mismo repositorio, `epdconfig.py` identico al commit anterior — verificado con `diff` byte a byte).

Se incluyen sin cambios `epd2in13_V4.py`, `epd2in13b_V4.py`, `epd2in9_V2.py`, `epd2in9b_V4.py`, `epd4in2_V2.py`, `epd7in5_V2.py` y `epd7in5b_V2.py`. `iauso/panels.py` mapea cada uno a su tamano y modo de color; `iauso/display.py` separa la imagen renderizada en dos capas (negro y color) para los modelos "b", usando el mismo patron `getbuffer()`/`display(imageblack, imagered)` del driver oficial. Ver [PANELES.md](PANELES.md) para el alcance y las limitaciones de esta parte.

El manual recomienda al menos 180 segundos entre refrescos y refrescar al menos cada 24 horas durante el uso. El proyecto fija un ciclo de 300 segundos, evita redibujar imágenes idénticas y fuerza mantenimiento aproximadamente diario. El tiempo real de refresco puede variar con temperatura y alimentación. No se usa refresco parcial ni animación.

## Autenticación

- [OpenAI: autenticación de Codex](https://developers.openai.com/codex/auth): sesiones de suscripción, almacenamiento local y autenticación por código de dispositivo.
- [Anthropic: autenticación de Claude Code](https://code.claude.com/docs/en/authentication): almacenamiento de credenciales por sistema operativo.
- [Anthropic: Claude Code con Pro o Max](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan).

Los endpoints de cuotas pertenecen a los proveedores, pero no constituyen aquí una promesa de API pública estable. Solo se implementan consultas de lectura con sesiones propias. El usuario completa los inicios de sesión en las herramientas oficiales.

## Servidor Docker de la versión 1.1

- [Docker Compose: secretos](https://docs.docker.com/compose/how-tos/use-secrets/): montaje del archivo privado en `/run/secrets/api_token`.
- [Gunicorn en PyPI](https://pypi.org/project/gunicorn/): servidor WSGI; esta entrega fija 26.2.0.
- [OpenAI: Codex CLI](https://github.com/openai/codex): paquete oficial `@openai/codex` para el contenedor temporal de autenticación.
- [Anthropic: instalación](https://code.claude.com/docs/en/setup): paquete `@anthropic-ai/claude-code` y requisitos de las CLI.
- [Anthropic: referencia CLI](https://code.claude.com/docs/en/cli-reference): `claude auth login`, sin `--console`, para la sesión de suscripción.

La API propia es nueva en esta adaptación; no forma parte del repositorio Swift original. El recolector se mantiene separado del proceso HTTP, por lo que varias pantallas comparten la misma lectura. El contenedor HTTP solo monta la carpeta del snapshot público y la clave de la API; las sesiones se montan únicamente en el recolector y en el contenedor temporal de autenticación.
