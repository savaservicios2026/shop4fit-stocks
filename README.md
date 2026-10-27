# Shop4Fit Stocks

Control de stock de la nave de Shop4Fit: entradas y salidas por código de barras, pedidos a proveedor vinculados a presupuestos y albaranes de cliente, análisis de ventas por categoría, etiquetas de códigos de barras en PDF y bandeja de **solicitudes de presupuesto** que llegan por WhatsApp y correo.

- **App:** https://savaservicios2026.github.io/shop4fit-stocks/
- **Dentro de Rutech:** es la sección **Stock** de Rutech (solo para usuarios de oficina). Rutech la muestra desde esta misma dirección, así que se entra con el mismo usuario.
- **Datos:** Firebase de Rutech (proyecto `rutech-61f25`): Firestore + Authentication. Entran los usuarios con rol `oficina` en Rutech. Las reglas están en el repositorio de Rutech (`firestore.rules`).
- **Instalar en el móvil:** abre la app en Chrome (Android) o Safari (iPhone) → *Añadir a pantalla de inicio*.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La app completa (generada desde `fuente/index.html`) |
| `firebase-config.js` | Configuración web de Firebase (pública, no es secreta) |
| `manifest.webmanifest`, `iconos/`, `sw.js` | Lo necesario para instalarla como app con el icono de Shop4Fit Stocks |
| `fuente/index.html` | Código fuente de la app, el mismo que la versión de claude.ai |
| `importadores/` | Entrada automática de correos y WhatsApp a *Solicitudes*; cómo activarla en [`importadores/LEEME.md`](importadores/LEEME.md) |
| `.github/workflows/importar-correo.yml` | Tarea que lee el correo de empresa cada 10 minutos |

## Proveedor por referencia (`proveedores-catalogo.json`)

Lista las referencias de los catálogos y tarifas de cada proveedor, con su correo. Cuando un producto o una línea de pedido no tiene proveedor en su ficha, la app lo busca aquí por la referencia (Pedidos › Proveedores, ficha y alta de producto). Para añadir un catálogo, añade sus referencias dentro de `catalogos` del proveedor.
