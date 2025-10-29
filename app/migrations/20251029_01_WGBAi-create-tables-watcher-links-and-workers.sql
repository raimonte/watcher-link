-- Create tables watcher_links and workers 
-- depends: 

create table watcher_links (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  payload_hash bytea not null unique,        -- sha256(payload)
  scope text not null default 'dashboard',
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create table workers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  name text not null,
  last_seen_at timestamptz not null,
  hashrate_mh numeric(18,3) not null,        -- без float/double
  status text not null check (status in ('online','offline','inactive'))
);

create index on workers (user_id);


