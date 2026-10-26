# Shop4Fit Stocks

Control de stock de la nave de Shop4Fit: entradas y salidas por código de barras, pedidos a proveedor vinculados a presupuestos y albaranes de cliente, análisis de ventas por categoría, etiquetas de códigos de barras en PDF y bandeja de **solicitudes de presupuesto** que llegan por WhatsApp y correo.

- **App:** https://savaservicios2026.github.io/shop4fit-stocks/
- **Datos:** Firebase (proyecto `shop4fit-stocks`): Firestore + Authentication con un único acceso de oficina. Las reglas están en `firestore.rules`.
- **Instalar en el móvil:** abre la app en Chrome (Android) o Safari (iPhone) → *Añadir a pantalla de inicio*.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La app completa (generada desde `fuente/index.html`) |
| `firebase-config.js` | Configuración web de Firebase (pública, no es secreta) |
| `manifest.webmanifest`, `iconos/`, `sw.js` | Lo necesario para instalarla como app con el icono de Shop4Fit Stocks |
| `firestore.rules` | Reglas de seguridad de la base de datos |
| `fuente/index.html` | Código fuente de la app, el mismo que la versión de claude.ai |
| `importadores/` | Entrada automática de correos y WhatsApp a *Solicitudes*; cómo activarla en [`importadores/LEEME.md`](importadores/LEEME.md) |
| `.github/workflows/importar-correo.yml` | Tarea que lee el correo de empresa cada 10 minutos |
