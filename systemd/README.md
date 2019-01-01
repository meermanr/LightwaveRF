Inspiration: https://gist.github.com/mosquito/b23e1c1e5723a7fd9e6568e5cf91180f

# LightwaveRF (docker compose) as a systemd unit

1. Edit path of WorkingDirectory in `lightwaverf.service`
2. Copy `lightwaverf.service` to `/etc/systemd/system/` 

```
systemctl start lightwaverf
```

# Docker cleanup timer with systemd

1. Copy `docker-cleanup.timer` to `/etc/systemd/system/` 
2. Copy `docker-cleanup.service` to `/etc/systemd/system/`
3. Run `systemctl enable docker-cleanup.timer`
