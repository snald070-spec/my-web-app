/**
 * getItems — normalises API responses.
 * Handles both legacy raw arrays AND paginated { items, total } objects.
 *
 * Usage:  const items = getItems(response.data);
 */
export const getItems = (data) =>
  Array.isArray(data) ? data : (data?.items ?? []);

export const getTotal = (data) =>
  Array.isArray(data) ? data.length : (data?.total ?? 0);
