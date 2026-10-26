import pytest


@pytest.mark.parametrize("environment", [{}, {"GITHUB_ACTIONS": "true"},
    {"RUNNER_ENVIRONMENT": "github-hosted"}])
def test_ci_provisioning_refuses_non_hosted_environment(monkeypatch, environment):
    from scripts.ci_mysql import require_hosted_runner
    for key in ["GITHUB_ACTIONS", "RUNNER_ENVIRONMENT"]:
        monkeypatch.delenv(key, raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(SystemExit, match="GitHub-hosted"):
        require_hosted_runner()
