export type Alert = {
  id: string;
  connection_id: string;
  timestamp: string;
  received_at: string;
  agent_id: string | null;
  agent_name: string | null;
  rule_id: string | null;
  rule_level: number;
  title: string;
  native_index: string;
  native_id: string;
};

export type AlertDetail = Alert & {
  document: {
    reference: Record<string, string>;
    context: Record<string, unknown>;
    source: Record<string, unknown>;
  };
};

export type Connection = {
  id: string;
  name: string;
  indexer_url: string;
  username: string;
  enabled: boolean;
  backfill_start: string;
  checkpoint: string;
  last_sync_at: string | null;
  last_error: string | null;
};

export type ConnectionData = {
  connections: Connection[];
  indexer_hosts: string[];
};
export type AlertPage = {
  alerts: Alert[];
  next_cursor: string | null;
  stats: { total: number; high: number; agents: number };
};
