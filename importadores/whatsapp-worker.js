// Webhook de la API de WhatsApp Business (Cloud API de Meta) → «Solicitudes» de Shop4Fit Stocks.
// Se despliega gratis como Cloudflare Worker. Cada número de teléfono es una solicitud; sus mensajes se van añadiendo.
// Variables del Worker (Settings → Variables, las tres como «Secret»):
//   VERIFY_TOKEN       texto inventado que se pone también en Meta al configurar el webhook
//   APP_SECRET         «Clave secreta de la app» de Meta (para comprobar que los avisos vienen de Meta)
//   IMPORTADOR_CLAVE   contraseña del usuario importador@rutech-61f25.firebaseapp.com en Firebase
const API_KEY = "AIzaSyBuBlY62FvQhA3aJ-JDJgxVexgs1Kay4Uo", PROYECTO = "rutech-61f25";
const IMPORTADOR = "importador@rutech-61f25.firebaseapp.com";
const RAIZ = `projects/${PROYECTO}/databases/(default)/documents`, BASE = "https://firestore.googleapis.com/v1/" + RAIZ;
const TIPOS = {image:"Foto", video:"Vídeo", audio:"Nota de voz", document:"Documento", sticker:"Sticker", location:"Ubicación", contacts:"Contacto"};

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (req.method === "GET") { // verificación del webhook desde el panel de Meta
      const ok = url.searchParams.get("hub.mode") === "subscribe" && url.searchParams.get("hub.verify_token") === env.VERIFY_TOKEN;
      return new Response(ok ? url.searchParams.get("hub.challenge") : "Prohibido", {status: ok ? 200 : 403});
    }
    if (req.method !== "POST") return new Response("", {status: 405});
    const cuerpo = await req.text();
    if (!(await firmaValida(cuerpo, req.headers.get("x-hub-signature-256"), env.APP_SECRET))) return new Response("Firma no válida", {status: 401});
    ctx.waitUntil(procesar(JSON.parse(cuerpo), env).catch(e => console.error(e)));
    return new Response("ok"); // Meta exige respuesta rápida; el guardado sigue en segundo plano
  }
};

async function firmaValida(cuerpo, firma, secreto) {
  if (!firma || !secreto) return false;
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(secreto), {name:"HMAC", hash:"SHA-256"}, false, ["sign"]);
  const hex = [...new Uint8Array(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(cuerpo)))].map(b => b.toString(16).padStart(2, "0")).join("");
  return firma === "sha256=" + hex;
}

async function procesar(aviso, env) {
  const mensajes = [];
  for (const e of aviso.entry || []) for (const c of e.changes || []) {
    const v = c.value || {}, nombres = Object.fromEntries((v.contacts || []).map(x => [x.wa_id, x.profile?.name || ""]));
    for (const m of v.messages || []) mensajes.push({m, nombre: nombres[m.from] || ""});
  }
  if (!mensajes.length) return; // avisos de estado (entregado, leído…): nada que guardar
  const token = await iniciarSesion(env);
  for (const {m, nombre} of mensajes) {
    const fecha = new Date(Number(m.timestamp) * 1000 || Date.now()).toISOString();
    const texto = m.type === "text" ? m.text?.body
      : m.type === "interactive" ? (m.interactive?.button_reply?.title || m.interactive?.list_reply?.title)
      : m.type === "button" ? m.button?.text
      : `[${TIPOS[m.type] || m.type}]${m[m.type]?.caption ? " " + m[m.type].caption : ""}${m.type === "document" && m.document?.filename ? " " + m.document.filename : ""}`;
    const msg = {id: m.id, fecha, canal: "whatsapp", de: nombre ? `${nombre} (+${m.from})` : "+" + m.from, asunto: "", texto: String(texto || "").slice(0, 8000)};
    const nueva = {canal: "whatsapp", nombre, empresa: "", telefono: m.from, email: "", asunto: "", nota: "", fecha, ultimo: fecha,
      estado: "nueva", sinLeer: true, pedidosCliente: [], autor: "importador-whatsapp", mensajes: [msg]};
    await anadirASolicitud(token, "whatsapp-" + m.from, nueva, msg);
  }
}

async function iniciarSesion(env) {
  const r = await fetch("https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=" + API_KEY, {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({email: IMPORTADOR, password: env.IMPORTADOR_CLAVE, returnSecureToken: true})});
  if (!r.ok) throw new Error("Firebase: no se pudo iniciar sesión como importador (" + r.status + ")");
  return (await r.json()).idToken;
}

const valor = v => typeof v === "boolean" ? {booleanValue: v} : Array.isArray(v) ? {arrayValue: {values: v.map(valor)}}
  : v && typeof v === "object" ? {mapValue: {fields: Object.fromEntries(Object.entries(v).map(([k, x]) => [k, valor(x)]))}} : {stringValue: String(v ?? "")};

async function anadirASolicitud(token, id, nueva, msg) {
  const h = {"Content-Type": "application/json", Authorization: "Bearer " + token};
  const r = await fetch(`${BASE}/solicitudes?documentId=${encodeURIComponent(id)}`, {method: "POST", headers: h, body: JSON.stringify({fields: valor(nueva).mapValue.fields})});
  if (r.ok) return;
  if (r.status !== 409) throw new Error("Firestore " + r.status + ": " + await r.text());
  const c = await fetch(BASE.replace("/documents", "/documents:commit"), {method: "POST", headers: h, body: JSON.stringify({writes: [{
    update: {name: `${RAIZ}/solicitudes/${id}`, fields: {ultimo: valor(msg.fecha), sinLeer: valor(true)}},
    updateMask: {fieldPaths: ["ultimo", "sinLeer"]},
    updateTransforms: [{fieldPath: "mensajes", appendMissingElements: {values: [valor(msg)]}}],
    currentDocument: {exists: true}}]})});
  if (!c.ok) throw new Error("Firestore " + c.status + ": " + await c.text());
}
