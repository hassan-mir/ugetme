# Security

ugetme runs a small HTTP service on your computer. This page says how it protects you, and how to report a problem.

## How ugetme protects you

- The service listens on `127.0.0.1` only, never on a network interface.
- Every request except `GET /health` needs the token in `~/.ugetme/token`. Web pages cannot read that file, and the service refuses browser preflight (`OPTIONS`) requests, so a web page cannot use the service.
- The cleanup engine never inherits the login or the credential variables of the program that started the service. It uses only the Claude login chosen in setup.
- Files with your text (settings, token, word list, log, pending checks) are written with owner-only permissions, and `~/.ugetme` is created with mode 0700.
- Text that ugetme cleans goes only to the engine you chose: `claude -p` with your login, or the OpenAI-compatible URL in your settings.

## Report a problem

Please do not open a public issue for a security problem. Open a private report through GitHub's **Security → Report a vulnerability** on this repository, with the steps to reproduce it. You will get an answer within a week.
