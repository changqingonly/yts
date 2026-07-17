export function createSessionRefresher({ refresh, onInvalid = () => {} }) {
  let active = null;

  async function refreshNow() {
    if (active) return active;
    active = Promise.resolve()
      .then(refresh)
      .catch((error) => {
        if (error?.status === 401) onInvalid(error);
        throw error;
      })
      .finally(() => {
        active = null;
      });
    return active;
  }

  return { refreshNow };
}
