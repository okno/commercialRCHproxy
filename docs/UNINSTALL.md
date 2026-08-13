# Uninstall

Default removal:

```bash
sudo ./scripts/uninstall.sh
```

The uninstall path should stop/remove:

- `commercialrchproxy-dumper.service`;
- `commercialrchproxy-parser.service`;
- legacy `commercialrchproxy.service` launcher;
- installed application/runtime scripts.

It must preserve by default:

- configured `OUTPUT_DIR`, including hidden `.state`, partials,
  ready/parsed jobs, and backups;
- `/etc/commercialrchproxy`;
- configured `LOG_DIR`;
- configured service account/group, so retained ownership remains stable.

Application uninstall does not change networking. If the optional secondary
address helper was installed, remove it separately only under an approved
network change:

```bash
sudo ./scripts/manage_secondary_ip.sh uninstall
```

The helper removes only an address its ownership state says it added. A
pre-existing/borrowed address is preserved.

Destructive purge requires the explicit flag and interactive confirmation:

```bash
sudo ./scripts/uninstall.sh --purge
```

Purge must refuse while the optional secondary-address service depends on the
application configuration. It destroys configuration, RAW/spool/counter state,
parsed outputs, and logs; recovery then requires an external verified backup.
It parses the preserved configuration without executing it and deletes only
the validated configured output/log roots and account; if exact targets cannot
be resolved, purge fails closed.
Follow legal/accounting/privacy retention policy and verify restore integrity
first. Uninstall or migration never authorizes replaying captured requests.
