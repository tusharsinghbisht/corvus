import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  Braces,
  Check,
  Database,
  FileSearch,
  Fingerprint,
  Github,
  Layers3,
  LockKeyhole,
  Radio,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { Brand } from "@/components/brand";
import { AgentArchitecture } from "@/components/agent-architecture";
import {
  InvestigationScene,
  EvidenceIllustration,
  StorageIllustration,
} from "@/components/isometric";
import { ArchitectureExplorer } from "@/components/landing-explorer";

const stack = [
  {
    name: "Next.js",
    layer: "THE INTERFACE",
    icon: Layers3,
    description:
      "React and TypeScript for an authenticated, responsive workspace. Your browser never receives backend or model credentials.",
  },
  {
    name: "Python · FastAPI",
    layer: "THE SERVICE",
    icon: Braces,
    description:
      "A small API and a separate ingestion worker. Backend adapters, evidence collection, reporting, and model transport remain separate.",
  },
  {
    name: "PostgreSQL",
    layer: "THE OPERATIONAL RECORD",
    icon: Database,
    description:
      "Transactional checkpoints, indexed alert fields, original JSONB payloads, sessions, and audit events. A foundation for later operational analytics.",
  },
  {
    name: "Docker · Caddy",
    layer: "THE DEPLOYMENT",
    icon: LockKeyhole,
    description:
      "Separate web, API, worker, and database containers. HTTPS at the edge, private service routing, and server-side secrets.",
  },
  {
    name: "LangGraph",
    layer: "WORKFLOW ORCHESTRATION",
    icon: Workflow,
    planned: true,
    description:
      "Planned for explicit agent handoffs, durable workflow state, checkpointing, and human-approval pauses. It is not part of the current runtime. Permissions and response policy stay enforced by Corvus outside the agents.",
  },
];

const questions = [
  {
    question: "Does Corvus replace Wazuh?",
    answer:
      "No. Wazuh remains responsible for detection and telemetry. Corvus is an independent companion that preserves incoming alerts and adds an evidence-led investigation workflow. You do not need to fork Wazuh or couple its lifecycle to Corvus.",
  },
  {
    question: "What can I use in the workspace today?",
    answer:
      "Authenticated Wazuh connection setup, durable alert ingestion, severity and time filters, search, pagination, sync health, and original-source inspection. The Analyst core already exists separately; manual dashboard triage is the next integration. Automatic mode is planned, not currently enabled.",
  },
  {
    question: "Does every alert get sent to a model?",
    answer:
      "No. The current ingestion worker makes no model calls. Analyst processing requires an explicit external-processing decision. Planned automatic mode will require separate connection-level consent and request limits; turning on ingestion will not opt you in.",
  },
  {
    question: "Can the Analyst contain or remediate an endpoint?",
    answer:
      "No. It is read-only and has no response executor. Recommendations remain advisory. A model disposition, completed report, or passed citation check is not authorization for an endpoint action.",
  },
  {
    question: "Why PostgreSQL instead of another analytics database?",
    answer:
      "The application needs transactions, deduplication, authentication, job state, and indexed queries first. PostgreSQL supports that operational workload and initial SQL analytics. High-volume raw telemetry stays in Wazuh rather than being copied into another event lake.",
  },
  {
    question: "What happens when telemetry is missing?",
    answer:
      "Collection failures, truncation, incomplete time windows, and missing ancestry are preserved as explicit gaps. The Analyst must distinguish unknown activity from evidence of absence. Schema and citation checks improve inspectability but do not prove narrative accuracy.",
  },
];

export default function Home() {
  return (
    <main className="landing">
      <nav className="landing-nav glass-panel" aria-label="Main navigation">
        <Brand />
        <div>
          <a href="#features">Features</a>
          <a href="#architecture">Architecture</a>
          <a href="#stack">The stack</a>
          <Link href="/soc" className="nav-cta">
            Open workspace <ArrowUpRight size={15} />
          </Link>
        </div>
      </nav>
      <section className="landing-hero marketing-container">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="dot" /> INDEPENDENT SOC WORKSPACE
          </div>
          <h1>
            The alert is only
            <br />
            <span>the beginning.</span>
          </h1>
          <p>
            Connect your detections to a clearer investigation path. Keep the
            original evidence, understand the context, and make the next
            decision with something to stand on.
          </p>
          <div className="hero-actions">
            <Link href="/soc" className="button primary">
              Enter workspace <ArrowUpRight size={17} />
            </Link>
            <a href="#architecture" className="quiet-link">
              Explore the architecture <ArrowRight size={16} />
            </a>
          </div>
          <div className="hero-note">
            <ShieldCheck size={15} />
            <span>
              Wazuh-first. Read-only. Human judgment stays in the loop.
            </span>
          </div>
        </div>
        <InvestigationScene />
      </section>
      <div className="stack-ribbon marketing-container">
        <span>
          DESIGNED AS A COMPANION.
          <br />
          NOT ANOTHER SIEM.
        </span>
        <div>
          <span>Next.js</span>
          <span>TypeScript</span>
          <span>FastAPI</span>
          <span>PostgreSQL</span>
          <span>Docker</span>
        </div>
      </div>

      <section id="features" className="marketing-section marketing-container">
        <div className="section-heading">
          <div>
            <div className="eyebrow">A WORKSPACE, NOT A WALL OF SIGNALS</div>
            <h2>
              Your sources intact.
              <br />
              Your workflow in one place.
            </h2>
          </div>
          <p>
            Live detections, durable records, original evidence.
            <br />
            The operational essentials, connected.
          </p>
        </div>
        <div className="feature-grid">
          <article className="feature-card glass-panel">
            <div className="feature-card-top">
              <Radio size={23} />
              <span className="availability-tag">Available now</span>
            </div>
            <h3>A real alert queue.</h3>
            <p>
              Ingest Wazuh alerts across agents and rule levels. Search, filter
              by severity and time, and inspect the original detection without
              switching between disconnected views.
            </p>
            <div className="feature-detail-line">
              <span>Read-only adapter</span>
              <ArrowRight size={13} />
              <span>Authenticated workspace</span>
            </div>
          </article>
          <article className="feature-card glass-panel">
            <div className="feature-card-top">
              <Fingerprint size={23} />
              <span className="availability-tag">Available now</span>
            </div>
            <h3>Identity comes with it.</h3>
            <p>
              Keep the connection, native index, document ID, timestamps, and
              original source. Normalization adds usable context without
              replacing the underlying evidence.
            </p>
            <div className="feature-detail-line">
              <span>Native reference</span>
              <ArrowRight size={13} />
              <span>Original JSON</span>
            </div>
          </article>
          <article className="feature-card feature-card-wide glass-panel">
            <div>
              <div className="feature-card-top">
                <Database size={23} />
                <span className="availability-tag">Available now</span>
              </div>
              <h3>
                The browser is not
                <br />
                your database.
              </h3>
              <p>
                PostgreSQL preserves records independently of a browser session.
                Idempotent inserts and checkpointed polling let the worker catch
                up without pretending incomplete queries succeeded.
              </p>
              <ul className="feature-checks">
                <li>
                  <Check size={14} />
                  Durable alert records
                </li>
                <li>
                  <Check size={14} />
                  Visible backfill and sync health
                </li>
                <li>
                  <Check size={14} />
                  No archive mirroring
                </li>
              </ul>
            </div>
            <StorageIllustration />
          </article>
          <article className="feature-card feature-card-wide glass-panel">
            <div>
              <div className="feature-card-top">
                <FileSearch size={23} />
                <span className="availability-tag">Analyst core</span>
              </div>
              <h3>
                Context beyond
                <br />
                the trigger.
              </h3>
              <p>
                The collector retrieves bounded surrounding activity and process
                ancestry. The Analyst separates observations, inferences,
                alternative explanations, and gaps in an advisory report.
              </p>
              <p className="feature-status">
                Analyst engine implemented. Dashboard triage is the next
                rollout.
              </p>
            </div>
            <EvidenceIllustration />
          </article>
        </div>
      </section>

      <section
        id="architecture"
        className="marketing-section architecture-section marketing-container"
      >
        <div className="section-heading">
          <div>
            <div className="eyebrow">THE SOC ARCHITECTURE</div>
            <h2>
              An investigation workflow.
              <br />
              Not an isolated agent.
            </h2>
          </div>
          <p>
            Correlation, investigation, intelligence, and response.
            <br />
            Shared evidence. Explicit handoffs. Clear authority.
          </p>
        </div>
        <AgentArchitecture />
        <div className="implemented-flow-heading">
          <span className="eyebrow">IMPLEMENTED DATA PATHS</span>
          <p>
            Explore the live ingestion path and the standalone Analyst core
            below.
          </p>
        </div>
        <ArchitectureExplorer />
        <div className="architecture-notes">
          <div>
            <span>01</span>
            <h3>Backend boundaries</h3>
            <p>
              Wazuh-specific queries and field mappings stay inside the adapter.
              The collector and Analyst work with an evidence contract, not a
              forked SIEM.
            </p>
          </div>
          <div>
            <span>02</span>
            <h3>Storage boundaries</h3>
            <p>
              Operational records live in PostgreSQL. High-volume telemetry
              stays in Wazuh and is retrieved only within a scoped collection.
            </p>
          </div>
          <div>
            <span>03</span>
            <h3>Authority boundaries</h3>
            <p>
              Data retrieval, external analysis, report validation, and human
              review are separate steps. None grants the model permission to
              execute a response.
            </p>
          </div>
        </div>
      </section>

      <section className="principles marketing-container glass-panel">
        <div className="eyebrow">WHAT MAKES CORVUS DIFFERENT</div>
        <h2>
          Clearer context.
          <br />
          Accountable decisions.
        </h2>
        <div className="principle-grid">
          <article>
            <span>01 / SOURCE FIRST</span>
            <h3>A detection is a lead.</h3>
            <p>
              Rule names and severity are starting points, not proof of
              compromise. Keep the source close enough to challenge the
              interpretation.
            </p>
          </article>
          <article>
            <span>02 / HONEST UNCERTAINTY</span>
            <h3>Unknown stays unknown.</h3>
            <p>
              Failed collection is not “nothing happened.” Gaps and partial
              windows stay visible instead of becoming confident model prose.
            </p>
          </article>
          <article>
            <span>03 / CHECKABLE OUTPUT</span>
            <h3>Findings need a trail.</h3>
            <p>
              Evidence binding and citation checks make reports easier to
              inspect. They do not replace review or prove that every claim
              follows from the logs.
            </p>
          </article>
          <article>
            <span>04 / CONTROL RETAINED</span>
            <h3>Advice is not authority.</h3>
            <p>
              A recommendation is not an approved action. Corvus does not
              silently isolate hosts or turn a model label into incident
              resolution.
            </p>
          </article>
        </div>
      </section>

      <section id="stack" className="marketing-section marketing-container">
        <div className="section-heading">
          <div>
            <div className="eyebrow">BUILT ON UNDERSTANDABLE PARTS</div>
            <h2>
              A focused stack.
              <br />
              Clear responsibilities.
            </h2>
          </div>
          <p>
            Focused by design.
            <br />
            Every component has a clear responsibility.
          </p>
        </div>
        <div className="tech-grid">
          {stack.map((item) => {
            const Icon = item.icon;
            return (
              <article
                key={item.name}
                className={`tech-card glass-panel${"planned" in item ? " tech-card-planned" : ""}`}
              >
                <div>
                  <Icon size={22} />
                  <span>{item.layer}</span>
                </div>
                <h3>
                  {item.name}
                  {"planned" in item && (
                    <span className="availability-tag">Planned</span>
                  )}
                </h3>
                <p>{item.description}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="marketing-section faq-section marketing-container">
        <div>
          <div className="eyebrow">BEFORE YOU CONNECT</div>
          <h2>A few straight answers.</h2>
          <p>
            What runs today, what is next,
            <br />
            and what Corvus intentionally does not do.
          </p>
        </div>
        <div className="faq-list">
          {questions.map((item) => (
            <details key={item.question}>
              <summary>
                {item.question}
                <span aria-hidden="true">+</span>
              </summary>
              <p>{item.answer}</p>
            </details>
          ))}
        </div>
      </section>
      <section className="final-cta marketing-container glass-panel">
        <span className="eyebrow">START WITH WHAT ACTUALLY HAPPENED</span>
        <h2>
          Your alerts.
          <br />A clearer next step.
        </h2>
        <p>Bring the source into focus. Leave the assumptions behind.</p>
        <div>
          <Link href="/soc" className="button primary">
            Open workspace <ArrowUpRight size={17} />
          </Link>
          <a
            href="https://github.com/tusharsinghbisht/corvus"
            className="quiet-link"
          >
            <Github size={17} />
            Read the source
          </a>
        </div>
      </section>
      <footer className="landing-footer marketing-container">
        <Brand />
        <span>Independent investigation. Evidence before conclusions.</span>
        <div>
          <a href="#architecture">Architecture</a>
          <a href="https://github.com/tusharsinghbisht/corvus">
            GitHub <ArrowUpRight size={13} />
          </a>
        </div>
      </footer>
    </main>
  );
}
