/** The section name as the first thing in the page; it rides with the page and dissolves on scroll. */
export function LargeTitle({ title, detail = false }: { title: string; detail?: boolean }) {
  return (
    <h1 className={`large-title${detail ? " is-detail" : ""}`}>
      <span className="lt-crisp">{title}</span>
      <span className="lt-blur" aria-hidden="true">
        {title}
      </span>
    </h1>
  );
}
