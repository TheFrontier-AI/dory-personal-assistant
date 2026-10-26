"""scripts/deploy.sh against a fake gcloud: a redeploy keeps what the live service needs.

`gcloud run deploy --set-env-vars / --set-secrets` REPLACES the service's lists, so anything the
script does not pass is dropped on the next deploy (Sign in with Discord broke that way)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "deploy.sh"

FAKE_GCLOUD = """#!/usr/bin/env bash
echo "$*" >> "$GCLOUD_LOG"
case "$*" in
  *projectNumber*) echo 123 ;;
  *"secrets versions list"*) echo "projects/p/secrets/s/versions/1" ;;  # every secret has a version
  *status.url*) echo "https://meeting-scribe-123.asia-southeast1.run.app" ;;
esac
exit 0
"""


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_redeploy_passes_discord_sign_in_and_reads_dotenv(tmp_path):
    (tmp_path / "scripts").mkdir()
    shutil.copy(SCRIPT, tmp_path / "scripts" / "deploy.sh")
    # a repo of its own: the script cd's to its parent and reads that .env, never the real one
    (tmp_path / ".env").write_text(
        "HUB_GOOGLE_CLIENT_ID=web-client.apps.googleusercontent.com\n"
        "DORY_DISCORD_CLIENT_ID=123456789012345678\n"
        "HUB_ADMIN_EMAILS=a@example.com,b@example.com\n"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gcloud").write_text(FAKE_GCLOUD)
    (bin_dir / "gcloud").chmod(0o755)
    log = tmp_path / "gcloud.log"
    env = {
        "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "HOME": str(tmp_path),  # no ~/google-cloud-sdk/path.bash.inc: the fake gcloud stays first
        "GCLOUD_LOG": str(log),
        "GCP_PROJECT": "test-project",
    }
    run = subprocess.run(
        ["bash", str(tmp_path / "scripts" / "deploy.sh")], env=env, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stderr
    deploy = next(line for line in log.read_text().splitlines() if line.startswith("run deploy"))
    # update, never replace: a value set on the service by hand survives a redeploy that omits it
    assert "--update-env-vars" in deploy and "--update-secrets" in deploy
    assert "--set-env-vars" not in deploy and "--set-secrets" not in deploy
    assert "DORY_DISCORD_CLIENT_SECRET=dory-discord-client-secret:latest" in deploy
    assert "DORY_NEBIUS_API_KEY=dory-nebius-api-key:latest" in deploy
    assert "DORY_SESSION_SECRET=dory-session-secret:latest" in deploy
    # documented as "environment, else .env": the .env values reach the service
    assert "HUB_GOOGLE_CLIENT_ID=web-client.apps.googleusercontent.com" in deploy
    assert "DORY_DISCORD_CLIENT_ID=123456789012345678" in deploy
    assert "HUB_ADMIN_EMAILS=a@example.com,b@example.com" in deploy
