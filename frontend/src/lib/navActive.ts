/** The longest nav href that matches this path, so a parent and a child are never both current. */
export function activeHref(pathname: string, hrefs: string[]): string | null {
  const matches = hrefs.filter((href) => pathname === href || (href !== "/" && pathname.startsWith(`${href}/`)));
  if (matches.length === 0) return null;
  return matches.sort((a, b) => b.length - a.length)[0];
}
