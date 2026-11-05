-- Reverting this metadata change preserves the table and message rows.
COMMENT ON TABLE public.messages IS 'Messages persisted by the platform delivery demonstration.';
