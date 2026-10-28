import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  Database,
  Fingerprint,
  ScanLine,
} from "lucide-react";
import { Brand } from "@/components/brand";

export default function Home() {
  return (
    <main className="landing">
      <nav className="landing-nav">
        <Brand />
        <div>
          <a href="#workflow">How it works</a>
          <a href="#principles">Principles</a>
          <Link href="/login" className="nav-cta">
            Open workspace <ArrowUpRight size={15} />
          </Link>
        </div>
      </nav>
      <section className="hero">
        <div className="eyebrow">
          <span className="dot" /> INDEPENDENT SOC WORKSPACE
        </div>
        <h1>
          More context.
          <br />
          Fewer assumptions.
        </h1>
        <p>
          Security alerts are a starting point. Corvus brings your Wazuh
          detections, supporting evidence, and investigation history into one
          focused workspace.
        </p>
        <div className="hero-actions">
          <Link href="/soc" className="button primary">
            Enter workspace <ArrowRight size={17} />
          </Link>
          <a href="#workflow" className="quiet-link">
            Follow the evidence ↓
          </a>
        </div>
        <div className="hero-foot">
          <span>Built around your telemetry.</span>
          <span>No replacement SIEM. No black-box response.</span>
        </div>
      </section>
      <section id="workflow" className="workflow">
        <div className="section-heading">
          <div>
            <div className="eyebrow">THE INVESTIGATION PATH</div>
            <h2>
              From a signal to something
              <br />
              you can stand behind.
            </h2>
          </div>
          <p>
            Keep the source. Gather the context.
            <br />
            Know what remains uncertain.
          </p>
        </div>
        <div className="steps">
          <article>
            <div className="step-top">
              <span>01 / CONNECT</span>
              <ScanLine size={22} />
            </div>
            <h3>
              Your detections,
              <br />
              one clear queue.
            </h3>
            <p>
              Connect Wazuh with dedicated read-only credentials. Incoming
              alerts retain their original source identity and severity.
            </p>
          </article>
          <article>
            <div className="step-top">
              <span>02 / PRESERVE</span>
              <Database size={22} />
            </div>
            <h3>
              A record that
              <br />
              doesn’t disappear.
            </h3>
            <p>
              PostgreSQL stores alerts independently of the browser, with
              ingestion checkpoints and visible connection health.
            </p>
          </article>
          <article>
            <div className="step-top">
              <span>03 / INVESTIGATE</span>
              <Fingerprint size={22} />
            </div>
            <h3>
              Evidence first.
              <br />
              Judgment second.
            </h3>
            <p>
              The read-only Analyst gathers scoped context and produces advisory
              findings. Missing evidence stays explicit. Human review stays
              essential.
            </p>
          </article>
        </div>
      </section>
      <section id="principles" className="principles">
        <div className="eyebrow">CONTROL STAYS WITH YOU</div>
        <h2>
          Connected to your stack.
          <br />
          Not in control of it.
        </h2>
        <div>
          <p>
            Corvus reads security data. It does not isolate endpoints, execute
            remediation, or treat a model recommendation as authorization.
          </p>
          <p>
            External model processing requires explicit approval. Credentials
            stay server-side; logs are evidence, never instructions.
          </p>
        </div>
      </section>
      <footer className="landing-footer">
        <Brand />
        <span>Wazuh · PostgreSQL · Azure Foundry</span>
        <Link href="/login">
          Open workspace <ArrowUpRight size={14} />
        </Link>
      </footer>
    </main>
  );
}
