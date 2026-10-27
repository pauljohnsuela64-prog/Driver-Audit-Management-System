import os
from unittest.mock import patch
import pytest
from desktop.api import ApiClient,ApiError
from desktop.config import Config
from tests.desktop.tls_demo import tls_demonstration


def test_disposable_tls_trust_hostname_and_rejection():
    with tls_demonstration('first fictional administrator password','second fictional administrator password') as demo:
        client=ApiClient(Config(demo.origin))
        assert client.health() is True
        login=client.sign_in('demo_admin','first fictional administrator password');client.logout(login.token)
        with patch.dict(os.environ,{'SSL_CERT_FILE':''}):
            with pytest.raises(ApiError) as unknown:client.health()
            assert unknown.value.status==0
        with pytest.raises(ApiError) as hostname:
            ApiClient(Config(demo.origin.replace('127.0.0.1','localhost'))).health()
        assert hostname.value.status==0
