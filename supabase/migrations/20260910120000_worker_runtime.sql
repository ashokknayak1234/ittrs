-- Apply after both existing ticket migrations. No ticket data is replaced.
CREATE TABLE public.ittrs_settings (key text PRIMARY KEY, value jsonb NOT NULL);
CREATE TABLE public.ittrs_sessions (token_hash text PRIMARY KEY, expires_at bigint NOT NULL);
CREATE INDEX ittrs_sessions_expiry ON public.ittrs_sessions(expires_at);
CREATE TABLE public.ittrs_rate_limits (key text PRIMARY KEY, count bigint NOT NULL, expires_at bigint NOT NULL);
CREATE INDEX ittrs_rate_limits_expiry ON public.ittrs_rate_limits(expires_at);

ALTER TABLE public.ittrs_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ittrs_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ittrs_rate_limits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.ittrs_settings, public.ittrs_sessions, public.ittrs_rate_limits FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.ittrs_settings, public.ittrs_sessions, public.ittrs_rate_limits TO service_role;

CREATE FUNCTION public.ittrs_rate_limit(p_key text, p_expires bigint, p_now bigint)
RETURNS bigint LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE n bigint;
BEGIN
  DELETE FROM public.ittrs_rate_limits WHERE expires_at < p_now;
  INSERT INTO public.ittrs_rate_limits AS r(key,count,expires_at) VALUES(p_key,1,p_expires)
    ON CONFLICT(key) DO UPDATE SET count=r.count+1 RETURNING count INTO n;
  RETURN n;
END;
$$;

CREATE FUNCTION public.ittrs_create_session(p_hash text, p_expires bigint, p_now bigint)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  DELETE FROM public.ittrs_sessions WHERE expires_at <= p_now;
  INSERT INTO public.ittrs_sessions(token_hash,expires_at) VALUES(p_hash,p_expires);
END;
$$;

CREATE FUNCTION public.ittrs_workload()
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
  SELECT COALESCE(jsonb_object_agg(team,n),'{}'::jsonb)
  FROM (SELECT team,count(*) n FROM public.tickets GROUP BY team) t;
$$;

CREATE FUNCTION public.ittrs_dashboard()
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
  SELECT jsonb_build_object(
    'total_tickets',count(*),
    'critical_tickets',count(*) FILTER(WHERE severity='Critical'),
    'sla_alerts',count(*) FILTER(WHERE sla_alerted),
    'not_satisfied',count(*) FILTER(WHERE satisfaction_status='Not_Satisfied'),
    'workload',public.ittrs_workload(),
    'tickets',(SELECT COALESCE(jsonb_agg(t ORDER BY t.created_at DESC),'[]'::jsonb)
               FROM (SELECT * FROM public.tickets ORDER BY created_at DESC LIMIT 100) t)
  ) FROM public.tickets;
$$;

REVOKE ALL ON FUNCTION public.ittrs_rate_limit(text,bigint,bigint), public.ittrs_create_session(text,bigint,bigint), public.ittrs_workload(), public.ittrs_dashboard() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ittrs_rate_limit(text,bigint,bigint), public.ittrs_create_session(text,bigint,bigint), public.ittrs_workload(), public.ittrs_dashboard() TO service_role;
