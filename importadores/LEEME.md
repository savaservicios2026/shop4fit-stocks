# Entrada automática de solicitudes

Las solicitudes de presupuesto llegan a la pestaña **Solicitudes** de la app. Cada contacto (un correo o un número de WhatsApp) es una solicitud, y sus mensajes nuevos se van añadiendo y la marcan como *sin leer*.

Todo funciona con el plan gratuito de Firebase (Spark): no hacen falta Cloud Functions.

## 0. Una vez: usuario importador y reglas

1. Firebase → **Authentication** → *Usuarios* → *Añadir usuario*: correo `importador@shop4fit-stocks.firebaseapp.com` y una contraseña larga. Esa contraseña es `IMPORTADOR_CLAVE`.
2. Firebase → **Firestore Database** → *Reglas*: pega el contenido de [`firestore.rules`](../firestore.rules) y pulsa *Publicar*.
   El importador solo puede crear solicitudes y añadirles mensajes; no ve el stock ni puede borrar nada.

## 1. Correo de empresa (cada 10 minutos, GitHub Actions)

`correo.py` lee la bandeja de entrada sin marcar nada como leído. Solo crea solicitudes con los correos que parecen una petición (presupuesto, oferta, precio, solicitud, lead…). Deja fuera los correos internos, los boletines, la bandeja «Otros» de Outlook y los remitentes que marques en la app con **«No importar más de…»** (por ejemplo, un proveedor que os manda sus presupuestos).

Los secretos se crean en GitHub → *Settings* → *Secrets and variables* → *Actions* → *New repository secret*. Siempre hace falta `IMPORTADOR_CLAVE`, la contraseña del paso 0.

### Microsoft 365 / Outlook (administracion@savaservicios.com)

Microsoft 365 ya no deja entrar por IMAP con contraseña, así que se usa una aplicación registrada en la empresa:

1. Entra en **entra.microsoft.com** con una cuenta de administrador → *Aplicaciones* → *Registros de aplicaciones* → **Nuevo registro**. Nombre: `Shop4Fit Solicitudes`; *Solo las cuentas de este directorio organizativo*; **Registrar**.
2. En la página que se abre, copia **Id. de aplicación (cliente)** → secreto `M365_CLIENTE`, y **Id. de directorio (inquilino)** → secreto `M365_TENANT`.
3. *Permisos de API* → **Agregar un permiso** → *Microsoft Graph* → **Permisos de aplicación** → marca `Mail.Read` → *Agregar permisos*. Después pulsa **Conceder consentimiento de administrador** y confirma.
4. *Certificados y secretos* → **Nuevo secreto de cliente** → caducidad 24 meses → *Agregar*. Copia la columna **Valor** (solo se ve una vez) → secreto `M365_SECRETO`.
5. Secreto `M365_BUZON`: `administracion@savaservicios.com`.

El secreto de cliente caduca a los 24 meses: entonces se crea otro y se cambia `M365_SECRETO`.

### Otros buzones (Gmail, correo del hosting) por IMAP

| Secreto | Valor |
|---|---|
| `IMAP_SERVIDOR` | Gmail / Google Workspace: `imap.gmail.com`. Otros: el servidor IMAP del proveedor |
| `IMAP_USUARIO` | la dirección del buzón |
| `IMAP_CLAVE` | Gmail: una *contraseña de aplicación*. Otros: la contraseña del buzón |
| `IMAP_CARPETA` | opcional; por defecto `INBOX` |

### Probarlo

GitHub → *Actions* → *Importar correos a Solicitudes* → **Run workflow**. La primera vez revisa los correos de los últimos 3 días. Si quieres que entren todos los correos y no solo los que parecen peticiones, crea el secreto `CORREO_TODO` con el valor `si`.

## 2. WhatsApp de empresa

**Ya disponible, sin configurar nada:** en Android, con la app instalada, mantén pulsado un mensaje en WhatsApp → *Compartir* → *S4F Stocks*: se abre la solicitud con el texto, el nombre y el teléfono. En iPhone, copia el mensaje y pégalo en *+ Nueva solicitud*.

**Automático (API de WhatsApp Business de Meta):** `whatsapp-worker.js` recibe los mensajes y los guarda. Se aloja gratis en Cloudflare Workers.

1. Cloudflare (cuenta gratuita) → *Workers & Pages* → *Create* → *Hello World* → *Edit code*: pega `whatsapp-worker.js` y despliega. Anota la URL `https://….workers.dev`.
2. En el Worker → *Settings* → *Variables and Secrets*: `VERIFY_TOKEN` (un texto que inventes), `APP_SECRET` (Meta → tu app → *Configuración básica* → *Clave secreta de la app*) e `IMPORTADOR_CLAVE`.
3. Meta for Developers → tu app → *WhatsApp* → *Configuración* → *Webhook*: URL del Worker y el mismo `VERIFY_TOKEN`; suscribe el campo `messages`.

Recibir mensajes de clientes en la API es gratis. Con la *coexistencia* de Meta el número sigue funcionando a la vez en la app WhatsApp Business del móvil (hay que abrir esa app al menos una vez cada 13 días).
