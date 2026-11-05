import Link from "next/link";

export function AgentTabs({
  current,
}: {
  current: "analyst" | "correlation" | "intel";
}) {
  return (
    <nav className="agent-tabs" aria-label="Investigation agents">
      {(["analyst", "correlation", "intel"] as const).map((kind) => (
        <Link
          key={kind}
          href={`/soc/agents/${kind}`}
          aria-current={current === kind ? "page" : undefined}
        >
          {kind === "analyst"
            ? "Investigations"
            : kind === "correlation"
              ? "Correlation"
              : "Intel"}
        </Link>
      ))}
    </nav>
  );
}
