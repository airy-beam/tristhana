"""TLS settings for Supabase (ADR-0014). Regression: the first deploy failed with
"CA cert does not include key usage extension" under Python 3.13's strict X.509 checks."""

import ssl
from pathlib import Path

from tristhana.infrastructure.db.engine import connect_args, tls_context

SUPABASE_CA = (
    Path(__file__).resolve().parents[3] / "infra" / "supabase" / "certs" / "supabase-ca.crt"
)


def test_supabase_ca_is_verified_fully_without_strict_mode() -> None:
    context = tls_context(SUPABASE_CA)

    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert not context.verify_flags & ssl.VERIFY_X509_STRICT
    assert "Supabase Root 2021 CA" in str(context.get_ca_certs())


def test_no_ca_file_means_no_tls_override() -> None:
    assert "ssl" not in connect_args(None)
