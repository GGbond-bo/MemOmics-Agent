# Source and test build notes

This source branch includes a small Windows password-SSH askpass helper.  It is
part of the password-login route and must remain paired with its source file.

| Item | Location | SHA-256 |
| --- | --- | --- |
| Helper source | `memomics/bio_tools/askpass_helper.cs` | `2ECA4C55CDA60367063A0CF263380141436F46415FE7C0372260291F0105CE9A` |
| Helper binary | `memomics/bio_tools/askpass_helper.exe` | `CC5C87A35EE092E318956F20E0DDD24AB4EC09E861491198603777748EAC32CF` |

The committed binary is built with the Microsoft .NET Framework compiler:

```text
Compiler: C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe
Compiler version: 4.8.9221.0 built by: NET481REL1LAST_25H2
Target: /target:winexe /optimize+
```

If `askpass_helper.cs` is changed, rebuild the helper, update
`ASKPASS_HELPER_SHA256` in `memomics/bio_tools/password_ssh.py` to the new
binary SHA-256, and rerun the password-SSH tests.  The runtime verifies the
binary hash and fails closed when the executable is absent or altered.

From the repository root, the equivalent rebuild command is:

```text
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /target:winexe /optimize+ /out:memomics\bio_tools\askpass_helper.exe memomics\bio_tools\askpass_helper.cs
```

For a standard development environment with the repository dependencies and
`pytest` installed, run the focused Python tests with:

```text
python -m pytest webui/tests/test_cluster_catalog_v2.py webui/tests/test_cluster_catalog_v4.py webui/tests/test_cluster_catalog_v5.py webui/tests/test_cluster_catalog_server_adapter.py webui/tests/test_cluster_credentials.py webui/tests/test_project_metadata_and_cluster_binding.py webui/tests/test_v5_password_route_policy.py webui/tests/test_v5_password_scp_runtime.py
```

The browser-free UI regressions use Node's built-in runtime, for example:

```text
node webui/tests/cluster_catalog_v5_fullpage_click.test.js
node webui/tests/cluster_catalog_v5_dialog_fix.test.js
node webui/tests/project_sessions_ui.test.js
```

## Source PR scope

This source handoff contains the `webui/server.py` and `webui/index.html`
integration, tests, and these additive modules:

| Module | Responsibility |
| --- | --- |
| `memomics/session_metadata.py` | Durable project and chat metadata tables. |
| `memomics/cluster_catalog.py` | Server, login-node, node, account, and matched-connection catalog. |
| `memomics/cluster_credentials.py` | Per-account Windows-encrypted password storage. |
| `webui/cluster_catalog_api.py` | Catalog REST router and validation boundary. |
| `memomics/bio_tools/ssh_policy.py` | Managed SSH argument and route policy. |
| `memomics/bio_tools/password_ssh.py` | Password-only SSH/SCP runtime with helper integrity checks. |
| `memomics/bio_tools/askpass_security.py` | Askpass helper trust and execution safeguards. |

It intentionally excludes bundled Python, runtime databases, user settings,
model keys, SSH credentials, cluster profiles, caches, and result data.
