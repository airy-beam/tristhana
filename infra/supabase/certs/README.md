# Supabase CA certificate

Put Supabase's root CA here as `supabase-ca.crt` (Supabase dashboard → Project Settings →
Database → SSL Configuration → Download certificate). It is public, not a secret.

The image copies this folder to `/app/certs`, and the deploy sets
`DATABASE_CA_FILE=/app/certs/supabase-ca.crt`, so the API and the migrations job verify the
pooler's certificate and hostname (TLS verify-full, ADR-0014). Without the file the service
fails to start, and Cloud Run keeps the previous revision.
