"""Generate isolated SDK public configuration for the packaged witness."""
import sys
import time
import jwt
from pathlib import Path
import control_plane_kit_core as core

sys.path.insert(0, "/source/products/cloudflared_connector/tests")
from managed_control_fixtures import fixture, token

value = fixture("a")
target = Path("/evidence/control.json")
target.write_bytes(core.ReceiverNodeControlConfigurationCodec().encode_bytes(value.config))
target.chmod(0o444)

claims = jwt.decode(token(value), options={"verify_signature": False})
now = int(time.time())
claims.update(iat=now, nbf=now, exp=now + 90)
grant = claims["workload_node_health_read"]
grant.update(issued_at=now, not_before=now, expires_at=now + 90)
credential = jwt.encode(claims, value.health_private, algorithm="EdDSA",
                        headers={"kid": grant["key_id"], "typ": "CPK-WORKLOAD-NODE-HEALTH-READ+JWT"})
token_file = Path("/evidence/synthetic-health.jwt")
token_file.write_text(credential)
token_file.chmod(0o400)
