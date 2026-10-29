"use client";

import { useState } from "react";

const layers = [
  {
    id: "source",
    label: "Wazuh",
    subtitle: "The source",
    description:
      "Detections and high-volume telemetry stay in Wazuh. Corvus connects with a dedicated read-only account.",
  },
  {
    id: "engine",
    label: "Corvus",
    subtitle: "The investigation layer",
    description:
      "Alerts retain their identity and context. The collector and Analyst build on the source, rather than replacing your SIEM.",
  },
  {
    id: "storage",
    label: "PostgreSQL",
    subtitle: "The durable record",
    description:
      "Alerts, checkpoints, connections, and audit events survive browser sessions and application restarts.",
  },
] as const;

export function InvestigationScene() {
  const [selected, setSelected] = useState<string>("engine");
  const active = layers.find((layer) => layer.id === selected)!;
  return (
    <div className="investigation-scene">
      <div className="scene-caption">
        <span className="scene-cross">+</span> THE CORVUS INVESTIGATION LAYER{" "}
        <span>01—03</span>
      </div>
      <svg
        className="isometric-scene"
        viewBox="0 0 760 490"
        role="img"
        aria-labelledby="scene-title scene-description"
      >
        <title id="scene-title">
          An isometric view of Wazuh, Corvus, and PostgreSQL
        </title>
        <desc id="scene-description">
          Three connected platforms. Select a platform or its label to explore
          what it does.
        </desc>
        <defs>
          <pattern
            id="scene-grid"
            width="52"
            height="30"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M0 15 26 0 52 15 26 30Z"
              fill="none"
              stroke="#252525"
              strokeWidth=".65"
            />
          </pattern>
        </defs>
        <path
          d="m24 287 353-204 359 207-353 204Z"
          fill="url(#scene-grid)"
          opacity=".6"
        />
        <path className="scene-rail" d="m176 293 205 118 206-119M381 411V332" />
        <path
          className="scene-signal"
          d="m176 293 205 118 206-119M381 411V332"
        />
        <ellipse cx="380" cy="372" rx="116" ry="30" fill="#000" opacity=".55" />
        <g
          className={`iso-platform ${selected === "source" ? "selected" : ""}`}
          role="button"
          tabIndex={0}
          aria-label="Explore Wazuh source"
          aria-pressed={selected === "source"}
          onClick={() => setSelected("source")}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setSelected("source");
            }
          }}
        >
          <path
            d="m70 247 106-61 106 61v34l-106 61-106-61Z"
            fill="#111"
            stroke="#404040"
          />
          <path d="m70 247 106 61v34L70 281Z" fill="#151515" stroke="#404040" />
          <path
            d="m176 308 106-61v34l-106 61Z"
            fill="#202020"
            stroke="#404040"
          />
          <path
            className="iso-top"
            d="m70 247 106-61 106 61-106 61Z"
            fill="#242424"
            stroke="#686868"
          />
          <g
            transform="matrix(.85 -.49 .85 .49 142 246)"
            fill="none"
            stroke="#dedede"
            strokeWidth="2.5"
          >
            <path d="M0 0v-25h34V0Z" />
            <path d="M7-17h20M7-9h20M13 8h8M17 0v8" />
          </g>
          <text x="176" y="373" textAnchor="middle">
            Wazuh
          </text>
          <text className="iso-subtitle" x="176" y="393" textAnchor="middle">
            DETECTIONS & TELEMETRY
          </text>
        </g>
        <g
          className={`iso-platform iso-engine ${selected === "engine" ? "selected" : ""}`}
          role="button"
          tabIndex={0}
          aria-label="Explore Corvus investigation layer"
          aria-pressed={selected === "engine"}
          onClick={() => setSelected("engine")}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setSelected("engine");
            }
          }}
        >
          <path
            d="m267 272 114-66 114 66v25l-114 66-114-66Z"
            fill="#171717"
            stroke="#454545"
          />
          <path
            d="m267 272 114 66 114-66M381 338v25"
            fill="none"
            stroke="#454545"
          />
          <path
            d="m267 226 114-66 114 66v25l-114 66-114-66Z"
            fill="#1c1c1c"
            stroke="#626262"
          />
          <path
            d="m267 226 114 66 114-66M381 292v25"
            fill="none"
            stroke="#626262"
          />
          <path
            className="iso-top"
            d="m267 180 114-66 114 66v25l-114 66-114-66Z"
            fill="#333"
            stroke="#a3a3a3"
          />
          <path
            d="m267 180 114 66 114-66M381 246v25"
            fill="none"
            stroke="#a3a3a3"
          />
          <g transform="matrix(.9 -.52 .9 .52 322 180)" color="#f5f5f5">
            <use href="/brand/mark.svg#raven" width="64" height="64" />
          </g>
          <path
            d="m327 293 24 14m-24-61 24 14m-24-61 24 14"
            stroke="#a3a3a3"
            strokeWidth="2"
          />
          <text x="381" y="68" textAnchor="middle">
            Corvus
          </text>
          <text className="iso-subtitle" x="381" y="89" textAnchor="middle">
            INVESTIGATION LAYER
          </text>
        </g>
        <g
          className={`iso-platform ${selected === "storage" ? "selected" : ""}`}
          role="button"
          tabIndex={0}
          aria-label="Explore PostgreSQL storage"
          aria-pressed={selected === "storage"}
          onClick={() => setSelected("storage")}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setSelected("storage");
            }
          }}
        >
          <path
            d="m481 247 106-61 106 61v34l-106 61-106-61Z"
            fill="#151515"
            stroke="#404040"
          />
          <path
            d="m481 247 106 61v34l-106-61Z"
            fill="#181818"
            stroke="#404040"
          />
          <path
            d="m587 308 106-61v34l-106 61Z"
            fill="#202020"
            stroke="#404040"
          />
          <path
            className="iso-top"
            d="m481 247 106-61 106 61-106 61Z"
            fill="#242424"
            stroke="#686868"
          />
          <g
            transform="matrix(.85 -.49 .85 .49 558 246)"
            fill="none"
            stroke="#dedede"
            strokeWidth="2.5"
          >
            <ellipse cx="17" cy="-19" rx="20" ry="7" />
            <path d="M-3-19V7c0 10 40 10 40 0v-26M-3-6c0 10 40 10 40 0" />
          </g>
          <text x="587" y="373" textAnchor="middle">
            PostgreSQL
          </text>
          <text className="iso-subtitle" x="587" y="393" textAnchor="middle">
            PERSISTENCE & PROVENANCE
          </text>
        </g>
      </svg>
      <div
        className="scene-controls"
        role="group"
        aria-label="Explore the architecture"
      >
        {layers.map((layer) => (
          <button
            key={layer.id}
            aria-pressed={selected === layer.id}
            onClick={() => setSelected(layer.id)}
          >
            {layer.label}
            <span>↗</span>
          </button>
        ))}
      </div>
      <div className="scene-description" aria-live="polite">
        <span>{active.subtitle}</span>
        <p>{active.description}</p>
      </div>
    </div>
  );
}

export function EvidenceIllustration() {
  return (
    <svg
      viewBox="0 0 320 190"
      className="feature-illustration"
      aria-hidden="true"
    >
      {[48, 24, 0].map((offset, index) => (
        <g key={offset} transform={`translate(0 ${offset})`}>
          <path
            d="m52 71 101-56 112 62v13l-101 56L52 84Z"
            fill={index === 2 ? "#252525" : "#141414"}
            stroke={index === 2 ? "#646464" : "#3b3b3b"}
          />
          <path
            d="m52 71 112 62 101-56M164 133v13"
            fill="none"
            stroke="#454545"
          />
          {index === 2 && (
            <g stroke="#c4c4c4" strokeWidth="2">
              <path d="m111 63 47-26 41 23-47 26ZM120 86l37 21m15-9 24-13m-13-7 24-13" />
              <path d="m153 52 13 7-13 8-13-8Z" fill="#c4c4c4" />
            </g>
          )}
        </g>
      ))}
    </svg>
  );
}

export function StorageIllustration() {
  return (
    <svg
      viewBox="0 0 320 190"
      className="feature-illustration"
      aria-hidden="true"
    >
      <path
        d="m30 128 128 72 128-72M158 200v-65"
        fill="none"
        stroke="#3f3f3f"
        strokeDasharray="4 5"
      />
      {[
        { x: 60, y: 88 },
        { x: 158, y: 40 },
        { x: 256, y: 88 },
      ].map(({ x, y }, index) => (
        <g key={x}>
          <path
            d={`M${x - 39} ${y}l39-22 39 22v43l-39 22-39-22Z`}
            fill="#171717"
            stroke="#494949"
          />
          <path
            d={`M${x - 39} ${y}l39 22 39-22M${x} ${y + 22}v43`}
            fill="none"
            stroke="#494949"
          />
          <path
            d={`M${x - 39} ${y}l39-22 39 22-39 22Z`}
            fill={index === 1 ? "#3a3a3a" : "#242424"}
            stroke="#777"
          />
          <path
            d={`M${x - 24} ${y + 25}l13 7m-13 3 13 7`}
            stroke="#aaa"
            strokeWidth="2"
          />
        </g>
      ))}
    </svg>
  );
}
