# Update

Deployment dependencies are pinned and hash-checked in
`requirements-deployment.lock`. A dependency upgrade requires regenerating and
reviewing that file together with `requirements-deployment.in`; the updater
does not silently broaden versions.

Test and CI dependencies are independently pinned and hash-checked in
`requirements-dev.lock`, generated from `requirements-dev.in`. Changes to
either input/lock pair must be reviewed together.

Run from the trusted Git checkout:

```bash
cd commercialRCHproxy
sudo ./scripts/update.sh
```

The update procedure backs up the installed application/configuration, fetches and accepts only a fast-forward Git update, refreshes the virtual environment, runs automated tests, restarts the service, and runs a non-invasive health check.

Before updating:

- schedule a management-software/fiscal change window;
- confirm recent protected backups;
- inspect the changelog and protocol evidence changes;
- stop if the working tree contains unexplained modifications;
- never add a real PCAP/RAW/PDF to Git.

If deployment, restart, or health fails after activation, the installer restores
the prior release link, systemd unit, operations scripts, enabled/disabled
state, and prior active/inactive state. The separate pre-update backup remains
the recovery source for configuration, captured data, and logs. A transport
job in an unknown fiscal state must never be replayed automatically.
