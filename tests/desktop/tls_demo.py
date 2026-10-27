"""Ephemeral TLS fixture: process-local trust only, never changes Windows roots."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import ipaddress
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID
from scripts.desktop_demo import demonstration


@contextmanager
def tls_demonstration(first,second):
    with TemporaryDirectory(prefix='dams-fictional-tls-') as directory:
        root=Path(directory);now=datetime.now(timezone.utc)
        ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'DAMS ephemeral test CA')])
        ca=(x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
            .add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),critical=False)
            .sign(ca_key,hashes.SHA256()))
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        certificate=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Fictional loopback API')]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
            .add_extension(x509.KeyUsage(True,False,True,False,False,False,False,False,False),critical=True)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
            .sign(ca_key,hashes.SHA256()))
        (root/'ca.pem').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        (root/'server.pem').write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        (root/'server.key').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        with patch.dict(os.environ,{'SSL_CERT_FILE':str(root/'ca.pem'),'SSLKEYLOGFILE':''}):
            with demonstration(first,second,tls=(root/'server.pem',root/'server.key')) as demo:yield demo
