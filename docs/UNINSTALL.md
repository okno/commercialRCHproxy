# Uninstall

Default application removal:

```bash
sudo ./scripts/uninstall.sh
```

The service and installed application are removed. The following evidence is preserved:

- `/var/lib/commercialrchproxy/jobs`;
- `/etc/commercialrchproxy`;
- `/var/log/commercialrchproxy`.

The script does not remove the manually configured secondary IP or unrelated firewall/network configuration.

Destructive purge requires both the explicit flag and interactive confirmation:

```bash
sudo ./scripts/uninstall.sh --purge
```

Purge destroys configuration, archives, and logs and is not recoverable unless an external backup exists. Follow legal/accounting retention obligations and verify backup integrity first.
