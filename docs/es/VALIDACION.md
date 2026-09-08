# Validación de la entrega

Fecha: 7 de septiembre de 2026.

Versión 1.2. Resultado: **30 pruebas aprobadas** con `python3 -m unittest discover -s tests -v`.

Cobertura relevante:

- Umbrales de color configurables: `warn_percent`/`crit_percent` cambian efectivamente el color de las barras, un panel de un solo color de tinta nunca pinta el segundo y uno monocromo no pinta ninguno; se rechazan valores fuera de rango o con `warn_percent` mayor que `crit_percent`.
- Claude: formatos nuevo y anterior, combinación sin duplicados y valores ausentes.
- Codex: cuotas principales, duración real y reinicios absolutos/relativos.
- Rechazo de porcentajes inválidos, sesiones vencidas y API keys en lugar de sesiones.
- HTTP 401, espera 429 persistente, caché con fecha original y cambio de cuenta/token.
- Proveedores deshabilitados: no se leen sus credenciales.
- Snapshot sin secretos, validación de fecha, datos antiguos y rechazo de DEMO como fuente real.
- Imagen 296 × 160 limitada a negro, blanco, amarillo y rojo; vista previa inspeccionada.
- `getbuffer()` oficial: 11.840 bytes; codificación correcta de los cuatro colores.
- Intervalo mínimo entre refrescos, mantenimiento diario y espera después de un fallo de hardware simulado.
- Flujo por línea de comandos de DEMO y receptor, sin necesitar GPIO ni cuentas.
- Envío SSH con comando fijo, datos por entrada estándar y rechazo de opciones inyectadas en el destino.
- API sobre HTTP local real: autenticación Bearer, rutas/métodos, errores 401/503 y cabeceras sin caché.
- API sin consultas adicionales a proveedores y salida limitada a campos públicos; datos privados inyectados en las pruebas se eliminan de la respuesta.
- Cliente HTTP y CLI de la Raspberry: lectura de la API y renderizado 296 × 160 sin leer sesiones locales.
- Caída del servidor: conserva cuotas con su fecha, marca desconexión y descarta lecturas de otro servidor o fuera de orden.
- Detección de datos antiguos aunque la API siga funcionando; bloqueo de redirecciones y HTTPS como valor predeterminado.
- Inicializador del servidor: carpetas/clave privadas y conservación de claves/configuración en una segunda ejecución.

Comprobaciones adicionales: sintaxis del instalador con `bash -n`, compilación Python y unidades generadas aceptadas por `systemd-analyze verify` (salida 0). Los dos archivos Waveshare incluidos se compararon byte a byte con el commit documentado.

Se ejecutó además **Gunicorn 26.2.0 real**, con dos procesos y dos hilos por proceso, usando los mismos argumentos HTTP del Dockerfile: inicio correcto y respuestas 200, 401 y 503 verificadas con datos simulados. La clave de prueba no aparece en stdout/stderr. Se analizó el YAML de Compose y se verificaron montajes separados, UID/GID 1000, puerto local predeterminado y perfil de autenticación temporal. Esto no equivale a construir ni ejecutar los contenedores.

Pendiente en el equipo del usuario: construcción y arranque de Docker Compose, descarga/login de las CLI oficiales, conectividad entre servidor y Raspberry, alimentación y montaje del HAT, permisos GPIO/SPI, refresco físico y respuesta actual de los servicios autenticados. No había un motor Docker disponible aquí; no se ejecutó el instalador en una Raspberry ni se usaron credenciales reales durante estas pruebas.

## Añadido en la versión 1.2

Se verificó con Docker Compose real: construcción de las imágenes, arranque de `collector` y `api`, login real de Claude y Codex, y respuestas 200 de `/healthz` y `/v1/usage` con cuotas reales de ambos proveedores. También se comprobó el preflight `OPTIONS` y las cabeceras CORS con `curl` contra el servidor en marcha.

Se renderizaron los ocho paneles del registro (`iauso/panels.py`) y se revisó que cada uno use exclusivamente los colores que su tinta permite: solo negro y blanco en los monocromos, y negro/blanco/color en los "duo". **Los siete paneles distintos del 2.15G no se probaron en hardware físico**: su código de driver es el oficial de Waveshare sin modificar, pero la comunicación SPI real con esos paneles queda sin verificar. Ver [PANELES.md](PANELES.md).

Tampoco se probaron en un servidor real las unidades systemd de [SIN_DOCKER.md](SIN_DOCKER.md) ni los ejemplos de [INTEGRACIONES.md](INTEGRACIONES.md); sí se verificó que cada receta de [CONFIGURACION.md](CONFIGURACION.md) cargue y renderice, y que todos los enlaces internos de la documentación resuelvan.
