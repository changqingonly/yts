import { startGateway } from "./desktop";
import { assertApiTarget, isTauriRuntime } from "./environment";

export async function ensureInferenceReady(target) {
  const requestTarget = assertApiTarget(target);
  if (requestTarget !== "local" || !isTauriRuntime()) return;
  await startGateway();
}
