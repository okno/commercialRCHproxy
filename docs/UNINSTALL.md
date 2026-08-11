# Uninstall

Default application removal:

```bash
sudo ./scripts/uninstall.sh
```

The service and installed application are removed. The following evidence is preserved:

- `/var/lib/commercialrchproxy/jobs`;
- `/etc/commercialrchproxy`;
- `/var/log/commercialrchproxy`.

Application uninstall does not change networking. If the optional helper was
installed, its separate service and address state are preserved by default.
Remove it explicitly before or after application uninstall:

```bash
sudo ./scripts/manage_secondary_ip.sh uninstall
```

The helper removes only an exact address that its runtime ownership state says
it added. A pre-existing/borrowed address is preserved. If the source checkout
is no longer available, the installed helper is at
`/usr/local/libexec/commercialrchproxy-network/manage_secondary_ip.sh`.

Destructive purge requires both the explicit flag and interactive confirmation:

```bash
sudo ./scripts/uninstall.sh --purge
```

Purge refuses while the optional secondary-address service is installed,
active, or enabled because it depends on a root-only configuration below
`/etc/commercialrchproxy`.

Purge destroys configuration, archives, and logs and is not recoverable unless an external backup exists. Follow legal/accounting retention obligations and verify backup integrity first.
