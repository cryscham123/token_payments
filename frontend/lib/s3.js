export function getS3Url(path) {
  if (!path) return "";
  if (/^https?:\/\//.test(path)) return path;
  const cleanPath = path.startsWith("/") ? path.slice(1) : path;
  return `/${cleanPath}`;
}
