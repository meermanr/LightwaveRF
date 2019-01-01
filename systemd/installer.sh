#!/bin/bash -x
sudo ln -s $(readlink -f lightwaverf.service) /etc/systemd/system/
sudo systemctl start lightwaverf

sudo ln -s $(readlink -f docker-cleanup.timer) $(readlink -f docker-cleanup.service) /etc/systemd/system/
sudo systemctl enable docker-cleanup.timer
