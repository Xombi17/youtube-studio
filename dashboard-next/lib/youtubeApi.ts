/**
 * Thin fetch wrapper for CreatorRadar's /api/youtube/* endpoints.
 */
export function ytFetch(subpath: string, init?: RequestInit): Promise<Response> {
  const clean = subpath.startsWith("/") ? subpath : `/${subpath}`;
  return fetch(`/api/youtube${clean}`, init);
}
