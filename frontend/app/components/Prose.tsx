// Renders parsed answer blocks (plain English + legal language).
import type { Block } from "../lib/types";

function BlockView({ b }: { b: Block }) {
  if (b.t === "h2") return <h2 dangerouslySetInnerHTML={{ __html: b.html }} />;
  if (b.t === "h3") return <h3 dangerouslySetInnerHTML={{ __html: b.html }} />;
  if (b.t === "p")
    return <p className={b.lead ? "lead" : ""} dangerouslySetInnerHTML={{ __html: b.html }} />;
  if (b.t === "ul")
    return (
      <ul>
        {b.items.map((it, i) => (
          <li key={i}>
            <span dangerouslySetInnerHTML={{ __html: it.html }} />
            {it.cite && (
              <>
                {" "}
                <span className="cite-ref">{it.cite}</span>
              </>
            )}
          </li>
        ))}
      </ul>
    );
  if (b.t === "quote")
    return (
      <div className="verbatim">
        <span className="vq">“{b.text}”</span>
        <div className="vmeta">
          <span className="vtag">Verbatim statute</span>
          <span className="vrule" />
          <span className="vcite">{b.cite}</span>
        </div>
      </div>
    );
  return null;
}

export default function Prose({ blocks }: { blocks: Block[] }) {
  return (
    <div className="prose">
      {blocks.map((b, i) => (
        <BlockView key={i} b={b} />
      ))}
    </div>
  );
}
