import logging
import socket
import sys

import paramiko.auth_handler
import requests
import argparse


def valid(self, msg):
    self.auth_event.set()
    self.authenticated = True
    print("Valid key")


def parse_service_accept(self, m):
    # https://tools.ietf.org/html/rfc4252#section-7
    service = m.get_text()
    if not (service == "ssh-userauth" and self.auth_method == "publickey"):
        return self._parse_service_accept(m)
    m = paramiko.message.Message()
    m.add_byte(paramiko.common.cMSG_USERAUTH_REQUEST)
    m.add_string(self.username)
    m.add_string("ssh-connection")
    m.add_string(self.auth_method)
    m.add_boolean(False)
    m.add_string(self.private_key.public_blob.key_type)
    m.add_string(self.private_key.public_blob.key_blob)
    self.transport._send_message(m)


def patch_paramiko():
    table = paramiko.auth_handler.AuthHandler._client_handler_table

    # In order to avoid using a private key, two callbacks must be patched.
    # The MSG_USERAUTH_INFO_REQUEST (SSH_MSG_USERAUTH_PK_OK 60) indicates a valid public key.
    table[paramiko.common.MSG_USERAUTH_INFO_REQUEST] = valid
    # The MSG_SERVICE_ACCEPT event triggers when server sends a request for auth.
    # By default, paramiko signs it with the private key. We don't want that.
    table[paramiko.common.MSG_SERVICE_ACCEPT] = parse_service_accept


def probe_host(hostname_or_ip, port, username, public_key):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((hostname_or_ip, port))
    transport = paramiko.transport.Transport(sock)
    transport.start_client()

    # For compatibility with paramiko, we need to generate a random private key and replace
    # the public key with our data.
    key = paramiko.RSAKey.generate(2048)
    key.public_blob = paramiko.pkey.PublicBlob.from_string(public_key)
    try:
        transport.auth_publickey(username, key)
    except paramiko.ssh_exception.AuthenticationException:
        print("Bad key")


def get_public_key(username):
    r = requests.get('https://github.com/%s.keys' % username)
    return r.content.decode('utf-8').splitlines()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('host', type=str, help='Hostname or IP address')
    parser.add_argument('--github-username', type=str, default=None)
    parser.add_argument('--ssh-username', type=str, default="root")
    parser.add_argument('--loglevel', default='INFO')
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--public-key', type=str, default=None)

    args = parser.parse_args(sys.argv[1:])
    logging.basicConfig(level=args.loglevel)
    if args.github_username:
        keys = get_public_key(args.github_username)
    elif args.public_key:
        keys = [open(args.public_key, 'rt').read()]
    else:
        raise ValueError("Public key is missing. Please use --github-username or --public-key")

    for key in keys:
        patch_paramiko()
        probe_host(
            hostname_or_ip=args.host,
            port=args.port,
            username=args.ssh_username,
            public_key=key
        )


if __name__ == '__main__':
    main()
