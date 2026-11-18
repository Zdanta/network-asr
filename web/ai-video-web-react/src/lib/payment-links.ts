export function isPaymentUrl(value?: string | null) {
  if (!value) return false;
  try {
    const url = new URL(value);
    if (url.username || url.password) return false;
    return url.protocol === "https:" || (url.protocol === "alipays:" && url.hostname === "platformapi" && url.pathname === "/startapp");
  } catch { return false; }
}

export function isHttpsUrl(value?: string | null) {
  try { return Boolean(value && new URL(value).protocol === "https:"); }
  catch { return false; }
}

export function purchaseEntryExpired(value?: string | null) {
  if (!value) return false;
  const iso = value.replace(" ", "T");
  const zoned = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : iso + "+08:00";
  return Date.parse(zoned) < Date.now();
}
