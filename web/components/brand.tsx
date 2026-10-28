import Link from "next/link";

export function Brand({ dark = false }: { dark?: boolean }) {
  return (
    <Link
      href="/"
      className={`brand ${dark ? "brand-dark" : ""}`}
      aria-label="Corvus home"
    >
      <svg width="36" height="36" viewBox="0 0 64 64" aria-hidden="true">
        <use href="/brand/mark.svg#raven" />
      </svg>
      <span>corvus</span>
    </Link>
  );
}
