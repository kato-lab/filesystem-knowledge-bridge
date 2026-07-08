# autofs / NFS notes

If `/home/<user>` is managed by autofs, Docker bind mounts may not see newly triggered mounts unless mount propagation is configured.

Use:

```yaml
volumes:
  - type: bind
    source: /home
    target: /host_home
    read_only: true
    bind:
      propagation: rslave
```

In some environments, it may be more stable to mount the NFS export directly on the AI server, for example:

```text
/mnt/lab-home/<user>/knowledge
```

and bind mount `/mnt/lab-home` into the container.
