import {
  assertApiTarget,
  endpointForTarget,
  selectedApiTarget,
  streamEndpointForTarget,
} from "./environment";

const JSON_CONTENT_TYPE = "application/json";
const WS_CONNECT_FAILED = "WS_CONNECT_FAILED";

export function apiBase(target = selectedApiTarget()) {
  return endpointForTarget(assertApiTarget(target)).apiBase;
}

export function websocketBase(target = selectedApiTarget()) {
  const base = apiBase(target);
  if (base.startsWith("https://")) return `wss://${base.slice("https://".length)}`;
  if (base.startsWith("http://")) return `ws://${base.slice("http://".length)}`;
  throw new Error(`Unsupported API base URL: ${base}`);
}

export function rpcWebSocketUrl(target = selectedApiTarget()) {
  return `${websocketBase(target)}/api/transport/rpc`;
}

export function musicStreamUrl(target = selectedApiTarget()) {
  return `${streamEndpointForTarget(target)}/music/stream`;
}

export async function requestJson(path, options = {}) {
  try {
    return await requestJsonOverWebSocket(path, options);
  } catch (error) {
    if (error?.code === "WS_CONNECT_FAILED") {
      return requestJsonOverHttp(path, options);
    }
    throw error;
  }
}

export async function requestJsonOverWebSocket(path, options = {}) {
  const token = localStorage.getItem("yts-access-token") || "";
  const { target, auth, headers: extraHeaders, body, method = "GET" } = options;
  const requestTarget = target ?? selectedApiTarget();
  const baseUrl = apiBase(requestTarget);
  const headers = jsonHeaders({ token, auth, extraHeaders });
  const parsedBody = parseRequestBody(body);
  const messageId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const response = await sendRpcMessage(requestTarget, {
    id: messageId,
    method,
    path,
    headers,
    body: parsedBody,
  });
  return handleJsonResponse({
    path,
    auth,
    target: requestTarget,
    baseUrl,
    status: response.status,
    statusText: "",
    body: response.body,
  });
}

export async function requestJsonOverHttp(path, options = {}) {
  const token = localStorage.getItem("yts-access-token") || "";
  const { target, auth, headers: extraHeaders, ...fetchOptions } = options;
  const requestTarget = target ?? selectedApiTarget();
  const baseUrl = apiBase(requestTarget);
  const headers = jsonHeaders({ token, auth, extraHeaders });
  let response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...fetchOptions,
      headers,
    });
  } catch (error) {
    annotateRequestError(error, { path, target: requestTarget, baseUrl });
    throw error;
  }
  const body = await response.json().catch(() => null);
  return handleJsonResponse({
    path,
    auth,
    target: requestTarget,
    baseUrl,
    status: response.status,
    statusText: response.statusText,
    body,
  });
}

export async function uploadForm(path, formData, options = {}) {
  const token = localStorage.getItem("yts-access-token") || "";
  const { target, auth, headers: extraHeaders, ...fetchOptions } = options;
  const requestTarget = target ?? selectedApiTarget();
  const baseUrl = apiBase(requestTarget);
  const headers = {
    ...(token && auth !== false ? { Authorization: `Bearer ${token}` } : {}),
    ...(extraHeaders ?? {}),
  };
  let response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method: "POST",
      ...fetchOptions,
      headers,
      body: formData,
    });
  } catch (error) {
    annotateRequestError(error, { path, target: requestTarget, baseUrl });
    throw error;
  }
  const body = await response.json().catch(() => null);
  return handleJsonResponse({
    path,
    auth,
    target: requestTarget,
    baseUrl,
    status: response.status,
    statusText: response.statusText,
    body,
  });
}

export async function requestBlob(path, options = {}) {
  const token = localStorage.getItem("yts-access-token") || "";
  const { target, auth, headers: extraHeaders, ...fetchOptions } = options;
  const requestTarget = target ?? selectedApiTarget();
  const baseUrl = apiBase(requestTarget);
  const headers = {
    ...(token && auth !== false ? { Authorization: `Bearer ${token}` } : {}),
    ...(extraHeaders ?? {}),
  };
  let response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...fetchOptions,
      headers,
    });
  } catch (error) {
    annotateRequestError(error, { path, target: requestTarget, baseUrl });
    throw error;
  }
  if (response.status >= 200 && response.status < 300) {
    return response.blob();
  }
  const body = await response.json().catch(() => null);
  throw responseError({
    path,
    auth,
    target: requestTarget,
    baseUrl,
    status: response.status,
    statusText: response.statusText,
    body,
  });
}

export function openJsonStream(path, payload, handlers = {}, options = {}) {
  const requestTarget = options.target ?? selectedApiTarget();
  const token = localStorage.getItem("yts-access-token") || "";
  const fallbackJson = options.fallbackJson;
  const ws = new WebSocket(`${websocketBase(requestTarget)}${path}`);
  let settled = false;
  let opened = false;

  ws.onopen = () => {
    opened = true;
    handlers.onOpen?.(ws);
    ws.send(
      JSON.stringify({
        ...payload,
        authorization: token ? `Bearer ${token}` : "",
      }),
    );
  };
  ws.onmessage = (event) => {
    handlers.onMessage?.(JSON.parse(event.data), ws);
  };
  ws.onerror = () => {
    if (settled) return;
    settled = true;
    if (!opened && fallbackJson) {
      fallbackJson().then(handlers.onFallbackResult).catch(handlers.onError);
      return;
    }
    handlers.onError?.(connectionError("JSON stream WebSocket connection failed"));
  };
  ws.onclose = () => {
    handlers.onClose?.(ws, settled);
  };
  return ws;
}

export function openBinaryStream(path, { target = selectedApiTarget(), onOpen, onMessage, onError, onClose } = {}) {
  const url = path.startsWith("ws://") || path.startsWith("wss://") ? path : `${musicStreamUrl(target)}${path}`;
  const ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => onOpen?.(ws);
  ws.onmessage = (event) => onMessage?.(event, ws);
  ws.onerror = () => onError?.(connectionError("Binary stream WebSocket connection failed"));
  ws.onclose = () => onClose?.(ws);
  return ws;
}

function sendRpcMessage(target, message) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(rpcWebSocketUrl(target));
    let settled = false;
    ws.onopen = () => {
      ws.send(JSON.stringify(message));
    };
    ws.onmessage = (event) => {
      settled = true;
      resolve(JSON.parse(event.data));
      ws.close();
    };
    ws.onerror = () => {
      if (!settled) {
        settled = true;
        reject(connectionError("WebSocket RPC connection failed"));
      }
    };
    ws.onclose = () => {
      if (!settled) {
        settled = true;
        reject(connectionError("WebSocket RPC closed before response"));
      }
    };
  });
}

function jsonHeaders({ token, auth, extraHeaders }) {
  return {
    "Content-Type": JSON_CONTENT_TYPE,
    ...(token && auth !== false ? { Authorization: `Bearer ${token}` } : {}),
    ...(extraHeaders ?? {}),
  };
}

function parseRequestBody(body) {
  if (body === undefined || body === null || body === "") return null;
  if (typeof body === "string") return JSON.parse(body);
  return body;
}

function handleJsonResponse({ path, auth, target, baseUrl, status, statusText, body }) {
  if (status >= 200 && status < 300) return body;
  throw responseError({ path, auth, target, baseUrl, status, statusText, body });
}

function responseError({ path, auth, target, baseUrl, status, statusText, body }) {
  if (status === 401 && auth !== false) {
    localStorage.removeItem("yts-access-token");
    localStorage.removeItem("yts-user");
    window.dispatchEvent(new CustomEvent("yts-auth-expired", { detail: { path, body } }));
  }
  const detail = body?.detail ?? body?.message ?? `${status} ${statusText}`.trim();
  const error = new Error(detail);
  error.status = status;
  error.body = body;
  error.path = path;
  error.target = target;
  error.apiBase = baseUrl;
  return error;
}

function annotateRequestError(error, { path, target, baseUrl }) {
  if (error && typeof error === "object") {
    error.path = path;
    error.target = target;
    error.apiBase = baseUrl;
  }
}

function connectionError(message) {
  const error = new Error(message);
  error.code = WS_CONNECT_FAILED;
  return error;
}
