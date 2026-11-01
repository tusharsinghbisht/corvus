export type AnalystPolicy = {
  connection_id: string;
  name: string;
  ingestion_enabled: boolean;
  enabled: boolean;
  minimum_level: 7 | 12 | 15;
  hourly_limit: number;
  daily_limit: number;
  version: number;
  activated_at: string | null;
  consent_at: string | null;
  used_hour: number;
  used_day: number;
};
export type AnalystSettings = {
  policies: AnalystPolicy[];
  global_daily_limit: number;
  global_used_day: number;
};
