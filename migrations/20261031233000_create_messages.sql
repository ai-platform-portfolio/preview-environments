CREATE TABLE public.messages (
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    text varchar(500) NOT NULL CHECK (length(btrim(text)) > 0),
    id uuid PRIMARY KEY
);
